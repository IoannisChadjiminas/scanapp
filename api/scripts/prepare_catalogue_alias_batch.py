"""Prepare evidence-backed alias-primary repairs. No database/publication writes.

Reuse only an already verified primary whose complete imported identity,
variants and source bytes match. Never choose a V-number or transfer an owner.
"""
import argparse
from collections import defaultdict
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from catalogue_completion_inventory import identity_differences, normalized_collector, numbered_title, token, digest_file


def select_aliases(cards, products, hashes, helpers):
    accepted, held = [], []
    for card in sorted(cards.values(), key=lambda r:r['id']):
        if card['language'] != 'en' or not card['id'].startswith('en:') or card['cardmarket_url']:
            continue
        legacy = cards.get(card['id'][3:])
        if not legacy or not legacy['cardmarket_url']:
            continue
        reasons = identity_differences(card, legacy)
        product = products.get(legacy['cardmarket_url'])
        title = numbered_title(product['name']) if product else None
        if not legacy['cardmarket_verified']:
            reasons.append('legacy_mapping_unverified')
        if not product or not product['matched'] or product['card_id'] not in (card['id'],legacy['id']):
            reasons.append('product_owner_or_match_conflict')
        if not title or title['name'].casefold() != card['name'].casefold():
            reasons.append('listing_name_conflict')
        if not title or normalized_collector(title['collector']) != normalized_collector(card['collector_number']):
            reasons.append('listing_collector_conflict')
        if title and product:
            suffix = re.search(re.escape(title['code'])+r'([0-9A-Za-z/]+)$', product['url'], re.I)
            if not suffix or normalized_collector(suffix[1]) != normalized_collector(title['collector']):
                reasons.append('url_collector_code_unconfirmed')
        first, second = hashes.get(card['id'],{}), hashes.get(legacy['id'],{})
        if not first.get('sha256') or first.get('sha256') != second.get('sha256'):
            reasons.append('source_bytes_differ_or_unavailable')
        if helpers.get(legacy['id'],{}).get('cardmarket_url') != legacy['cardmarket_url']:
            reasons.append('legacy_primary_helper_disagreement')
        evidence = dict(card_id=card['id'], alias_id=legacy['id'], card_before=card,
                        legacy_before=legacy, helper_before=helpers.get(card['id']),
                        product_before=product, source_hash=first.get('sha256'),
                        source_paths=[first.get('path'),second.get('path')],
                        primary_selection='reuse_verified_alias_primary',
                        live_access_verified=False, finish=None, finish_verified=False,
                        published=False, reasons=reasons)
        if reasons:
            held.append(evidence)
        else:
            accepted.append(evidence)
    return accepted, held


def digest_rows(rows, contract):
    ordered = sorted(rows, key=lambda r:str(r[contract['keys'][0]]).encode())
    hashes = [hashlib.md5('|'.join(token(r[c]) for c in contract['columns']).encode()).hexdigest() for r in ordered]
    return hashlib.md5(''.join(hashes).encode()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--export',type=Path,required=True)
    p.add_argument('--source-hashes',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); a.output.mkdir(parents=True,exist_ok=False)
    tables=defaultdict(list)
    for line in gzip.open(a.export,'rt'):
        record=json.loads(line)
        if 'row' in record:tables[record['table']].append(record['row'])
    cards={r['id']:r for r in tables['cards']}
    products={r['url']:r for r in tables['cardmarket_products']}
    helpers={r['card_id']:r['metadata'] for r in tables['cardmarket_url_helpers']}
    hashes={r['card_id']:r for r in map(json.loads,a.source_hashes.read_text().splitlines())}
    accepted,held=select_aliases(cards,products,hashes,helpers)
    for filename,records in [('selection.jsonl',accepted),('manual-holds.jsonl',held)]:
        (a.output/filename).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
    parent=tables['import_manifest'][0]
    groups=[accepted[:50],accepted[50:300],accepted[300:]]
    reports=[]
    for number,group in enumerate(groups,1):
        if not group:continue
        directory=a.output/f'batch-{number:02d}';directory.mkdir()
        before=deepcopy(list(cards.values()))
        ledgers=[]
        for evidence in group:
            card=cards[evidence['card_id']];legacy=cards[evidence['alias_id']]
            fields=('cardmarket_url','cardmarket_id','cardmarket_verified','cardmarket_provenance','cardmarket_verified_at')
            changes={k:legacy[k] for k in fields}
            changes['cardmarket_provenance']='verified-identical-source-alias:'+legacy['id']
            ledgers.append(dict(card_id=card['id'], before={k:card[k] for k in fields}, after=changes,
                                helper_before=helpers.get(card['id']), alias_id=legacy['id'],
                                source_sha256=evidence['source_hash']))
            card.update(changes)
            helpers[card['id']]=dict(card_id=card['id'],cardmarket_url=card['cardmarket_url'],
                cardmarket_id=card['cardmarket_id'],provenance=card['cardmarket_provenance'],
                verified_at=card['cardmarket_verified_at'])
        contract=parent['metadata']['digests']['cards']
        report=dict(batch_id=directory.name,records=len(group),parent_cards_md5=digest_rows(before,contract),
                    candidate_cards_md5=digest_rows(list(cards.values()),contract),
                    existing_products_unchanged=True,existing_vectors_unchanged=True,
                    status='prepared_not_published', live_url_checks=0,
                    limitation='Alias mapping repair cohort; this does not satisfy the varied printing/reference pilot gate.')
        (directory/'correction-ledger.json').write_text(json.dumps(ledgers,ensure_ascii=False,indent=2))
        (directory/'report.json').write_text(json.dumps(report,indent=2));reports.append(report)
    candidate=sqlite3.connect(a.output/'candidate.sqlite')
    for table,rows in [('cards',list(cards.values())),('cardmarket_products',list(products.values())),
                       ('cardmarket_url_helpers',[dict(card_id=k,metadata=v) for k,v in helpers.items()])]:
        columns=list(rows[0]);candidate.execute(f'CREATE TABLE {table} ({",".join(columns)})')
        candidate.executemany(f'INSERT INTO {table} VALUES ({",".join("?" for _ in columns)})',
            [tuple(json.dumps(r[k],ensure_ascii=False) if isinstance(r[k],(dict,list)) else r[k] for k in columns) for r in rows])
    candidate.commit();candidate.close()
    report=dict(accepted=len(accepted),held=len(held),batches=reports,export_sha256=digest_file(a.export),
                hash_evidence_sha256=digest_file(a.source_hashes),parent_import=parent['import_id'],
                activated=False,published=False,writer_blocker='PlanetScale connector HTTP 403; runtime role read-only')
    (a.output/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))


if __name__=='__main__':main()
