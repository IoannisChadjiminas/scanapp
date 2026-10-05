"""Paired offline full-pipeline regression. Never indexes the frozen photos.

Uses 100 previously labelled raw photos and 50 slabs, not a fresh holdout. The
candidate explicitly forbids reference-image reads. No thresholds are tuned.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import cv2
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.db import init_results
from app.recognition.artifacts import sha256_file
from app.recognition.artwork import ArtworkIndex
from app.recognition.pipeline import recognize_bytes
from benchmark_printing_crops import load_readonly_runtime

ROOT = Path(__file__).resolve().parents[2]


def selection():
    fresh = json.loads((ROOT / 'docs/grading-fresh100-frozen-sources-20261002.json').read_text())
    truth = json.loads((ROOT / 'docs/grading-fresh100-card-truth-audited-20261002.json').read_text())
    assert truth['sources_sha256'] == sha256_file(ROOT / 'docs/grading-fresh100-frozen-sources-20261002.json')
    expected = {p['id']: p['expected_card_ids'] for p in truth['photos']}
    cases = [{**p, 'kind': p['manual_truth']['kind'], 'expected_card_ids': expected[p['id']]}
             for p in fresh['photos']]
    extra = []
    for batch in (4, 3, 2):
        labels = json.loads((ROOT / f'docs/internet-photo-holdout{batch}-sources.json').read_text())
        for p in labels['photos']:
            if 'slab' not in p['conditions']:
                path = f'datasets/review/holdout{batch}-frozen-20261002/photos/{p["id"]}.jpg'
                extra.append({**p, 'kind': 'raw', 'path': path,
                              'expected_card_ids': [p['expected_card_id']]})
    cases.extend(extra[:50])
    assert Counter(p['kind'] for p in cases) == {'raw': 100, 'slab': 50}
    assert len({p['sha256'] for p in cases}) == len(cases)
    for p in cases:
        assert sha256_file(ROOT / p['path']) == p['sha256']
    return cases


def stable_response(response):
    result = dict(response)
    for field in ('id', 'timings_ms'):
        result.pop(field, None)
    result['versions'] = {k: v for k, v in result['versions'].items() if k != 'reference_features'}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('images', 'features'), required=True)
    parser.add_argument('--audit-dir', type=Path, required=True)
    parser.add_argument('--features-dir', type=Path)
    parser.add_argument('--shards', type=int, default=1)
    parser.add_argument('--shard-index', type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.shards <= 8 or not 0 <= args.shard_index < args.shards:
        parser.error('Invalid diagnostic shard index/count')
    cv2.setNumThreads(1)
    output = args.audit_dir / (args.mode + '.jsonl')
    if output.exists():
        parser.error('Output exists; never overwrite an audit run')
    code = {str(p.relative_to(ROOT)): sha256_file(p) for p in (ROOT / 'api/app').rglob('*.py')}
    cases = selection()[args.shard_index::args.shards]
    settings = Settings(_env_file=None, data_dir=Path('/data'), catalogue_backend='sqlite',
                        enable_matched=True, store_captures=False,
                        reference_features_dir=args.features_dir if args.mode == 'features' else None)
    source = sqlite3.connect('file:/data/catalog.sqlite?mode=ro', uri=True)
    catalog = sqlite3.connect(':memory:')
    source.backup(catalog)
    source.close()
    catalog.row_factory = sqlite3.Row
    catalog.execute('PRAGMA query_only=ON')
    runtime = load_readonly_runtime(settings, catalog)
    runtime.artwork_index = ArtworkIndex.load(Path('/data/artwork'), snapshot=runtime.snapshot,
        model_path=settings.dinov2_path, known_ids={r[0] for r in catalog.execute('SELECT id FROM cards')},
        known_languages={r[0]: r[1] or 'en' for r in catalog.execute('SELECT id,language FROM cards')})
    # Both paths use one frozen catalogue/vector/model/code snapshot.
    if args.mode == 'features':
        assert runtime.artwork_verifier.feature_store is not None
        reference_hashes = {r['source_sha256'] for r in runtime.artwork_verifier.feature_store.manifest['records'].values()
                            if r['available']}
        assert not reference_hashes.intersection(p['sha256'] for p in cases)
        original_open = Image.open
        root = settings.images_dir.resolve()
        def no_reference_image_reads(fp, *pos, **kwargs):
            if isinstance(fp, (str, Path)) and Path(fp).resolve().is_relative_to(root):
                raise AssertionError('Candidate attempted to read an original reference image')
            return original_open(fp, *pos, **kwargs)
        Image.open = no_reference_image_reads
    results = sqlite3.connect(':memory:')
    results.row_factory = sqlite3.Row
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('feature-parity','test','test')")
    results.commit()
    with output.open('x') as handle:
        for number, case in enumerate(cases, 1):
            # Same geometric verifier RNG state, independent of previous scan.
            cv2.setRNGSeed(0)
            response = recognize_bytes((ROOT / case['path']).read_bytes(), settings=settings,
                runtime=runtime, catalog=catalog, results=results, session_id='feature-parity',
                skip_detect=False, language='auto', store_capture=False).model_dump(mode='json')
            handle.write(json.dumps(dict(case=case, response=response)) + '\n')
            handle.flush()
            print(json.dumps({'mode': args.mode, 'completed': number, 'total': len(cases),
                              'case': case['id'], 'status': response['status']}), flush=True)
    assert code == {str(p.relative_to(ROOT)): sha256_file(p) for p in (ROOT / 'api/app').rglob('*.py')}, 'Code changed during run'
    audit = dict(code_hashes=code, catalogue_sha256=sha256_file(Path('/data/catalog.sqlite')),
                 selection_sha256=hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest(),
                 versions=runtime.versions(), no_reference_image_reads=args.mode == 'features',
                 sample_counts=dict(Counter(p['kind'] for p in cases)))
    (args.audit_dir / (args.mode + '-audit.json')).write_text(json.dumps(audit, indent=2))
    if args.mode == 'features':
        baseline_audit = json.loads((args.audit_dir / 'images-audit.json').read_text())
        assert all(audit[k] == baseline_audit[k] for k in ('code_hashes', 'catalogue_sha256', 'selection_sha256'))
        baseline = [json.loads(line) for line in (args.audit_dir / 'images.jsonl').read_text().splitlines()]
        candidate = [json.loads(line) for line in output.read_text().splitlines()]
        deltas = []
        scores = {}
        def canonical(cid):
            return cid if cid.startswith(('en:', 'ja:')) else 'en:' + cid
        for old, new in zip(baseline, candidate, strict=True):
            assert old['case'] == new['case']
            a, b = stable_response(old['response']), stable_response(new['response'])
            if a != b:
                deltas.append(dict(id=old['case']['id'], fields=[k for k in a if a[k] != b[k]]))
        for kind in ('raw', 'slab'):
            rows = [p for p in candidate if p['case']['kind'] == kind]
            scorable = [p for p in rows if p['case']['expected_card_ids']]
            correct = sum(bool(p['response']['best_match']) and canonical(p['response']['best_match']['card_id'])
                          in p['case']['expected_card_ids'] for p in scorable)
            scores[kind] = dict(photos=len(rows), scorable=len(scorable), correct_best_match=correct,
                               unscored=len(rows)-len(scorable))
        summary = dict(equal_responses=len(candidate)-len(deltas), photos=len(candidate), deltas=deltas,
                       grading_equal=sum(a['response']['grading'] == b['response']['grading']
                                         for a, b in zip(baseline, candidate, strict=True)),
                       accuracy=scores, no_reference_image_reads=True,
                       limitations='Previously tested Internet-photo regression, not unseen holdout, staging HTTP or Flutter camera. Printing truth excludes finish/authenticity; missing catalogue truth remains unscored.')
        (args.audit_dir / 'parity-summary.json').write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary), flush=True)
        if deltas:
            raise SystemExit('Storage-path regression detected; do not activate')


if __name__ == '__main__':
    main()
