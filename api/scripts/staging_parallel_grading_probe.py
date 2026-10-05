"""Paired scheduling regression on frozen real photos, read-only catalogue.

Runs inside the deployment image with /data mounted read-only. Never indexes
photos, persists captures, changes cloud mappings, or tunes confidence rules.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import resource
import statistics
import sys
import time
from threading import Lock

import cv2
import sqlite3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.db import init_catalog, init_results
from app.planetscale import CloudCatalogConnection, load_cloud_catalogue
from app.recognition.artifacts import sha256_file
from app.recognition.pipeline import recognize_bytes
from app.recognition.runtime import Runtime
from app.recognition.grading import VERSION as GRADING_VERSION


def stable(response):
    return {k: v for k, v in response.items() if k not in {'id', 'timings_ms'}}


class SessionProbe:
    """Diagnostic-only wrapper: observe model tensors without changing OCR."""
    def __init__(self, session, label, events, lock):
        self.session, self.label = session, label
        self.events, self.lock = events, lock

    def __getattr__(self, name):
        return getattr(self.session, name)

    def __call__(self, tensor, *args, **kwargs):
        digest = hashlib.sha256(tensor.tobytes()).hexdigest()
        started = time.perf_counter()
        try:
            return self.session(tensor, *args, **kwargs)
        finally:
            event = {'model': self.label, 'shape': list(tensor.shape),
                     'sha256': digest, 'ms': round((time.perf_counter()-started)*1000, 2)}
            with self.lock:
                self.events.append(event)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-dir', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=8)
    parser.add_argument('--baseline-file', type=Path,
                        help='Compare one candidate pass with the frozen feature-reader baseline')
    parser.add_argument('--profile-ocr', action='store_true')
    parser.add_argument('--detector-max-side', action='store_true',
                        help='Diagnostic only: test RapidOCR max-side rather than min-side resizing')
    parser.add_argument('--card-deadline', action='store_true')
    parser.add_argument('--recheck-completed-holder-reviews', type=Path,
                        help='Replay all completed grading/ambiguous-printing branches from a full deadline run')
    args = parser.parse_args()
    if args.limit < 4 or args.limit % 2:
        parser.error('--limit must be an even number of at least four')
    cv2.setNumThreads(1)
    # No drawings are produced by this replay. Avoid downloading an unused
    # visualization font into the ephemeral diagnostic container.
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path = lambda self, *args, **kwargs: 'unused-benchmark-drawing-font'
    settings = Settings(store_captures=False, portfolio_database_url='',
                        parallel_grading=True, enable_matched=True,
                        grading_at_card_deadline=args.card_deadline)
    assert not (args.card_deadline and args.profile_ocr), 'Do not mix cross-request asynchronous tensor traces'
    assert settings.catalogue_backend == 'planetscale'
    assert settings.reference_features_dir is not None
    catalog = sqlite3.connect(':memory:', factory=CloudCatalogConnection)
    catalog.row_factory = sqlite3.Row
    init_catalog(catalog)
    print(json.dumps({'phase': 'read_only_catalogue_load'}), flush=True)
    snapshot = load_cloud_catalogue(settings, catalog)
    runtime = Runtime(settings)
    runtime.load(snapshot)
    runtime.bind_card_languages(catalog)
    runtime.require()
    assert runtime.grading_ocr is not runtime.ocr and runtime.grading_executor is not None
    if args.detector_max_side:
        for reader in (runtime.ocr, runtime.grading_ocr):
            reader.engine.text_det.limit_type = 'max'
    cases = json.loads((args.audit_dir/'cases.json').read_text())
    baseline = None
    if args.baseline_file:
        baseline = {r['case']['id']: r for r in
                    (json.loads(line) for line in args.baseline_file.read_text().splitlines())}
        for case in cases:
            assert baseline[case['id']]['case']['sha256'] == case['sha256']
    if args.recheck_completed_holder_reviews:
        source = [json.loads(line) for line in args.recheck_completed_holder_reviews.read_text().splitlines()]
        assert len(source) == 150
        ids = {r['case']['id'] for r in source if r['parallel']['status']=='printing_ambiguous'
               and r['parallel']['grading']['company'] is not None}
        # Also confirm the originally slow unfinished-grade case still exits.
        ids.add('fresh100_205408031074')
        cases = [case for case in cases if case['id'] in ids]
    events, event_lock = [], Lock()
    if args.profile_ocr:
        for label, reader in [('card', runtime.ocr), ('grading', runtime.grading_ocr)]:
            for component in ('det', 'cls', 'rec'):
                model = getattr(reader.engine, 'text_'+component)
                model.session = SessionProbe(model.session, label+'.'+component, events, event_lock)
    if args.limit < len(cases):
        # Balance kinds and include short + hard cases from the prior frozen
        # baseline. Selection is reproducible, never cherry-picks successes.
        prior = [json.loads(line) for line in (args.audit_dir/'native-paired-full.jsonl').read_text().splitlines()]
        by_id = {r['case']['id']: r['features']['timings_ms'] for r in prior}
        selected = []
        for kind in ('raw', 'slab'):
            group = [c for c in cases if c['kind'] == kind]
            ordered = sorted(group, key=lambda c: by_id[c['id']]['total_ms'])
            indices = [0, len(ordered)//2, -1]
            for field in ('ocr_ms', 'grading_ms'):
                item = max(group, key=lambda c: by_id[c['id']].get(field, 0))
                if item not in selected:
                    selected.append(item)
            for i in indices:
                if sum(c['kind'] == kind for c in selected) >= args.limit//2:
                    break
                if ordered[i] not in selected:
                    selected.append(ordered[i])
        cases = selected[:args.limit]
    output = args.audit_dir/'parallel-paired.jsonl'
    deltas, records = [], []
    cache_catalog = runtime._sku_catalog
    cache_groups = runtime._sku_groups
    try:
        with output.open('x') as handle:
            for number, case in enumerate(cases, 1):
                path = args.audit_dir/case['photo_file']
                assert path.resolve().is_relative_to(args.audit_dir.resolve())
                assert sha256_file(path) == case['sha256']
                pair = []
                if baseline:
                    old = baseline[case['id']]['features']
                    assert old['versions'] == {
                        **runtime.versions(), 'presentation': 'best-match-v1', 'grading': GRADING_VERSION}
                    pair.append(('serial', old, old['timings_ms']['total_ms']))
                # Alternate ordering to reduce systematic warmup bias.
                modes = ('parallel',) if baseline else (
                    ('serial', 'parallel') if number%2 else ('parallel', 'serial'))
                case_profiles = {}
                for mode in modes:
                    events.clear()
                    settings.parallel_grading = mode == 'parallel'
                    runtime._sku_catalog = cache_catalog if mode == 'parallel' else None
                    runtime._sku_groups = cache_groups if mode == 'parallel' else None
                    results = sqlite3.connect(':memory:')
                    results.row_factory = sqlite3.Row
                    init_results(results)
                    results.execute("INSERT INTO sessions VALUES ('latency-test','test','test')")
                    results.commit()
                    cv2.setRNGSeed(0)
                    started = time.perf_counter()
                    try:
                        response = recognize_bytes(path.read_bytes(), settings=settings, runtime=runtime,
                            catalog=catalog, results=results, session_id='latency-test',
                            language='auto', store_capture=False).model_dump(mode='json')
                    finally:
                        results.close()
                    elapsed = (time.perf_counter()-started)*1000
                    if args.card_deadline:
                        # Outside response latency: verify optional work stops
                        # promptly and cannot accumulate behind later photos.
                        drain_started = time.perf_counter()
                        assert runtime.grading_slots.acquire(timeout=10), 'Cancelled label worker did not release its slot'
                        runtime.grading_slots.release()
                        response['timings_ms']['diagnostic_cleanup_ms'] = round((time.perf_counter()-drain_started)*1000,2)
                    pair.append((mode, response, elapsed))
                    case_profiles[mode] = list(events)
                    print(json.dumps({'case': case['id'], 'number': number, 'total': len(cases),
                        'mode': mode, 'ms': round(elapsed, 2),
                        'peak_rss_mib': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024, 1)}), flush=True)
                values = {mode: response for mode, response, _ in pair}
                times = {mode: elapsed for mode, _, elapsed in pair}
                old, new = stable(values['serial']), stable(values['parallel'])
                if old != new:
                    deltas.append({'id': case['id'], 'fields': [k for k in old if old[k] != new[k]]})
                record = {'case': case, **values, 'elapsed_ms': times,
                          'ocr_profile': case_profiles}
                records.append(record)
                handle.write(json.dumps(record)+'\n')
                handle.flush()
    finally:
        runtime.close()
        catalog.close()
    summary = {'photos': len(records), 'counts': dict(Counter(r['case']['kind'] for r in records)),
        'equal_responses': len(records)-len(deltas), 'deltas': deltas,
        'grading_equal': sum(r['serial']['grading'] == r['parallel']['grading'] for r in records),
        'card_responses_equal': sum({k:v for k,v in stable(r['serial']).items() if k!='grading'} ==
                                   {k:v for k,v in stable(r['parallel']).items() if k!='grading'} for r in records),
        'latency_ms': {mode: {'median': round(statistics.median(r['elapsed_ms'][mode] for r in records),2),
            'max': round(max(r['elapsed_ms'][mode] for r in records),2),
            'under_5000': sum(r['elapsed_ms'][mode] <= 5000 for r in records)} for mode in ('serial','parallel')},
        'peak_rss_mib': round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1),
        'baseline_reused': bool(baseline),
        'diagnostic_detector_max_side': args.detector_max_side,
        'card_deadline': args.card_deadline,
        'rechecked_completed_holder_reviews': bool(args.recheck_completed_holder_reviews),
        'ungraded': sum(r['parallel']['grading']['grading_status']=='ungraded' for r in records),
        'runtime_versions': runtime.versions(),
        'thresholds': runtime.threshold_config(),
        'limitations': 'Scheduling/storage regression on frozen convenience photos, not unseen accuracy or a latency SLA; diagnostic CPU contention may differ from live.'}
    (args.audit_dir/'parallel-summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)
    if deltas and (not args.card_deadline or any(any(f!='grading' for f in d['fields']) for d in deltas)):
        raise SystemExit('Scheduling regression; do not activate')


if __name__ == '__main__':
    main()
