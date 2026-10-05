"""Reconcile a repeatable-read cloud export without mutating any source.

Review flags and product ownership are evidence, never automatic approval.
Every card and product receives a durable task, including rows absent from HTML.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re


def digest_file(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def token(value):
    return 'N' if value is None else 'V' + str(value).encode().hex()


def identity_differences(left, right):
    fields = ('language', 'set_id', 'name', 'collector_number',
              'printed_collector_number', 'remote_image_url')
    differences = [k for k in fields if left.get(k) != right.get(k)]
    def variants(row):
        value = row.get('variants_json')
        return json.loads(value) if isinstance(value, str) else value
    if variants(left) != variants(right):
        differences.append('variants_json')
    return differences


def normalized_collector(value):
    """Only pad-normalize a wholly numeric value; never discard identity tokens."""
    value = str(value or '').strip()
    return str(int(value)) if re.fullmatch(r'[0-9]+', value) else value


def numbered_title(title):
    title = re.sub(r'From\s.*$', '', title).strip()
    match = re.fullmatch(r'(.+?)\s*\(([A-Za-z0-9.-]+)\s+([^() ]+)\)', title)
    return dict(name=match[1].strip(), code=match[2], collector=match[3]) if match else None


def local_candidate_check(card, product, registry):
    """An evidence filter, not mapping approval or a claim of live access."""
    reasons = []
    identity = numbered_title(product['name'])
    scope = registry.get(product['expansion'])
    if not scope or scope.get('verification') != 'approved_exact_scope':
        reasons.append('expansion_scope_unapproved')
    elif (scope['language'], scope['set_id']) != (card['language'], card['set_id']):
        reasons.append('language_or_set_conflict')
    if not identity:
        reasons.append('full_collector_identity_unparsed')
    else:
        if identity['name'].casefold() != card['name'].casefold():
            reasons.append('name_conflict')
        if normalized_collector(identity['collector']) != normalized_collector(card['collector_number']):
            reasons.append('collector_conflict')
    if product.get('card_id') not in (None, '', card['id']):
        reasons.append('owner_conflict')
    return reasons


def reconcile(export, published, digital, output):
    output.mkdir(parents=True, exist_ok=False)
    tables = defaultdict(list)
    snapshot = None
    for line in gzip.open(export, 'rt'):
        record = json.loads(line)
        if record['table'] == '_snapshot':
            snapshot = record
        else:
            tables[record['table']].append(record['row'])
    if not snapshot or len(tables['import_manifest']) != 1:
        raise ValueError('Expected one pinned snapshot/import')
    manifest = tables['import_manifest'][0]
    meta = manifest['metadata']
    checks = {}
    for table, contract in meta['digests'].items():
        rows = sorted(tables[table], key=lambda row: str(row[contract['keys'][0]]).encode())
        hashes = [hashlib.md5('|'.join(token(r[c]) for c in contract['columns']).encode()).hexdigest() for r in rows]
        actual = hashlib.md5(''.join(hashes).encode()).hexdigest()
        checks[table] = dict(actual=actual, expected=contract['md5'], passed=actual == contract['md5'])
        if not checks[table]['passed']:
            raise ValueError('Export digest mismatch: ' + table)
    vector_checks = {}
    vectors = defaultdict(dict)
    for row in tables['card_embeddings']:
        raw = base64.b64decode(row['embedding']['base64'])
        actual = hashlib.sha256(raw[4:]).hexdigest()
        if len(raw) != 1540 or raw[:4] != b'\x01\x80\x00\x00' or actual != row['source_vector_sha256']:
            raise ValueError('Vector checksum/dimension mismatch')
        if row['card_id'] in vectors[row['mode']]:
            raise ValueError('Duplicate vector ID')
        vectors[row['mode']][row['card_id']] = row['source_vector_sha256']
    for mode, rows in vectors.items():
        contract = meta['vectors'][mode]
        actual = hashlib.md5(''.join(rows[k] for k in sorted(rows, key=lambda k: k.encode())).encode()).hexdigest()
        passed = actual == contract['aggregate_md5'] and len(rows) == contract['count']
        vector_checks[mode] = dict(count=len(rows), actual=actual, passed=passed)
        if not passed:
            raise ValueError('Vector aggregate mismatch: ' + mode)
    cards = {c['id']: c for c in tables['cards']}
    products = {p['url']: p for p in tables['cardmarket_products']}
    if len(cards) != len(tables['cards']) or len(products) != len(tables['cardmarket_products']):
        raise ValueError('Duplicate card/product key')
    orphan_vectors = set().union(*[set(v) for v in vectors.values()]) - cards.keys()
    orphan_owners = {p['card_id'] for p in products.values() if p['card_id']} - cards.keys()
    if orphan_vectors or orphan_owners:
        raise ValueError('Orphan identity')
    helpers = {r['card_id']: r['metadata'] for r in tables['cardmarket_url_helpers']}
    reviews = {r['url']: r for r in tables['cardmarket_review']}
    html = json.loads(Path(published).read_text())
    html_rows = {r['url']: r for r in html['rows']}
    references = {r['source_key']: r['metadata'] for r in tables['reference_metadata']}
    crawls = {r['source_key']: r['metadata'] for r in tables['source_records'] if r['source_table'] == 'cardmarket_expansion_crawls'}
    digital_data = json.loads(Path(digital).read_text())
    if digital_data['id'] != 'tcgp':
        raise ValueError('Invalid digital-series evidence')
    digital_sets = {s['id'] for s in digital_data['sets']}
    art = defaultdict(list)
    owned = defaultdict(list)
    for row in tables['artwork_embeddings']:
        art[row['card_id']].append(dict(profile=row['profile'], source_vector_sha256=row['source_vector_sha256'], metadata=row['metadata']))
    for p in products.values():
        if p['card_id']:
            owned[p['card_id']].append(p)
    conflicts, aliases, registry_candidates = [], [], defaultdict(Counter)
    for c in cards.values():
        p = products.get(c['cardmarket_url'])
        if p and p['card_id'] and p['card_id'] != c['id']:
            owner = cards[p['card_id']]
            prefix = c['language'] == owner['language'] == 'en' and c['id'].removeprefix('en:') == owner['id'].removeprefix('en:')
            differences = identity_differences(c, owner)
            record = dict(card=c, product=p, owner=owner, identity_differences=differences,
                          decision='pending_exact_print_evidence', published=False)
            (aliases if prefix else conflicts).append(record)
        for p in owned[c['id']]:
            registry_candidates[p['expansion']][(c['language'], c['set_id'])] += 1
    conflict_ids = {r['card']['id'] for r in conflicts}
    alias_ids = {r['card']['id'] for r in aliases}
    tasks, pending = [], []
    coverage, queues = defaultdict(Counter), defaultdict(Counter)
    for c in sorted(cards.values(), key=lambda c: c['id']):
        cid = c['id']
        scope = 'digital' if c['language'] == 'en' and c['set_id'] in digital_sets else 'physical_catalogue'
        capabilities = dict(primary_url=bool(c['cardmarket_url']), image_marked_present=bool(c['has_image']),
                            source_bytes_rechecked=False, pad=cid in vectors['pad'], square=cid in vectors['square'],
                            artwork_profiles=[r['profile'] for r in art[cid]])
        issues = []
        if cid in conflict_ids:
            issues.append('identity_owner_conflict')
        if cid in alias_ids:
            issues.append('alias_print_equivalence_unverified')
        if not capabilities['image_marked_present']:
            issues.append('exact_original_image_missing')
        if not capabilities['primary_url']:
            issues.append('exact_cardmarket_identity_url_missing')
        if capabilities['primary_url'] and c['cardmarket_url'] not in products:
            issues.append('primary_url_absent_from_products')
        if capabilities['primary_url'] and helpers.get(cid, {}).get('cardmarket_url') != c['cardmarket_url']:
            issues.append('primary_helper_mirror_disagreement')
        if capabilities['image_marked_present'] and not capabilities['square']:
            issues.append('square_vector_missing')
        if capabilities['image_marked_present'] and not capabilities['pad']:
            issues.append('pad_vector_missing')
        linked_reviews = [reviews.get(p['url']) for p in owned[cid] if p['url'] in reviews]
        if any(r['recognition_review_pending'] for r in linked_reviews):
            issues.append('recognition_printing_warning')
        queue = 'excluded_digital' if scope == 'digital' else (issues[0] if issues else 'existing_coverage_revalidation')
        task = dict(task_id='card:'+cid, card=c, scope=scope, aliases=[], queue=queue, issues=issues,
                    capabilities=capabilities, products=owned[cid], helper=helpers.get(cid),
                    review=linked_reviews, published_reference=html['cards'].get(cid),
                    reference_metadata=references.get('review-card:'+cid), artwork=art[cid],
                    verification='not_newly_approved', parent_import=snapshot['import_id'])
        tasks.append(task)
        if issues and scope != 'digital':
            pending.append(task)
        language = c['language']
        queues[language][queue] += 1
        counts = coverage[language]
        counts['rows'] += 1
        if scope != 'digital':
            counts['physical_rows'] += 1
            for key in ('primary_url', 'image_marked_present', 'pad', 'square'):
                counts[key] += capabilities[key]
            counts['artwork_cards'] += bool(art[cid])
            counts['missing_images'] += not capabilities['image_marked_present']
            counts['missing_urls'] += not capabilities['primary_url']
    for url, p in sorted(products.items()):
        review = reviews.get(url)
        tasks.append(dict(task_id='product:'+url, queue='owned_product_revalidation' if p['card_id'] else 'unmatched_product_exact_identity',
                          product=p, review=review, published_review=html_rows.get(url),
                          crawl=crawls.get(p['expansion']), verification='not_newly_approved',
                          url_evidence_state='listed_in_saved_expansion' if p['expansion'] in crawls else 'stored_product_only',
                          live_access_verified=False))
    def write(name, records):
        with (output/name).open('w') as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False)+'\n')
    write('inventory.jsonl', tasks)
    write('pending-cards.jsonl', pending)
    write('owner-conflicts.jsonl', conflicts)
    write('alias-candidates.jsonl', aliases)
    write('registry-candidates.jsonl', [dict(expansion=e, candidates=[dict(language=l,set_id=s,owned_products=n) for (l,s),n in c.items()], verification='unapproved') for e,c in sorted(registry_candidates.items())])
    report = dict(snapshot=snapshot, table_counts={k:len(v) for k,v in tables.items()}, coverage=coverage,
                  disjoint_card_queues=queues, owner_conflicts=len(conflicts), prefix_alias_candidates=len(aliases),
                  alias_metadata_agree=sum(not r['identity_differences'] for r in aliases),
                  table_digest_checks=checks, vector_checks=vector_checks,
                  export_sha256=digest_file(export), published_review_sha256=digest_file(published),
                  published_rows=len(html['rows']), unmatched_products=sum(not p['matched'] for p in products.values()),
                  manifest_count_discrepancies={k:dict(expected=meta['counts'][k],actual=len(v)) for k,v in tables.items() if k in meta['counts'] and meta['counts'][k]!=len(v)},
                  newly_completed=0, activated=False)
    (output/'report.json').write_text(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', type=Path, required=True)
    parser.add_argument('--published', type=Path, required=True)
    parser.add_argument('--digital-series', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    print(json.dumps(reconcile(a.export,a.published,a.digital_series,a.output), indent=2))


if __name__ == '__main__':
    main()
