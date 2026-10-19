"""Frozen image regression for the conflict-only title retry.

Run in a separate resource-limited API-image container with read-only data.
Both arms use the same current code/catalogue; only the retry flag changes.
"""
import argparse
from dataclasses import fields
from contextlib import contextmanager, nullcontext
import gc
import hashlib
import json
from pathlib import Path
import resource
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
from PIL import Image
from app.config import Settings
from app.db import init_catalog, init_results
from app.planetscale import CloudCatalogConnection, load_cloud_catalogue
from app.recognition import pipeline
from app.recognition.artifacts import sha256_file
from app.recognition.runtime import Runtime
from app.recognition.ocr import OcrHit, OcrResult
from regression_layout_recovery import exact_pixel_inference_cache, summarize


@contextmanager
def selected_query_frame(path, enabled, recorded_ocr=None):
    # Retained cases omit the original phone quad. Query-image cases replay
    # the actual selected frame, without redetecting its sleeve/background.
    # Input-image cases exercise ordinary framing separately.
    if not enabled:
        yield
        return
    original = pipeline._recognize_bytes_once
    with Image.open(path) as source:
        frame = source.convert('RGB')
    def evaluate(data, **kwargs):
        if '_frame_override' not in kwargs:
            kwargs['_frame_override'] = ('replay_selected_query', frame)
            kwargs['_frame_detected_override'] = True
            if recorded_ocr:
                # Retained JPEGs are recompressed: preserve the actual first
                # observations in an additional evidence-reproduction case.
                # The new focused read and artwork geometry still use models.
                names = {field.name for field in fields(OcrResult)} - {'hits'}
                kwargs['_title_retry_ocr'] = OcrResult(
                    **{k: v for k, v in recorded_ocr.items() if k in names},
                    hits=[OcrHit(**h) for h in recorded_ocr['hits']])
        return original(data, **kwargs)
    pipeline._recognize_bytes_once = evaluate
    try:
        yield
    finally:
        pipeline._recognize_bytes_once = original
        frame.close()


def evaluate(case, root, settings, runtime, catalog, *, uncached):
    pair = {}
    photo = root / case['photo_file']
    cache = nullcontext() if uncached else exact_pixel_inference_cache(runtime)
    with cache, selected_query_frame(photo, case.get('selected_query', False), case.get('recorded_ocr')):
        for enabled in (False, True):
            config = settings.model_copy(update={'ocr_conflict_title_retry': enabled})
            results = sqlite3.connect(':memory:')
            results.row_factory = sqlite3.Row
            init_results(results)
            results.execute("INSERT INTO sessions VALUES('title-regression','test','test')")
            cv2.setRNGSeed(0)
            start = time.perf_counter()
            try:
                response = pipeline.recognize_bytes(photo.read_bytes(), settings=config, runtime=runtime,
                    catalog=catalog, results=results, session_id='title-regression', store_capture=False, graded=False)
                evidence = json.loads(results.execute('SELECT ocr_json FROM scans WHERE id=?', (response.id,)).fetchone()[0])
                pair['candidate' if enabled else 'baseline'] = dict(
                    card_id=response.best_match.card_id if response.best_match else None,
                    status=response.status.value, response=response.model_dump(mode='json'),
                    evidence=evidence, elapsed_ms=round((time.perf_counter()-start)*1000))
            finally:
                results.close()
    return pair


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--photos-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--batch-size', type=int, default=30)
    parser.add_argument('--uncached', action='store_true')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    cases = manifest['cases']
    root = args.photos_root.resolve()
    for case in cases:
        photo = (root / case['photo_file']).resolve()
        if not photo.is_relative_to(root) or sha256_file(photo) != case['sha256']:
            raise ValueError('Frozen photo hash/path mismatch: ' + case['id'])
    rows = []
    if args.output.exists():
        if not args.resume:
            parser.error('output exists; --resume requires the identical manifest/runtime')
        rows = [json.loads(line) for line in args.output.read_text().splitlines() if line]
        lookup = {case['id']: case for case in cases}
        if any(row['case'] != lookup.get(row['case']['id']) for row in rows):
            raise ValueError('Resume manifest differs')
    completed = {row['case']['id'] for row in rows}
    pending = [case for case in cases if case['id'] not in completed][:args.batch_size]
    if not pending:
        print(json.dumps(dict(phase='complete', completed=len(rows))), flush=True)
        return
    cv2.setNumThreads(1)
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path = lambda self, *a, **k: 'unused-regression-font'
    settings = Settings().model_copy(update=dict(store_captures=False, use_grading=False,
        parallel_grading=False, grading_at_card_deadline=False))
    catalog = sqlite3.connect(':memory:', factory=CloudCatalogConnection)
    catalog.row_factory = sqlite3.Row
    init_catalog(catalog)
    with sqlite3.connect(f'file:{settings.catalog_sqlite}?mode=ro', uri=True) as source:
        catalog.executemany('INSERT INTO set_totals VALUES(?,?,?,?)',
            source.execute('SELECT language,set_id,official_total,fetched_at FROM set_totals'))
    catalog.commit()
    runtime = Runtime(settings)
    try:
        snapshot = load_cloud_catalogue(settings, catalog)
        metadata = dict(manifest_sha256=sha256_file(args.manifest),
            code_sha256=hashlib.sha256(b''.join(path.read_bytes() for path in sorted(
                Path(pipeline.__file__).parent.parent.rglob('*.py')))).hexdigest(),
            catalogue_version=snapshot.catalogue_version, catalogue_import_id=settings.planetscale_import_id,
            reference_features=str(settings.reference_features_dir), artwork_bundle=str(settings.artwork_bundle_dir),
            thresholds=runtime.threshold_config(), grading_enabled=False, catalogue_writes=False,
            operational_writes=False, exact_pixel_cache=not args.uncached,
            settings={k: getattr(settings, k) for k in ['ocr_adaptive_footer', 'ocr_parallel_regions',
                'structured_layout_recovery', 'ocr_complete_frame_first', 'ocr_title_only_single_printing']})
        metadata_path = args.output.with_suffix('.metadata.json')
        if metadata_path.exists() and json.loads(metadata_path.read_text()) != metadata:
            raise ValueError('Resume runtime/catalogue changed')
        metadata_path.write_text(json.dumps(metadata, indent=2))
        runtime.load(snapshot)
        runtime.bind_card_languages(catalog)
        runtime.require()
        print(json.dumps(dict(phase='ready', total=len(cases), batch=len(pending), completed=len(rows))), flush=True)
        with args.output.open('a' if args.resume else 'x') as handle:
            for case in pending:
                pair = evaluate(case, root, settings, runtime, catalog, uncached=args.uncached)
                row = dict(case=case, **pair)
                handle.write(json.dumps(row) + '\n')
                handle.flush()
                rows.append(row)
                summary = summarize(rows)
                summary['total'] = len(cases)
                args.output.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2))
                recovery = pair['candidate']['evidence'].get('title_recovery') or {}
                print(json.dumps(dict(completed=len(rows), total=len(cases), id=case['id'],
                    before=[pair['baseline']['card_id'], pair['baseline']['status']],
                    after=[pair['candidate']['card_id'], pair['candidate']['status']],
                    retry=recovery.get('selected'), lost_correct=len(summary['lost_correct_matches']),
                    max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)), flush=True)
                gc.collect()
    finally:
        runtime.close()
        catalog.close()


if __name__ == '__main__':
    main()
