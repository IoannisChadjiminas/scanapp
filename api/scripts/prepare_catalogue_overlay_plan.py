"""Prepare guarded SQL for an isolated loading catalogue; never connect or activate.

All before values are retained in the append-only review plan. A caller must
check returned counts and record commits; an ambiguous response is not retryable
until its exact keys have been read back. Publication gates remain separate.
"""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import numpy as np

from prepare_catalogue_seed_plan import identifier, literal


def value_sql(value, kind='text'):
    if value is None:
        return 'NULL::' + kind
    if kind == 'jsonb':
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        return "convert_from(decode('" + raw.hex() + "','hex'),'UTF8')::jsonb"
    if kind in ('integer', 'bigint'):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError('Expected integral value')
        return str(value) + '::' + kind
    if kind != 'text' or not isinstance(value, str):
        raise ValueError('Unsupported SQL value')
    # Hex encoding avoids SQL escapes and preserves arbitrary UTF-8 text.
    return "convert_from(decode('" + value.encode().hex() + "','hex'),'UTF8')"


def vector_sql(vector):
    vector = np.asarray(vector, dtype=np.float32)
    if vector.shape != (384,) or not np.isfinite(vector).all():
        raise ValueError('Invalid vector')
    if not np.isclose(np.linalg.norm(vector), 1, atol=1e-4):
        raise ValueError('Non-normalized vector')
    tokens = [format(float(v), '.9g') for v in vector]
    if not np.array_equal(np.asarray(tokens, dtype=np.float32), vector):
        raise ValueError('Vector text roundtrip failed')
    return "'[" + ','.join(tokens) + "]'::vector"


def guard(schema, import_id):
    return ('EXISTS (SELECT 1 FROM ' + identifier(schema) + '.import_manifest WHERE import_id='
            + literal(import_id) + " AND status='loading')")


def insert_sql(schema, import_id, table, rows, types):
    if not rows:
        raise ValueError('Empty insert')
    cols = list(rows[0])
    if any(list(r) != cols for r in rows):
        raise ValueError('Column drift')
    names = ','.join(identifier(c) for c in cols)
    values = ','.join('(' + ','.join(vector_sql(r[c]) if types[c] == 'vector'
                                    else value_sql(r[c], types[c]) for c in cols) + ')' for r in rows)
    return ('WITH changed AS (INSERT INTO ' + identifier(schema) + '.' + identifier(table)
            + ' (' + names + ') SELECT * FROM (VALUES ' + values + ') AS v(' + names
            + ') WHERE ' + guard(schema, import_id) + ' RETURNING 1)'
            + ' SELECT count(*) AS rows_changed FROM changed;')


