#!/usr/bin/env python3
"""Collect observed set URLs, following listing/pagination links with durable progress.

This is acquisition evidence, not a verified card-to-catalogue mapping or a writer
for staging. One local browser lane serves every set in manifest priority order.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from local_client import RUN, request


_CARDMARKET_LOCALES = {'en', 'de', 'fr', 'es', 'it', 'pt', 'nl'}


def canonical_listing_url(url: str) -> str:
    """Keep observed listing routes in English while retaining their filters."""
    parts = urlsplit(url)
    path = parts.path.split('/')
    if len(path) > 1 and path[1] in _CARDMARKET_LOCALES:
        path[1] = 'en'
    return urlunsplit((parts.scheme, parts.netloc, '/'.join(path), parts.query, ''))


def canonical_product_url(url: str) -> str:
    """Collapse Cardmarket's translated URLs to the stable English product route."""
    parts = urlsplit(canonical_listing_url(url))
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip('/'), '', ''))


def canonicalize_group_products(group: dict) -> None:
    """Migrate old locale-keyed checkpoints and prefer the English product label."""
    products = {}
    for product in group.get('products', {}).values():
        original_url = product.get('url', '')
        canonical_url = canonical_product_url(original_url)
        candidate = {**product, 'url': canonical_url}
        current = products.get(canonical_url)
        original_locale = urlsplit(original_url).path.split('/')[1:2]
        current_locale = urlsplit(current.get('_source_url', '')).path.split('/')[1:2] if current else []
        if current is None or (original_locale == ['en'] and current_locale != ['en']):
            candidate['_source_url'] = original_url
            products[canonical_url] = candidate
    for product in products.values():
        product.pop('_source_url', None)
    group['products'] = products


def canonicalize_group_pages(group: dict) -> None:
    """Collapse locale aliases in checkpoints without discarding page evidence."""
    pages = {}
    pending = [canonical_listing_url(url) for url in group.get('pending', [])]
    for url, evidence in group.get('pages', {}).items():
        canonical_url = canonical_listing_url(url)
        try:
            evidence_url = json.loads(Path(evidence).read_text()).get('requested_url', url)
        except (OSError, ValueError, TypeError):
            evidence_url = url
        evidence_locale = urlsplit(evidence_url).path.split('/')[1:2]
        if evidence_locale != ['en']:
            # Refetch this canonical route so the saved product labels use English.
            pending.append(canonical_url)
            continue
        pages.setdefault(canonical_url, evidence)
    group['pages'] = pages
    group['pending'] = list(dict.fromkeys(
        url for url in pending if url not in pages
    ))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    os.replace(temporary, path)


def product_snapshot(run_dir: Path, state: dict) -> None:
    products = [{'group_id': gid, **product} for gid, group in state['groups'].items()
                for product in group['products'].values()]
    target = run_dir / 'cardmarket-products.jsonl'
    temporary = target.with_suffix('.jsonl.tmp')
    temporary.write_text(''.join(json.dumps(p, ensure_ascii=False, sort_keys=True) + '\n' for p in products))
    os.replace(temporary, target)


def validate_manifest(manifest: list[dict], registry: list[dict]) -> None:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scraper'))
    from allow import cardmarket_expansion_listing
    allowed = {r['group_id'] for r in registry}
    seen = set()
    for row in manifest:
        gid, url = row['group_id'], row['url']
        if gid not in allowed or gid in seen or not cardmarket_expansion_listing(url):
            raise ValueError(f'Invalid or duplicate group/listing: {gid}')
        if not row.get('source'):
            raise ValueError(f'Observed URL source is required for {gid}')
        seen.add(gid)


