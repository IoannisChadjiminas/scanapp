"""Read-only staging-architecture parity check; no persistent scan/database writes.

Consumes a frozen cases.json and photos below --audit-dir. Run in the deployment
image with a read-only data mount and the existing read-only catalogue role.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys
import time

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.db import init_catalog, init_results
from app.planetscale import load_cloud_catalogue
from app.recognition.artifacts import sha256_file
from app.recognition.local_match import LocalArtworkVerifier
from app.recognition.pipeline import recognize_bytes
from app.recognition.printing import ReferencePrintingIndex, artwork_thumbnail
from app.recognition.reference_features import ReferenceFeatureStore, SIFT_PROFILES, extract_reference
from app.recognition.runtime import Runtime


def stable(response):
    value = dict(response)
    for field in ('id', 'timings_ms'):
        value.pop(field, None)
    value['versions'] = {k: v for k, v in value['versions'].items() if k != 'reference_features'}
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-dir', type=Path, required=True)
    parser.add_argument('--features-dir', type=Path, required=True)
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    settings = Settings(reference_features_dir=None, store_captures=False,
                        portfolio_database_url='', enable_matched=True)
    assert settings.catalogue_backend == 'planetscale'
    catalog = sqlite3.connect(':memory:')
    catalog.row_factory = sqlite3.Row
    init_catalog(catalog)
    print(json.dumps({'phase': 'read_only_cloud_snapshot'}), flush=True)
    snapshot = load_cloud_catalogue(settings, catalog)
    rows = [dict(r) for r in catalog.execute('SELECT id,image_path,rarity FROM cards')]
    store = ReferenceFeatureStore.load(args.features_dir, rows)
    # All feature provenance must match the deployed originals, not test photos.
    for record in store.manifest['records'].values():
        if record['available']:
            assert sha256_file(Path(record['image_path'])) == record['source_sha256']
    print(json.dumps({'phase': 'all_reference_checksums_verified', 'available': store.manifest['available']}), flush=True)
    # A representative extraction check catches differences between CPU builds.
    available = [(cid, r) for cid, r in sorted(store.manifest['records'].items()) if r['available']]
    native_deltas = []
    for cid, record in available[::max(1, len(available)//100)][:100]:
        with Image.open(record['image_path']) as original:
            for features, contrast in SIFT_PROFILES:
                native = extract_reference(original, record['art_box'], features, contrast)
                saved = store.features(cid, record['image_path'], tuple(record['art_box']), features, contrast)
                if (not np.array_equal(native.points, saved.points)
                    or not np.array_equal(native.descriptors, saved.descriptors)
                    or native.size != saved.size):
                    native_deltas.append({'id': cid, 'profile': features})
            if not np.array_equal(artwork_thumbnail(original), store.thumbnail(cid, record['image_path'])):
                native_deltas.append({'id': cid, 'profile': 'thumbnail'})
    (args.audit_dir/'native-reference-check.json').write_text(json.dumps({'sample': 100, 'deltas': native_deltas}, indent=2))
    print(json.dumps({'phase': 'native_reference_check', 'deltas': len(native_deltas)}), flush=True)
    if native_deltas:
        raise SystemExit('Reference extraction differs on deployment architecture; rebuild before activation')
    runtime = Runtime(settings)
    runtime.load(snapshot)
    runtime.bind_card_languages(catalog)
    runtime.require()
    original_open = Image.open
    root = settings.images_dir.resolve()
    blocked_reads = 0
    def no_reference_reads(fp, *pos, **kwargs):
        nonlocal blocked_reads
        if isinstance(fp, (str, Path)) and Path(fp).resolve().is_relative_to(root):
            blocked_reads += 1
            raise AssertionError('Feature-backed scan attempted reference-image read')
        return original_open(fp, *pos, **kwargs)
    cases = json.loads((args.audit_dir/'cases.json').read_text())
    if args.limit:
        # Balanced smoke subset; the complete file remains frozen for full run.
        cases = [p for kind in ('raw', 'slab') for p in [c for c in cases if c['kind'] == kind][:args.limit//2]]
    source_hashes = {r['source_sha256'] for r in store.manifest['records'].values() if r['available']}
    assert not source_hashes.intersection(c['sha256'] for c in cases)
    output = args.audit_dir/('paired-smoke.jsonl' if args.limit else 'paired-full.jsonl')
    deltas = []
    grading_equal = 0
    counts = Counter()
    scores = Counter()
    versions = None
    with output.open('x') as handle:
        for number, case in enumerate(cases, 1):
            path = args.audit_dir/case['photo_file']
            assert path.resolve().is_relative_to(args.audit_dir.resolve())
            assert sha256_file(path) == case['sha256']
            payload = path.read_bytes()
            pair = []
            for mode in ('images', 'features'):
                # Fresh reference caches and the same geometric RNG for each path.
                runtime.artwork_verifier = LocalArtworkVerifier(settings.data_dir,
                    feature_store=store if mode == 'features' else None)
                runtime.printing_index = ReferencePrintingIndex(settings.data_dir,
                    feature_store=store if mode == 'features' else None)
                runtime.artwork_verifier.reference_boxes = {
                    cid: tuple(r['art_box']) for cid, r in store.manifest['records'].items()}
                Image.open = no_reference_reads if mode == 'features' else original_open
                results = sqlite3.connect(':memory:')
                results.row_factory = sqlite3.Row
                init_results(results)
                results.execute("INSERT INTO sessions VALUES ('staging-feature-parity','test','test')")
                results.commit()
                cv2.setRNGSeed(0)
                started = time.perf_counter()
                try:
                    response = recognize_bytes(payload, settings=settings, runtime=runtime,
                        catalog=catalog, results=results, session_id='staging-feature-parity',
                        skip_detect=False, language='auto', store_capture=False).model_dump(mode='json')
                finally:
                    Image.open = original_open
                    results.close()
                pair.append(response)
                print(json.dumps({'case': case['id'], 'number': number, 'total': len(cases),
                                  'mode': mode, 'seconds': round(time.perf_counter()-started, 2)}), flush=True)
            old, new = pair
            a, b = stable(old), stable(new)
            if a != b:
                deltas.append({'id': case['id'], 'fields': [k for k in a if a[k] != b[k]]})
            grading_equal += old['grading'] == new['grading']
            counts[case['kind']] += 1
            expected = case['expected_card_ids']
            if expected:
                scores[case['kind']+'_scorable'] += 1
                best = new.get('best_match')
                cid = best['card_id'] if best else ''
                if cid and not cid.startswith(('en:', 'ja:')):
                    cid = 'en:'+cid
                scores[case['kind']+'_correct'] += cid in expected
            versions = new['versions']
            handle.write(json.dumps({'case': case, 'images': old, 'features': new})+'\n')
            handle.flush()
    summary = {'photos': len(cases), 'equal_responses': len(cases)-len(deltas),
               'grading_equal': grading_equal, 'deltas': deltas,
               'blocked_reference_read_attempts': blocked_reads, 'sample_counts': dict(counts),
               'scores': dict(scores), 'versions': versions,
               'catalogue_import_id': settings.planetscale_import_id,
               'limitations': 'Previously tested convenience regression photos, not an unseen benchmark; no finish/authenticity truth.'}
    destination = args.audit_dir/('smoke-summary.json' if args.limit else 'full-summary.json')
    destination.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
    if deltas or blocked_reads:
        raise SystemExit('Staging storage-path regression; do not activate')


if __name__ == '__main__':
    main()
