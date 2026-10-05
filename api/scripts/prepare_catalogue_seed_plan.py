"""Prepare bounded, non-activating SQL copies from an immutable live export.

No database connection. Loading status is required on every copy. The caller
must verify parent digests and each returned row count, and checkpoint commits.
"""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re

KEYS = {
    'cards': ['id'], 'card_embeddings': ['card_id', 'mode'],
    'artwork_embeddings': ['card_id', 'profile'], 'cardmarket_products': ['url'],
    'cardmarket_url_helpers': ['card_id'], 'cardmarket_review': ['url'],
    'source_records': ['source_table', 'source_key'], 'reference_metadata': ['source_key'],
}


def identifier(value):
    if not re.fullmatch(r'[a-z_][a-z0-9_]*', value):
        raise ValueError('Unsafe identifier')
    return '"' + value + '"'


def literal(value):
    if not isinstance(value, str) or '\x00' in value or '\\' in value:
        raise ValueError('Expected unambiguous text key')
    return "'" + value.replace("'", "''") + "'"


def bound(keys, values, columns=False):
    parts = [identifier(k) + ' COLLATE "C"' for k in keys] if columns else [literal(v) for v in values]
    return parts[0] if len(parts) == 1 else '(' + ','.join(parts) + ')'


def chunks(table, rows, columns, parent, target, import_id, size):
    if table not in KEYS or not 1 <= size <= 1000 or parent == target:
        raise ValueError('Invalid isolated seed request')
    keys = KEYS[table]
    order = sorted(rows, key=lambda row: tuple(v.encode('utf-8') for v in row))
    if len(set(order)) != len(order):
        raise ValueError('Duplicate parent key')
    names = ','.join(identifier(c) for c in columns)
    expr = bound(keys, [], columns=True)
    previous = None
    result = []
    for offset in range(0, len(order), size):
        group = order[offset:offset + size]
        upper = group[-1]
        condition = expr + ' <= ' + bound(keys, upper)
        if previous is not None:
            condition += ' AND ' + expr + ' > ' + bound(keys, previous)
        condition += (' AND EXISTS (SELECT 1 FROM ' + identifier(target) + '.import_manifest'
                      ' WHERE import_id=' + literal(import_id) + " AND status='loading')")
        sql = ('WITH copied AS (INSERT INTO ' + identifier(target) + '.' + identifier(table)
               + ' (' + names + ') SELECT ' + names + ' FROM ' + identifier(parent) + '.'
               + identifier(table) + ' WHERE ' + condition + ' RETURNING 1)'
               ' SELECT count(*) AS rows_inserted FROM copied;')
        result.append(dict(table=table, batch=len(result) + 1, expected_rows=len(group),
                           lower_exclusive=previous, upper_inclusive=upper, sql=sql,
                           sql_sha256=hashlib.sha256(sql.encode()).hexdigest()))
        previous = upper
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--export', type=Path, required=True)
    p.add_argument('--target-schema', required=True)
    p.add_argument('--import-id', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    identifier(a.target_schema)
    keys = defaultdict(list)
    columns = {}
    parent = None
    with gzip.open(a.export, 'rt') as h:
        for line in h:
            record = json.loads(line)
            table = record['table']
            if table == '_snapshot':
                parent = record['schema']
            if table not in KEYS:
                continue
            row = record['row']
            if table in columns and list(row) != columns[table]:
                raise ValueError('Export column drift')
            columns[table] = list(row)
            keys[table].append(tuple(row[k] for k in KEYS[table]))
    if not parent or set(keys) != set(KEYS):
        raise ValueError('Incomplete parent snapshot')
    batches = [b for t in KEYS for b in chunks(t, keys[t], columns[t], parent,
               a.target_schema, a.import_id, 1000)]
    a.output.mkdir(parents=True, exist_ok=False)
    with (a.output / 'seed-batches.jsonl').open('x') as h:
        for b in batches:
            h.write(json.dumps(b) + '\n')
    report = dict(parent_schema=parent, target_schema=a.target_schema, import_id=a.import_id,
                  counts={t: len(v) for t, v in keys.items()}, batches=len(batches),
                  max_rows_per_batch=1000, required_status='loading',
                  export_sha256=hashlib.sha256(a.export.read_bytes()).hexdigest(),
                  executed=False, publication_allowed=False,
                  requirements=['Approved isolated DDL and loading manifest first',
                                'Fresh parent digests before copying',
                                'Verify returned row counts and persist commit evidence',
                                'No blind retries after an ambiguous write response',
                                'Overlay reviewed changes and compute actual full manifest',
                                'Coherent validation and rollback before activation'])
    (a.output / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == '__main__':
    main()