def update_sql(schema, import_id, table, changes, keys, types):
    if not changes:
        raise ValueError('Empty update')
    cols = list(changes[0]['before'])
    if any(set(x['before']) != set(cols) or set(x['after']) != set(cols) for x in changes):
        raise ValueError('Update column drift')
    if any(any(x['before'][k] != x['after'][k] for k in keys) for x in changes):
        raise ValueError('Key mutation')
    values = ','.join('(' + ','.join(value_sql(x[side][c], types[c])
                                    for side in ('before', 'after') for c in cols) + ')'
                      for x in changes)
    names = ','.join(identifier(side + '_' + c) for side in ('before', 'after') for c in cols)
    assignments = ','.join(identifier(c) + '=v.' + identifier('after_' + c) for c in cols if c not in keys)
    checks = ' AND '.join('t.' + identifier(c) + ' IS NOT DISTINCT FROM v.'
                          + identifier('before_' + c) for c in cols)
    return ('WITH changed AS (UPDATE ' + identifier(schema) + '.' + identifier(table)
            + ' AS t SET ' + assignments + ' FROM (VALUES ' + values + ') AS v(' + names
            + ') WHERE ' + checks + ' AND ' + guard(schema, import_id) + ' RETURNING 1)'
            + ' SELECT count(*) AS rows_changed FROM changed;')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); root = args.run_root
    checkpoint = json.loads((root / 'run.json').read_text())
    for relative in ('alias-candidate-v2/selection.jsonl', 'skyridge-pilot-selection.json',
                     'coherent-candidate-v2/loading-metadata.json',
                     'coherent-candidate-v2/pad-manifest.json', 'coherent-candidate-v2/square-manifest.json',
                     'skyridge-regression-v1/regression-complete.summary.json'):
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != checkpoint['checkpoint_hashes'][relative]:
            raise ValueError('Reviewed dependency changed: ' + relative)
    regression = json.loads((root / 'skyridge-regression-v1/regression-complete.summary.json').read_text())
    if not regression['identity_regression_passed'] or regression['lost_correct_matches'] or regression['status_changes']:
        raise ValueError('Source regression gate failed')
    export = root / 'live-export.jsonl.gz'
    if hashlib.sha256(export.read_bytes()).hexdigest() != checkpoint['checkpoint_hashes']['live-export.jsonl.gz']:
        raise ValueError('Immutable parent export changed')
    plan = json.loads((root / 'publication-plan-v1/plan.json').read_text())
    schema, import_id = plan['candidate_schema'], plan['candidate_import']
    if schema == plan['parent_schema']:
        raise ValueError('Active parent cannot be target')
    tables = defaultdict(list)
    for line in gzip.open(export, 'rt'):
        record = json.loads(line)
        if record['table'] != '_snapshot':
            tables[record['table']].append(record['row'])
    parent_cards = {x['id']: x for x in tables['cards']}
    db = sqlite3.connect((root / 'skyridge-pilot-v1/catalog.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    cards = {x['id']: dict(x) for x in db.execute('SELECT * FROM cards')}; db.close()
    if cards.keys() != parent_cards.keys():
        raise ValueError('Catalogue identity drift')
    aliases = [json.loads(l) for l in (root / 'alias-candidate-v2/selection.jsonl').read_text().splitlines()]
    sources = json.loads((root / 'skyridge-pilot-selection.json').read_text())['records']
    allowed = {x['card_id'] for x in aliases} | {x['id'] for x in sources}
    changes = [{'before': parent_cards[c], 'after': cards[c]} for c in sorted(cards) if cards[c] != parent_cards[c]]
    if {x['before']['id'] for x in changes} != allowed:
        raise ValueError('Changed cards differ from reviewed cohorts')
    corrections = [item for file in sorted((root / 'alias-candidate-v2').glob('batch-*/correction-ledger.json'))
                   for item in json.loads(file.read_text())]
    corrections += json.loads((root / 'skyridge-pilot-v1/correction-ledger.json').read_text())
    if len(corrections) != len(changes):
        raise ValueError('Correction ledger cardinality drift')
    for correction in corrections:
        cid = correction['card_id']
        if any(parent_cards[cid][k] != v for k, v in correction['before'].items()):
            raise ValueError('Correction before evidence drift')
        if any(cards[cid][k] != v for k, v in correction['after'].items()):
            raise ValueError('Correction after evidence drift')
    for x in changes:
        changed = {c for c in x['before'] if x['before'][c] != x['after'][c]}
        cid = x['before']['id']
        permitted = ({'cardmarket_id', 'cardmarket_url', 'cardmarket_verified', 'cardmarket_provenance', 'cardmarket_verified_at'}
                     if cid in {a['card_id'] for a in aliases}
                     else {'image_path', 'has_image', 'remote_image_url', 'printed_collector_number'})
        if not changed <= permitted:
            raise ValueError('Unexpected card identity/variant change')
    batches = []
    def add(table, operation, rows, keys, types, size=50):
        for offset in range(0, len(rows), size):
            group = rows[offset:offset + size]
            sql = (insert_sql(schema, import_id, table, group, types) if operation == 'insert'
                   else update_sql(schema, import_id, table, group, keys, types))
            # Embeddings retain hashes; binary arrays live in immutable artifacts.
            ledger = [{k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in r.items()} for r in group]
            batches.append(dict(batch_id=f'overlay-{len(batches)+1:03}', table=table,
                                operation=operation, expected_rows=len(group), ledger=ledger,
                                sql=sql, sql_sha256=hashlib.sha256(sql.encode()).hexdigest()))
    card_types = {c: ('bigint' if c == 'cardmarket_id' else 'integer' if c in ('has_image', 'cardmarket_verified') else 'text') for c in next(iter(cards.values()))}
    add('cards', 'update', changes, ['id'], card_types)
    adb = sqlite3.connect((root / 'alias-candidate-v2/candidate.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
    adb.row_factory = sqlite3.Row
    helper_map = {x['card_id']: json.loads(x['metadata']) for x in adb.execute('SELECT * FROM cardmarket_url_helpers')}; adb.close()
    old_helpers = {x['card_id'] for x in tables['cardmarket_url_helpers']}
    if any(x['card_id'] in old_helpers for x in aliases):
        raise ValueError('Expected additive alias helpers')
    helpers = [dict(card_id=x['card_id'], metadata=helper_map[x['card_id']]) for x in aliases]
    add('cardmarket_url_helpers', 'insert', helpers, [], dict(card_id='text', metadata='jsonb'))
    coherent = root / 'coherent-candidate-v2'
    metadata = json.loads((coherent / 'loading-metadata.json').read_text())
    old_vectors = {(x['card_id'], x['mode']): x for x in tables['card_embeddings']}
    additions, snapshot_changes = [], []
    for mode, matrix_file, ids_file in [
        ('pad', root / 'skyridge-pilot-v1/vectors/embeddings.npy', root / 'skyridge-pilot-v1/vectors/embedding_card_ids.npy'),
        ('square', coherent / 'square-embeddings.npy', coherent / 'square-card-ids.npy')]:
        matrix = np.load(matrix_file, allow_pickle=False); ids = np.load(ids_file, allow_pickle=False)
        mode_manifest = json.loads((coherent / (mode + '-manifest.json')).read_text())
        if (hashlib.sha256(matrix_file.read_bytes()).hexdigest() != mode_manifest['embeddings_sha256']
                or hashlib.sha256(ids_file.read_bytes()).hexdigest() != mode_manifest['ids_sha256']):
            raise ValueError('Coherent mode artifact changed')
        if len(set(ids.tolist())) != len(ids) or matrix.shape != (len(ids), 384):
            raise ValueError('Invalid vector cardinality')
        for cid, vector in zip(ids.tolist(), matrix):
            digest = hashlib.sha256(vector.astype('>f4').tobytes()).hexdigest()
            old = old_vectors.get((cid, mode)); snapshot = metadata['vectors'][mode]['snapshot']
            if old:
                if digest != old['source_vector_sha256']:
                    raise ValueError('Existing vector changed')
                before = {k: old[k] for k in ('card_id', 'mode', 'snapshot_id', 'source_vector_sha256')}
                snapshot_changes.append(dict(before=before, after=dict(before, snapshot_id=snapshot)))
            else:
                if cid not in {x['id'] for x in sources} and (cid, mode) != ('en:mep-078', 'square'):
                    raise ValueError('Unexpected vector addition')
                additions.append(dict(card_id=cid, mode=mode, snapshot_id=snapshot,
                                      embedding=vector, source_vector_sha256=digest))
    if len(snapshot_changes) != len(old_vectors):
        raise ValueError('Old vector missing')
    add('card_embeddings', 'update', snapshot_changes, ['card_id', 'mode'],
        {k: 'text' for k in snapshot_changes[0]['before']}, size=1000)
    add('card_embeddings', 'insert', additions, [], dict(card_id='text', mode='text', snapshot_id='text', embedding='vector', source_vector_sha256='text'))
    art = np.load(root / 'skyridge-pilot-v1/artwork/embeddings.npy', allow_pickle=False)
    art_records = json.loads((root / 'skyridge-pilot-v1/artwork/records.json').read_text())
    for file, field in [('embeddings.npy', 'embeddings_sha256'), ('records.json', 'records_sha256')]:
        if hashlib.sha256((root / 'skyridge-pilot-v1/artwork' / file).read_bytes()).hexdigest() != metadata['artwork'][field]:
            raise ValueError('Coherent artwork artifact changed')
    old_art = {(x['card_id'], x['profile']): x for x in tables['artwork_embeddings']}
    art_additions = []
    for index, (record, vector) in enumerate(zip(art_records, art)):
        digest = hashlib.sha256(vector.astype('>f4').tobytes()).hexdigest(); key = (record['card_id'], record['profile'])
        if key in old_art:
            if old_art[key]['row_index'] != index or old_art[key]['source_vector_sha256'] != digest:
                raise ValueError('Existing artwork changed')
        else:
            if key[0] not in {x['id'] for x in sources} | {'en:mep-078'} or key[1] not in ('conventional_window', 'broad_center_hypothesis'):
                raise ValueError('Unexpected artwork addition')
            art_additions.append(dict(card_id=key[0], profile=key[1], row_index=index, embedding=vector,
                                      source_vector_sha256=digest, metadata=record))
    if len(art_records) != len(art) or len(art_additions) != 66:
        raise ValueError('Artwork cardinality drift')
    if len({(x['card_id'], x['profile']) for x in art_records}) != len(art_records):
        raise ValueError('Duplicate artwork key')
    add('artwork_embeddings', 'insert', art_additions, [], dict(card_id='text', profile='text', row_index='integer', embedding='vector', source_vector_sha256='text', metadata='jsonb'))
    source_rows, references = [], []
    for source in sources:
        if not source['identity_approved'] or source['readable_contradictions'] or source['unexpected_stamp_observed']:
            raise ValueError('Unapproved source')
        source_path = source['source_file']
        source_path = root / source_path[len('/completion/'):] if source_path.startswith('/completion/') else Path(source_path)
        if hashlib.sha256(source_path.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('Reviewed source bytes changed')
        evidence = dict(source, publication_approved=False, public_display_policy='pending',
                        candidate_import=import_id, status='reviewed_disposable_reference_not_activated')
        source_rows.append(dict(source_table='catalogue_completion_sources', source_key=import_id + ':' + source['id'], metadata=evidence))
        references.append(dict(source_key='catalogue-completion-source:' + import_id + ':' + source['id'], metadata=evidence))
    old_source_keys = {(x['source_table'], x['source_key']) for x in tables['source_records']}
    old_ref_keys = {x['source_key'] for x in tables['reference_metadata']}
    if any((x['source_table'], x['source_key']) in old_source_keys for x in source_rows) or any(x['source_key'] in old_ref_keys for x in references):
        raise ValueError('Source key collision')
    # source_records accepts only Cardmarket crawl/snapshot records. The exact
    # same independent-source evidence is retained in reference_metadata.
    add('reference_metadata', 'insert', references, [], dict(source_key='text', metadata='jsonb'))
    old_refs = {x['source_key']: x for x in tables['reference_metadata']}
    for mode in ('pad', 'square'):
        key = 'vector-manifest:' + mode
        add('reference_metadata', 'update', [dict(before=old_refs[key], after=dict(source_key=key, metadata=json.loads((coherent / (mode + '-manifest.json')).read_text())))], ['source_key'], dict(source_key='text', metadata='jsonb'))
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.output / 'overlay-batches.jsonl').open('x') as handle:
        for batch in batches:
            handle.write(json.dumps(batch, ensure_ascii=False) + '\n')
    report = dict(batches=len(batches), card_changes=len(changes), helper_additions=len(helpers),
                  existing_vector_snapshot_rebindings=len(snapshot_changes), vector_additions=len(additions),
                  artwork_additions=len(art_additions), source_additions=0, reference_additions=len(references),
                  expected_post_overlay_counts=metadata['counts'], target_schema=schema, import_id=import_id,
                  executed=False, activated=False, publication_allowed=False,
                  import_metadata_replacement_pending=True,
                  requirements=['Exact isolated DDL approval and seed verification', 'Returned count and commit evidence for every batch',
                                'No blind retry; full row readback on ambiguous outcome', 'Full candidate digests/vector binary roundtrip validation',
                                'Final loading import metadata update from actual readback', 'Source display, coherent startup, staging and rollback gates'])
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
