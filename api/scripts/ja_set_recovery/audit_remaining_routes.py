#!/usr/bin/env python3
"""Audit the 60 held routes using existing evidence only; never navigate or map cards."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from collect_listings import canonical_listing_url, canonical_product_url

RUN = Path(__file__).resolve().parents[3] / 'data/catalogue-gaps/ja-set-recovery-20261029-v3'


def audit(run_dir: Path) -> dict:
    registry = {row['group_id']: row for row in json.loads((run_dir / 'set-registry.json').read_text())}
    queue = json.loads((run_dir / 'shared-listing-review-queue.json').read_text())
    main = json.loads((run_dir / 'listing-progress.json').read_text())
    cache = {url: path for group in main['groups'].values() for url, path in group.get('pages', {}).items()}
    pool_progress = run_dir / 'shared-listings-progress.json'
    if pool_progress.exists():
        pools = json.loads(pool_progress.read_text())
        cache.update({url: path for source in pools.get('sources', {}).values()
                      for url, path in source.get('pages', {}).items()})
    cache = {canonical_listing_url(url): Path(path) for url, path in cache.items() if Path(path).is_file()}
    live_path = run_dir / 'review/remaining-route-live-checks.json'
    live = {row['url']: row for row in json.loads(live_path.read_text())} if live_path.exists() else {}
    sources = []
    for entry in queue:
        pending, seen, products, missing = [entry['url']], set(), {}, []
        evidence = set()
        while pending:
            url = canonical_listing_url(pending.pop(0))
            if url in seen:
                continue
            seen.add(url)
            if url not in cache:
                missing.append(url)
                continue
            path = cache[url]
            result = json.loads(path.read_text()).get('result', {})
            evidence.add(str(path))
            if result.get('outcome') not in {'offers', 'empty', 'listing_links'}:
                missing.append(url)
                continue
            pending.extend(result.get('listing_urls', []) + result.get('pagination_urls', []))
            for product in result.get('products', []):
                canonical = canonical_product_url(product['url'])
                products[canonical] = {**product, 'url': canonical}
        sources.append({
            'name': entry['name'], 'url': entry['url'], 'related_group_ids': entry['group_ids'],
            'collection_complete_from_cache': not missing,
            'cached_product_count': len(products),
            'cached_product_examples': list(products.values())[:3],
            'missing_page_urls': missing, 'evidence_files': sorted(evidence),
            'live_route_check': live.get(entry['url']), 'membership_verified': False,
        })
    decisions = list(csv.DictReader((run_dir / 'review/remaining-group-routing.csv').open()))
    groups = []
    for decision in decisions:
        gid = decision['group_id']
        related = [source for source in sources if gid in source['related_group_ids']]
        state = decision['state']
        scope = ('shared_collection_route' if state == 'shared_listing_needs_partition'
                 else 'combined_collection_routes' if state == 'multi_listing_group_requires_union'
                 else 'candidate_pool_only' if state == 'broad_pool_needs_card_match'
                 else 'no_confirmed_route')
        groups.append({
            'group_id': gid, 'name': registry[gid]['name'], 'code': registry[gid]['code'],
            'reference_card_count': registry[gid]['listed_cards'], 'route_scope': scope,
            'sources': [source['url'] for source in related],
            'all_source_pages_cached': bool(related) and all(source['collection_complete_from_cache'] for source in related),
            'live_source_routes_checked': sum(bool(source['live_route_check']) for source in related),
            'membership_verified': False,
            'next_action': decision['next_action'],
        })
    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'method': 'Read existing mapped/pool page evidence and manual browser route checks; no network, no card mapping, no source ledger edits.',
        'held_groups': len(groups), 'scope_counts': dict(Counter(g['route_scope'] for g in groups)),
        'distinct_review_sources': len(sources),
        'fully_cached_sources': sum(s['collection_complete_from_cache'] for s in sources),
        'sources_with_live_route_check': sum(bool(s['live_route_check']) for s in sources),
        'sources': sources, 'groups': groups,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, default=RUN)
    args = parser.parse_args()
    result = audit(args.run_dir)
    destination = args.run_dir / 'review/remaining-route-acquisition-audit.json'
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    csv_path = destination.with_suffix('.csv')
    with csv_path.open('w') as stream:
        fields = ['group_id', 'name', 'code', 'reference_card_count', 'route_scope', 'sources',
                  'all_source_pages_cached', 'live_source_routes_checked', 'membership_verified', 'next_action']
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in result['groups']:
            writer.writerow({**row, 'sources': ' | '.join(row['sources'])})
    print(json.dumps({k: v for k, v in result.items() if k not in {'sources', 'groups'}}, indent=2))


if __name__ == '__main__':
    main()
