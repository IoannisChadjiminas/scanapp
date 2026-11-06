#!/usr/bin/env python3
"""Collect review-pool URLs once without asserting group/card membership.

Run after the mapped collection queue is complete. Exact URL pages already
collected by that queue are reused from their evidence files; only additional
pool pages are navigated in the same local Chrome lane.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from collect_listings import canonical_listing_url, canonical_product_url, write_json
from local_client import RUN, request


def read_result(path: str | Path) -> dict:
    return json.loads(Path(path).read_text()).get('result', {})


def evidence_path(run_dir: Path, source_id: str, url: str, result: dict,
                  group_ids: list[str] | None = None) -> Path:
    payload = {
        'source_id': source_id,
        'source_url': url,
        'related_group_ids': group_ids or [],
        'membership_verified': False,
        'retrieved_at': datetime.now(timezone.utc).isoformat(),
        'result': result,
    }
    data = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    path = run_dir / 'source-pages' / 'shared-listings' / source_id / (hashlib.sha256(data).hexdigest()[:20] + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    return path


def page_cache(run_dir: Path, main_progress: dict, pool_state: dict) -> dict[str, str]:
    cache: dict[str, str] = {}
    for group in main_progress.get('groups', {}).values():
        cache.update(group.get('pages', {}))
    for source in pool_state.get('sources', {}).values():
        cache.update(source.get('pages', {}))
        cache.update(source.get('cached_pages', {}))
    return {url: path for url, path in cache.items() if Path(path).exists()}


def evidence_locale(path: str | Path, fallback_url: str) -> str:
    try:
        source_url = json.loads(Path(path).read_text()).get('source_url', fallback_url)
    except (OSError, ValueError, TypeError):
        source_url = fallback_url
    return urlsplit(str(source_url)).path.strip('/').split('/', 1)[0].casefold()


def normalize_existing_sources(state: dict) -> None:
    """Keep English evidence and enqueue translated pages again under /en/."""
    for source in state['sources'].values():
        pages = source.get('pages', {})
        english_pages = {}
        translated_routes = []
        for url, evidence in pages.items():
            canonical = canonical_listing_url(url)
            if evidence_locale(evidence, url) == 'en':
                english_pages[canonical] = evidence
            else:
                translated_routes.append(canonical)

        if translated_routes:
            source['pages'] = english_pages
            source['pending'] = list(dict.fromkeys(
                source.get('pending', []) + translated_routes
            ))
            source['products'] = {}

        waiting = source.get('waiting_for_owner')
        pending = []
        for index, url in enumerate(source.get('pending', [])):
            # The paused URL must match the live browser session exactly for
            # owner confirmation. After confirmation it is requeued in English.
            if waiting and index == 0:
                pending.append(url)
            else:
                pending.append(canonical_listing_url(url))
        source['pending'] = list(dict.fromkeys(pending))
        # Rebuild from the retained English evidence so dropping translated
        # page records cannot silently drop their English duplicates too.
        products = {}
        for page_url, evidence in source.get('pages', {}).items():
            if evidence_locale(evidence, page_url) != 'en':
                continue
            for item in read_result(evidence).get('products', []):
                product_url = canonical_product_url(item.get('url', ''))
                products[product_url] = {
                    'source_id': source['source_id'],
                    'source_url': source['url'],
                    'source_name': source.get('name', ''),
                    'related_group_ids': source.get('related_group_ids', []),
                    'membership_verified': False,
                    'url': product_url,
                    'name': item.get('name', ''),
                    'evidence_file': evidence,
                }
        source['products'] = products


def snapshot(run_dir: Path, state: dict) -> None:
    rows = []
    for source in state['sources'].values():
        for product in source.get('products', {}).values():
            rows.append(product)
    rows.sort(key=lambda row: (row['source_url'], row['url']))
    target = run_dir / 'shared-listings-products.jsonl'
    temporary = target.with_suffix('.jsonl.tmp')
    temporary.write_text(''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in rows))
    os.replace(temporary, target)


def write_report(run_dir: Path, state: dict, pages_fetched: int, pages_reused: int,
                 state_name: str) -> dict:
    sources = list(state['sources'].values())
    products = {row['url'] for source in sources for row in source.get('products', {}).values()}
    report = {
        'state': state_name,
        'pool_urls': len(sources),
        'pool_sources_complete': sum(source.get('state') == 'complete' for source in sources),
        'pool_sources_in_scope': len(sources),
        'pages_fetched_this_run': pages_fetched,
        'pages_reused_from_cache_this_run': pages_reused,
        'distinct_product_urls': len(products),
        'membership_verified': False,
    }
    write_json(run_dir / 'shared-listings-report.json', report)
    return report


def validate(queue: list[dict], registry: list[dict]) -> None:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scraper'))
    from allow import cardmarket_expansion_listing

    allowed = {row['group_id'] for row in registry}
    seen: set[str] = set()
    for row in queue:
        url = row['url']
        if url in seen:
            raise ValueError(f'Duplicate pool URL; queue must be deduplicated: {url}')
        seen.add(url)
        if not cardmarket_expansion_listing(url):
            raise ValueError(f'Invalid observed Cardmarket expansion URL: {url}')
        if not row.get('group_ids') or not set(row['group_ids']) <= allowed:
            raise ValueError(f'Invalid related group IDs for pool URL: {url}')


def collect(queue: list[dict], run_dir: Path, session_id: str, max_pages: int,
            confirm: bool = False, call=request) -> dict:
    queue = [{**row, 'url': canonical_listing_url(row['url'])} for row in queue]
    registry = json.loads((run_dir / 'set-registry.json').read_text())
    validate(queue, registry)
    manifest = json.loads((run_dir / 'listing-seeds.json').read_text())
    mapped_ids = {row['group_id'] for row in manifest}
    main_path = run_dir / 'listing-progress.json'
    main = json.loads(main_path.read_text()) if main_path.exists() else {'groups': {}}
    paused = [gid for gid, group in main.get('groups', {}).items() if group.get('waiting_for_owner')]
    if paused:
        raise ValueError(f'Mapped listing queue is paused at {paused[0]}; resume it before collecting review pools')
    incomplete = sorted(gid for gid in mapped_ids if not main.get('groups', {}).get(gid, {}).get('complete'))
    if incomplete:
        raise ValueError(f'Mapped listing queue is not complete yet ({len(incomplete)} route groups remain)')

    state_path = run_dir / 'shared-listings-progress.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {'sources': {}}
    normalize_existing_sources(state)
    for row in queue:
        digest = hashlib.sha256(row['url'].encode()).hexdigest()[:16]
        source = state['sources'].setdefault(row['url'], {
            'source_id': digest,
            'url': row['url'],
            'name': row.get('name', ''),
            'related_group_ids': row['group_ids'],
            'state': 'pending',
            'pending': [row['url']],
            'pages': {},
            'products': {},
        })
        if source['source_id'] != digest:
            raise ValueError(f'Source identity mismatch for {row["url"]}')
        source['name'] = row.get('name', source.get('name', ''))
        source['related_group_ids'] = sorted(set(source.get('related_group_ids', [])) | set(row['group_ids']))

    cache = page_cache(run_dir, main, state)
    write_json(state_path, state)
    snapshot(run_dir, state)
    pages_fetched = 0
    pages_reused = 0
    for row in queue:
        source = state['sources'][row['url']]
        while source['pending']:
            url = source['pending'][0]
            confirmed_localized_page = False
            if url in source['pages']:
                source['pending'].pop(0)
                continue
            if url in cache:
                result = read_result(cache[url])
                evidence = cache[url]
                pages_reused += 1
            else:
                if pages_fetched >= max_pages:
                    break
                if source.get('waiting_for_owner'):
                    if not confirm:
                        write_report(run_dir, state, pages_fetched, pages_reused, 'waiting_for_owner')
                        return {'state': 'waiting_for_owner', 'url': url, 'session_id': session_id}
                    if source['waiting_for_owner'] != session_id:
                        raise ValueError('Resume requires the same browser session id')
                    result = call('POST', '/catalogue-listing/confirm', {'url': url, 'session_id': session_id})
                    confirm = False
                    confirmed_localized_page = canonical_listing_url(url) != url
                else:
                    result = call('POST', '/catalogue-listing', {'url': url, 'session_id': session_id})
                    confirmed_localized_page = False
                pages_fetched += 1
                evidence = str(evidence_path(run_dir, source['source_id'], url, result,
                                             source['related_group_ids']))
                cache[url] = evidence
                source['last_outcome'] = result.get('outcome')
                source['last_evidence'] = evidence
                if result.get('owner_verification_required'):
                    source['waiting_for_owner'] = session_id
                    source['state'] = 'waiting_for_owner'
                    write_json(state_path, state)
                    snapshot(run_dir, state)
                    write_report(run_dir, state, pages_fetched, pages_reused, 'waiting_for_owner')
                    return {'state': 'waiting_for_owner', 'url': url, 'session_id': session_id,
                            'source_name': source.get('name')}
            outcome = result.get('outcome')
            if outcome not in {'offers', 'empty', 'listing_links'}:
                source['state'] = 'stopped'
                source['last_outcome'] = outcome
                write_json(state_path, state)
                snapshot(run_dir, state)
                write_report(run_dir, state, pages_fetched, pages_reused, 'stopped')
                return {'state': 'stopped', 'url': url, 'outcome': outcome,
                        'source_name': source.get('name')}
            source.pop('waiting_for_owner', None)
            if confirmed_localized_page:
                # Confirmation clears only the owner's current localized tab.
                # Fetch the same filtered listing in English before saving names.
                source['pending'][0] = canonical_listing_url(url)
                source['state'] = 'collecting'
                write_json(state_path, state)
                continue
            source['pages'][url] = evidence
            source['pending'].pop(0)
            source['last_outcome'] = outcome
            source['last_evidence'] = evidence
            for child in result.get('listing_urls', []) + result.get('pagination_urls', []):
                child = canonical_listing_url(child)
                if child not in source['pages'] and child not in source['pending']:
                    source['pending'].append(child)
            for item in result.get('products', []):
                product_url = canonical_product_url(item['url'])
                source['products'][product_url] = {
                    'source_id': source['source_id'],
                    'source_url': source['url'],
                    'source_name': source.get('name', ''),
                    'related_group_ids': source['related_group_ids'],
                    'membership_verified': False,
                    'url': product_url,
                    'name': item.get('name', ''),
                    'evidence_file': evidence,
                }
            source['state'] = 'complete' if not source['pending'] else 'collecting'
            write_json(state_path, state)
            snapshot(run_dir, state)
        if pages_fetched >= max_pages:
            break

    return write_report(run_dir, state, pages_fetched, pages_reused, 'checkpoint')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queue', type=Path, default=RUN / 'shared-listing-review-queue.json')
    parser.add_argument('--session-id', default='ja-recovery-a')
    parser.add_argument('--max-pages', type=int, default=10000)
    parser.add_argument('--confirm', action='store_true', help='Owner manually cleared the paused tab')
    args = parser.parse_args()
    if args.max_pages < 1:
        parser.error('--max-pages must be positive')
    with (RUN / 'listing-collector.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error('Another local listing collector is already running')
        result = collect(json.loads(args.queue.read_text()), RUN, args.session_id,
                         args.max_pages, args.confirm)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
