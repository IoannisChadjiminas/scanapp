"""Compute an offline candidate's actual coherent counts/digests/vector manifests.

This prepares a loading import. It cannot approve sources, activate a release,
write cloud data, or turn an unresolved URL into a completed mapping.
"""
import argparse
import base64
from collections import Counter, defaultdict
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import numpy as np


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table_digest(rows, contract):
    keys = contract['keys']
    order = sorted(rows, key=lambda r: tuple(str(r[k]).encode() for k in keys))
    tokens = lambda value: 'N' if value is None else 'V' + str(value).encode().hex()
    hashes = [hashlib.md5('|'.join(tokens(r[c]) for c in contract['columns']).encode()).hexdigest()
              for r in order]
    return hashlib.md5(''.join(hashes).encode()).hexdigest()


def vector_hashes(matrix, ids, parent):
    if matrix.shape != (len(ids), 384) or len(set(ids)) != len(ids):
        raise ValueError('Invalid shape or duplicate vector ID')
    if not np.isfinite(matrix).all() or not np.allclose(np.linalg.norm(matrix, axis=1), 1, atol=1e-4):
        raise ValueError('Non-finite or non-normalized vector')
    hashes = {str(cid): hashlib.sha256(np.asarray(v, dtype='>f4').tobytes()).hexdigest()
              for cid, v in zip(ids, matrix)}
    if any(hashes.get(cid) != digest for cid, digest in parent.items()):
        raise ValueError('Existing cloud vector bytes changed or disappeared')
    return hashes, hashlib.md5(''.join(hashes[c] for c in sorted(hashes, key=lambda c:c.encode())).encode()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); r = a.run_root
    candidate = r / 'skyridge-pilot-v1'
    checkpoint=json.loads((r/'run.json').read_text())
    if sha(r/'live-export.jsonl.gz')!=checkpoint['checkpoint_hashes']['live-export.jsonl.gz']:
        raise ValueError('Immutable parent export changed')
    checks = json.loads((r/'skyridge-regression-v1/regression-complete.summary.json').read_text())
    if not checks['identity_regression_passed'] or checks['lost_correct_matches'] or checks['status_changes']:
        raise ValueError('Frozen regression gate failed')
    tables = defaultdict(list); parent_vectors = defaultdict(dict)
    for line in gzip.open(r/'live-export.jsonl.gz', 'rt'):
        record = json.loads(line)
        if record['table'] == '_snapshot':continue
        row = record['row']; table = record['table']; tables[table].append(row)
        if table == 'card_embeddings':
            raw = base64.b64decode(row['embedding']['base64'])
            if raw[:4] != b'\x01\x80\x00\x00' or len(raw) != 1540:
                raise ValueError('Invalid cloud vector encoding')
            digest = hashlib.sha256(raw[4:]).hexdigest()
            if digest != row['source_vector_sha256']:raise ValueError('Cloud vector hash mismatch')
            parent_vectors[row['mode']][row['card_id']] = digest
    if len(tables['import_manifest'])!=1:raise ValueError('Expected one parent import')
    parent = tables['import_manifest'][0]; metadata = deepcopy(parent['metadata'])
    if table_digest(tables['cards'],metadata['digests']['cards'])!=metadata['digests']['cards']['md5']:
        raise ValueError('Card parent digest mismatch')
    db = sqlite3.connect((candidate/'catalog.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    cards = [dict(x) for x in db.execute('SELECT * FROM cards')];db.close()
    if {x['id'] for x in cards} != {x['id'] for x in tables['cards']}:
        raise ValueError('Unexpected catalogue identity addition/removal')
    metadata['digests']['cards']['md5'] = table_digest(cards, metadata['digests']['cards'])
    if table_digest(tables['cardmarket_products'], metadata['digests']['cardmarket_products']) != metadata['digests']['cardmarket_products']['md5']:
        raise ValueError('Product parent digest mismatch')
    a.output.mkdir(parents=True,exist_ok=False)
    pad = np.load(candidate/'vectors/embeddings.npy',allow_pickle=False)
    pad_ids = np.load(candidate/'vectors/embedding_card_ids.npy',allow_pickle=False)
    square = np.concatenate([np.load(r/'square-repair-v1/embeddings.npy',allow_pickle=False),
                             np.load(candidate/'new-square-vectors.npy',allow_pickle=False)])
    square_ids = np.asarray(np.load(r/'square-repair-v1/embedding_card_ids.npy',allow_pickle=False).tolist()
                            +np.load(candidate/'new-source-card-ids.npy',allow_pickle=False).tolist())
    np.save(a.output/'square-embeddings.npy',square);np.save(a.output/'square-card-ids.npy',square_ids)
    mode_reports={}
    for mode,matrix,ids in [('pad',pad,pad_ids),('square',square,square_ids)]:
        hashes,aggregate=vector_hashes(matrix,ids,parent_vectors[mode])
        if not set(hashes)<={c['id'] for c in cards}:raise ValueError('Orphan vectors')
        path = candidate/'vectors' if mode=='pad' else a.output
        array_path = path/('embeddings.npy' if mode=='pad' else 'square-embeddings.npy')
        ids_path = path/('embedding_card_ids.npy' if mode=='pad' else 'square-card-ids.npy')
        manifest=deepcopy(json.loads((candidate/'vectors/manifest.json').read_text()))
        manifest.update(preprocess_config=mode,indexed_count=len(ids),indexed_ids=ids.tolist(),
                        missing_images=len(cards)-len(ids),embeddings_sha256=sha(array_path),ids_sha256=sha(ids_path))
        (a.output/f'{mode}-manifest.json').write_text(json.dumps(manifest,indent=2))
        metadata['vectors'][mode].update(count=len(ids),snapshot='PS-CATALOGUE-EN-001-20261004-'+mode,aggregate_md5=aggregate)
        mode_reports[mode]=dict(count=len(ids),new_rows=len(ids)-len(parent_vectors[mode]),
                               parent_rows_preserved=len(parent_vectors[mode]),aggregate_md5=aggregate)
    art=np.load(candidate/'artwork/embeddings.npy',allow_pickle=False)
    records=json.loads((candidate/'artwork/records.json').read_text())
    if len(art)!=len(records):raise ValueError('Artwork cardinality mismatch')
    if art.shape!=(len(records),384) or not np.isfinite(art).all() or not np.allclose(np.linalg.norm(art,axis=1),1,atol=1e-4):
        raise ValueError('Artwork invalid vector')
    for old in tables['artwork_embeddings']:
        index=old['row_index'];record=records[index]
        if (record['card_id'],record['profile'])!=(old['card_id'],old['profile']) or hashlib.sha256(art[index].astype('>f4').tobytes()).hexdigest()!=old['source_vector_sha256']:
            raise ValueError('Cloud artwork changed')
    keys={(x['card_id'],x['profile']) for x in records}
    if len(keys)!=len(records) or not {k[0] for k in keys}<={c['id'] for c in cards}:
        raise ValueError('Artwork duplicate or orphan')
    art_hashes=[hashlib.sha256(v.astype('>f4').tobytes()).hexdigest() for v in art]
    metadata['artwork'].update(count=len(records),cards=len({x['card_id'] for x in records}),
        aggregate_md5=hashlib.md5(''.join(art_hashes).encode()).hexdigest(),
        embeddings_sha256=sha(candidate/'artwork/embeddings.npy'),
        records_sha256=sha(candidate/'artwork/records.json'),manifest_sha256=sha(candidate/'artwork/manifest.json'))
    counts={t:len(rows) for t,rows in tables.items() if t!='import_manifest'}
    aliases=[json.loads(line) for line in (r/'alias-candidate-v2/selection.jsonl').read_text().splitlines()]
    existing_helpers={x['card_id'] for x in tables['cardmarket_url_helpers']}
    counts['cardmarket_url_helpers']+=sum(x['card_id'] not in existing_helpers for x in aliases)
    sources=json.loads((r/'skyridge-pilot-selection.json').read_text())['records']
    counts['card_embeddings']=len(pad)+len(square);counts['artwork_embeddings']=len(art)
    # source_records is constrained to Cardmarket crawls/snapshots. Store
    # independent reference provenance in reference_metadata instead.
    counts['reference_metadata']+=len(sources)
    metadata.update(counts=counts,languages=dict(Counter(c['language'] for c in cards)),
        target=dict(organization='pokesingle',database='pokesingle-db',branch='main',schema='pokesingle_completion_20261004'),
        change_id='PS-CATALOGUE-EN-001-20261004',parent_import_id=parent['import_id'],
        parent_schema='pokesingle_recovery_20261003',app_cutover=False,
        activation_allowed=False,source_public_display_policy_pending=True,
        reference_source_evidence_storage='reference_metadata')
    (a.output/'loading-metadata.json').write_text(json.dumps(metadata,indent=2))
    report=dict(actual_candidate_cards=len(cards),expected_post_overlay_counts=counts,
        modes=mode_reports,artwork_parent_rows_preserved=len(tables['artwork_embeddings']),
        artwork_new_rows=len(art)-len(tables['artwork_embeddings']),
        metadata_sha256=sha(a.output/'loading-metadata.json'),
        status='prepared_loading_import_only',published=False,activated=False,
        outstanding=['Exact DDL approval','Cloud seed/overlay/readback','Public source display policy',
                     'Coherent startup and rollback validation','Staging candidate panel','Activated-import HTML'])
    (a.output/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))


if __name__=='__main__':main()