def write_report(run_dir: Path, state: dict, registry: list[dict], manifest: list[dict],
                 pages_this_run: int, state_name: str = 'checkpoint') -> dict:
    report_path = run_dir / 'listing-report.json'
    previous = json.loads(report_path.read_text()) if report_path.exists() else {}
    dynamic = {'state', 'pages_this_run', 'groups_listed', 'groups_seeded', 'groups_in_scope',
               'groups_without_observed_url', 'products'}
    report = {key: value for key, value in previous.items() if key not in dynamic}
    seeded = {row['group_id'] for row in manifest}
    report.update({
        'state': state_name,
        'pages_this_run': pages_this_run,
        'groups_listed': sum(bool(group.get('complete')) for group in state['groups'].values()),
        'groups_seeded': len(seeded),
        'groups_in_scope': len(registry),
        'groups_without_observed_url': [group['group_id'] for group in registry
                                        if group['group_id'] not in seeded],
        'products': sum(len(group.get('products', {})) for group in state['groups'].values()),
    })
    write_json(report_path, report)
    return report


def confirm_after_owner_clear(url: str, session_id: str, call, poll_seconds: float) -> dict:
    """Poll the same tab until the owner clears it, then read its catalogue page."""
    payload = {'url': url, 'session_id': session_id}
    while True:
        try:
            return call('POST', '/catalogue-listing/confirm', payload)
        except SystemExit as exc:
            if 'HTTP 409:' not in str(exc) or 'has not cleared to catalogue content' not in str(exc):
                raise
            print('Waiting for manual Cardmarket verification in the same Chrome tab...',
                  file=sys.stderr, flush=True)
            time.sleep(poll_seconds)


