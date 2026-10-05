"""Assemble a new immutable feature release from verified parent and delta bundles.

Runs in the staging-compatible builder. Existing bundles are never written.
Hard links require the same filesystem; there is no silent full-copy fallback.
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.artifacts import ArtifactError, sha256_file
from app.recognition.reference_features import ReferenceFeatureStore, catalogue_signature


def assemble(parent, parent_rows, candidate_rows, output, expected_sources, delta=None):
    parent = Path(parent)
    output = Path(output)
    old = ReferenceFeatureStore.load(parent, parent_rows)
    parent_manifest_hash = sha256_file(parent / 'manifest.json')
    if len({str(r['id']) for r in candidate_rows}) != len(candidate_rows):
        raise ArtifactError('Duplicate candidate ID')
    candidate_ids = {str(r['id']) for r in candidate_rows}
    if set(expected_sources) != candidate_ids:
        raise ArtifactError('Expected source hashes must cover every candidate ID')
    old_rows = {str(r['id']): r for r in parent_rows}
    delta_rows = [r for r in candidate_rows if delta and str(r['id']) in
                  json.loads((Path(delta) / 'manifest.json').read_text())['records']]
    additions = ReferenceFeatureStore.load(Path(delta), delta_rows) if delta else None
    records = {}
    plan = []
    for row in candidate_rows:
        card_id = str(row['id'])
        if additions and card_id in additions.manifest['records']:
            record = additions.manifest['records'][card_id]
            directory = Path(delta)
            origin = 'delta'
        elif card_id in old_rows and all(str(row.get(k) or '').casefold() ==
                str(old_rows[card_id].get(k) or '').casefold() for k in ('rarity',)) and (
                row.get('image_path') or '') == (old_rows[card_id].get('image_path') or ''):
            record = old.manifest['records'][card_id]
            directory = parent
            origin = 'parent'
        else:
            raise ArtifactError(f'Changed reference requires a validated delta: {card_id}')
        expected = expected_sources[card_id]
        if (record.get('source_sha256') if record['available'] else None) != expected:
            raise ArtifactError(f'Source selection mismatch: {card_id}')
        records[card_id] = deepcopy(record)
        if record['available']:
            plan.append((directory / record['filename'], record, origin))
    output.mkdir(parents=True, exist_ok=False)
    linked_bytes = 0
    for source, record, origin in plan:
        if source.is_symlink() or sha256_file(source) != record['sha256']:
            raise ArtifactError('Source feature changed before assembly')
        target = output / record['filename']
        os.link(source, target, follow_symlinks=False)
        if target.is_symlink() or sha256_file(target) != record['sha256']:
            raise ArtifactError('Linked feature checksum mismatch')
        linked_bytes += target.stat().st_size
    if sha256_file(parent / 'manifest.json') != parent_manifest_hash:
        raise ArtifactError('Parent manifest changed during assembly')
    # Independent manifest inode. Publish only after all links are verified.
    manifest = dict(schema_version=old.manifest['schema_version'],
                    processing=old.manifest['processing'],
                    catalogue_sha256=catalogue_signature(candidate_rows), records=records,
                    cards=len(records), available=sum(r['available'] for r in records.values()))
    temporary = output / 'manifest.pending.json'
    temporary.write_text(json.dumps(manifest, sort_keys=True, indent=2))
    temporary.rename(output / 'manifest.json')
    ReferenceFeatureStore.load(output, candidate_rows)
    ReferenceFeatureStore.load(parent, parent_rows)
    return dict(cards=len(records), available=manifest['available'],
                parent_files=sum(origin == 'parent' for _, _, origin in plan),
                delta_files=sum(origin == 'delta' for _, _, origin in plan),
                linked_bytes=linked_bytes, parent_manifest_sha256=parent_manifest_hash,
                manifest_sha256=sha256_file(output / 'manifest.json'), validated=True,
                safety='Never modify linked NPZ files in place; replace with a new inode in a new release.')


def rows(path):
    with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        return [dict(r) for r in db.execute('SELECT id,image_path,rarity FROM cards')]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent', type=Path, required=True)
    p.add_argument('--parent-catalogue', type=Path, required=True)
    p.add_argument('--candidate-catalogue', type=Path, required=True)
    p.add_argument('--expected-sources', type=Path, required=True)
    p.add_argument('--delta', type=Path)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    report = assemble(a.parent, rows(a.parent_catalogue), rows(a.candidate_catalogue),
                      a.output, json.loads(a.expected_sources.read_text()), a.delta)
    (a.output / 'assembly-report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == '__main__':
    main()