def collect(manifest: list[dict], run_dir: Path, session_id: str, max_pages: int,
            confirm: bool = False, wait_for_owner: bool = True, poll_seconds: float = 1.0,
            call=request) -> dict:
    registry = json.loads((run_dir / 'set-registry.json').read_text())
    manifest = [{**row, 'url': canonical_listing_url(row['url'])} for row in manifest]
    validate_manifest(manifest, registry)
    state_path = run_dir / 'listing-progress.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {'groups': {}}
    for group in state['groups'].values():
        if group.get('seed'):
            group['seed'] = canonical_listing_url(group['seed'])
        canonicalize_group_pages(group)
        canonicalize_group_products(group)
    product_snapshot(run_dir, state)
    used = 0
    paused = [gid for gid, group in state['groups'].items() if group.get('waiting_for_owner')]
    if paused:
        if not any(row['group_id'] == paused[0] for row in manifest):
            raise ValueError('Manifest omits the paused group; restore it before resuming')
        manifest = sorted(manifest, key=lambda row: row['group_id'] != paused[0])
    for row in manifest:
        gid, seed = row['group_id'], row['url']
        group = state['groups'].setdefault(gid, {'seed': seed, 'pending': [seed], 'pages': {}, 'products': {}})
        if group['seed'] != seed:
            raise ValueError(f'Seed changed for {gid}; review/reset that group progress explicitly')
        while group['pending']:
            url = group['pending'][0]
            if used >= max_pages:
                break
            if group.get('waiting_for_owner'):
                if group['waiting_for_owner'] != session_id:
                    raise ValueError('Resume requires the same browser session id')
                if not confirm and not wait_for_owner:
                    write_report(run_dir, state, registry, manifest, used, 'waiting_for_owner')
                    return {'state': 'waiting_for_owner', 'group_id': gid, 'url': url, 'session_id': session_id}
                if confirm:
                    try:
                        result = call('POST', '/catalogue-listing/confirm', {'url': url, 'session_id': session_id})
                    except SystemExit as exc:
                        if not wait_for_owner or 'HTTP 409:' not in str(exc) \
                                or 'has not cleared to catalogue content' not in str(exc):
                            raise
                        result = confirm_after_owner_clear(url, session_id, call, poll_seconds)
                else:
                    result = confirm_after_owner_clear(url, session_id, call, poll_seconds)
                confirm = False
            else:
                result = call('POST', '/catalogue-listing', {'url': url, 'session_id': session_id})
            used += 1
            payload = {'group_id': gid, 'requested_url': url, 'source': row['source'],
                       'retrieved_at': datetime.now(timezone.utc).isoformat(), 'result': result}
            data = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
            evidence = run_dir / 'source-pages' / gid / (hashlib.sha256(data).hexdigest()[:20] + '.json')
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_bytes(data)
            outcome = result.get('outcome')
            group['last_outcome'] = outcome
            group['last_evidence'] = str(evidence)
            if result.get('owner_verification_required'):
                group['waiting_for_owner'] = session_id
                if (run_dir / 'jobs.sqlite').exists():
                    from recovery import finish_job
                    finish_job(run_dir, f'{gid}:cardmarket_listing', 'waiting_for_owner',
                               'Manual verification required in the same local Chrome tab', quiet=True)
                write_json(state_path, state)
                write_report(run_dir, state, registry, manifest, used, 'waiting_for_owner')
                if not wait_for_owner:
                    return {'state': 'waiting_for_owner', 'group_id': gid, 'url': url, 'session_id': session_id}
                result = confirm_after_owner_clear(url, session_id, call, poll_seconds)
                payload = {'group_id': gid, 'requested_url': url, 'source': row['source'],
                           'retrieved_at': datetime.now(timezone.utc).isoformat(),
                           'resumed_after_owner_verification': True, 'result': result}
                data = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
                evidence = run_dir / 'source-pages' / gid / (hashlib.sha256(data).hexdigest()[:20] + '.json')
                evidence.write_bytes(data)
                outcome = result.get('outcome')
                group['last_outcome'] = outcome
                group['last_evidence'] = str(evidence)
            if outcome not in {'offers', 'empty', 'listing_links'}:
                write_json(state_path, state)
                write_report(run_dir, state, registry, manifest, used, 'stopped')
                return {'state': 'stopped', 'group_id': gid, 'url': url, 'outcome': outcome}
            group.pop('waiting_for_owner', None)
            group['pages'][url] = str(evidence)
            group['pending'].pop(0)
            for link in result.get('listing_urls', []) + result.get('pagination_urls', []):
                link = canonical_listing_url(link)
                if link not in group['pages'] and link not in group['pending']:
                    group['pending'].append(link)
            for product in result.get('products', []):
                canonical_url = canonical_product_url(product['url'])
                candidate = {**product, 'url': canonical_url, 'evidence_file': str(evidence)}
                current = group['products'].get(canonical_url)
                if current is None or urlsplit(product['url']).path.split('/')[1:2] == ['en']:
                    group['products'][canonical_url] = candidate
            group['complete'] = not group['pending']
            write_json(state_path, state)
            # Snapshot rebuilt from all completed pages; repeated runs cannot duplicate products.
            product_snapshot(run_dir, state)
            if group['complete'] and (run_dir / 'jobs.sqlite').exists():
                from recovery import finish_job
                finish_job(run_dir, f'{gid}:cardmarket_listing', 'complete',
                           'All observed listing pages collected; checklist reconciliation remains separate', quiet=True)
        if used >= max_pages:
            break
    return write_report(run_dir, state, registry, manifest, used)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True, help='JSON array: group_id, url, source')
    parser.add_argument('--session-id', default='ja-recovery-a')
    parser.add_argument('--max-pages', type=int, default=20)
    parser.add_argument('--confirm', action='store_true', help='Owner has manually cleared the paused tab')
    parser.add_argument('--no-wait-for-owner', action='store_true',
                        help='Exit immediately on a challenge instead of waiting for manual clearance')
    parser.add_argument('--owner-poll-seconds', type=float, default=1.0,
                        help='Seconds between checks while waiting for manual clearance')
    args = parser.parse_args()
    if args.max_pages < 1 or args.owner_poll_seconds < 0.5:
        parser.error('--max-pages must be positive and --owner-poll-seconds at least 0.5')
    with (RUN / 'listing-collector.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error('Another local listing collector is already running')
        result = collect(json.loads(args.manifest.read_text()), RUN, args.session_id, args.max_pages,
                         args.confirm, not args.no_wait_for_owner, args.owner_poll_seconds)
    display = {**result}
    if "groups_without_observed_url" in display:
        display["groups_without_observed_url"] = len(display["groups_without_observed_url"])
    print(json.dumps(display, indent=2))


if __name__ == '__main__':
    main()
