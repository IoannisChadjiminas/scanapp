"""Paired read-only replay of OCR-frame and printing-choice changes.

Uses the frozen deployed implementations with the SAME models, catalogue,
pixels, thresholds and runtime settings. No cloud writes or artifact rebuilds.
"""
import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import sqlite3
import statistics
import sys

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.db import init_results
from app.planetscale import CloudCatalogConnection, protect_catalogue
from app.recognition.artifacts import ArtifactSnapshot, sha256_file, validate_embeddings
from app.recognition.runtime import Runtime
import app.recognition.pipeline as pipeline
import app.recognition.printing as printing
import app.recognition.ocr_framing as framing


def frozen_function(path, name, module):
    node = next(n for n in ast.parse(path.read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = dict(vars(module))
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[name]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit-dir', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--baseline-app', type=Path, required=True)
    p.add_argument('--recent', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--per-kind', type=int, default=10)
    a = p.parse_args(); cv2.setNumThreads(1)
    cases = []
    for cid, expected in [('fa933ce9-43d1-40eb-be04-53a768f44aef', 'en:sv04-123'),
                          ('f94df8e2-685c-4ca2-a027-c84f4d01a43b', 'en:base1-24'),
                          ('7a6c3671-bd21-4533-ad18-caf8afa41364', 'en:base1-24')]:
        photo = a.recent / (cid + '.input.jpg')
        cases.append((dict(id=cid, kind='recent_phone', expected_card_ids=[expected],
                           sha256=sha256_file(photo)), photo))
    counts = Counter()
    for case in json.loads((a.audit_dir / 'cases.json').read_text()):
        if counts[case['kind']] < a.per_kind:
            cases.append((case, a.audit_dir / case['photo_file']))
            counts[case['kind']] += 1
    for case, photo in cases:
        assert sha256_file(photo) == case['sha256']
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path = lambda *args, **kwargs: 'unused-benchmark-font'
    manifest = json.loads((a.candidate / 'vectors/manifest.json').read_text())
    embeddings = np.load(a.candidate / 'vectors/embeddings.npy', mmap_mode='r')
    ids = np.load(a.candidate / 'vectors/embedding_card_ids.npy')
    validate_embeddings(embeddings, ids)
    for path, key in [('embeddings.npy', 'embeddings_sha256'), ('embedding_card_ids.npy', 'ids_sha256')]:
        assert sha256_file(a.candidate / 'vectors' / path) == manifest[key]
    snapshot = ArtifactSnapshot(**{key: manifest[key] for key in (
        'preprocess_config', 'use_ocr', 'catalogue_version', 'model_revision', 'model_name',
        'embedding_dim', 'card_count', 'indexed_count', 'missing_images', 'embeddings_sha256', 'ids_sha256')},
        embeddings=embeddings, card_ids=ids, manifest=manifest, bundle_dir=a.candidate / 'vectors')
    source = sqlite3.connect(f'file:{a.candidate}/catalog.sqlite?mode=ro', uri=True)
    catalog = sqlite3.connect(':memory:', factory=CloudCatalogConnection); catalog.row_factory = sqlite3.Row
    source.backup(catalog); source.close(); protect_catalogue(catalog)
    settings = Settings(_env_file=None, data_dir=Path('/data'), store_captures=False,
        parallel_grading=True, grading_at_card_deadline=True, ocr_complete_frame_first=True,
        ocr_adaptive_footer=True, ocr_parallel_regions=True, ocr_parallel_footer_halves=True,
        ocr_card_priority=True, reference_features_dir=a.candidate / 'features',
        artwork_bundle_dir=a.candidate / 'artwork')
    runtime = Runtime(settings); runtime.load(snapshot); runtime.bind_card_languages(catalog); runtime.require()
    after_probe, after_print = pipeline.complete_frame_probe_allowed, pipeline.assess_printings
    after_title = pipeline.complete_frame_title_supported
    before_probe = frozen_function(a.baseline_app / 'recognition/ocr_framing.py', 'complete_frame_probe_allowed', framing)
    before_print = frozen_function(a.baseline_app / 'recognition/printing.py', 'assess_printings', printing)
    records = []
    try:
        with a.output.open('x') as handle:
            for index, (case, photo) in enumerate(cases):
                outputs = {}
                for after in ([False, True] if index % 2 == 0 else [True, False]):
                    pipeline.complete_frame_probe_allowed = after_probe if after else before_probe
                    pipeline.assess_printings = after_print if after else before_print
                    pipeline.complete_frame_title_supported = after_title if after else lambda *args: False
                    results = sqlite3.connect(':memory:'); results.row_factory = sqlite3.Row; init_results(results)
                    results.execute("INSERT INTO sessions VALUES('probe','test','test')"); results.commit()
                    cv2.setRNGSeed(0)
                    response = pipeline.recognize_bytes(photo.read_bytes(), settings=settings, runtime=runtime,
                        catalog=catalog, results=results, session_id='probe', store_capture=False)
                    evidence = json.loads(results.execute('SELECT ocr_json FROM scans').fetchone()[0]); results.close()
                    outputs[after] = dict(response=response.model_dump(mode='json'), evidence=evidence)
                    assert runtime.grading_slots.acquire(timeout=60), 'Optional grading backlog'
                    runtime.grading_slots.release()
                def best(output):
                    cid = (output['response'].get('best_match') or {}).get('card_id')
                    return ('en:' + cid) if cid and ':' not in cid else cid
                before, after = outputs[False], outputs[True]
                record = dict(case=case, before=before, after=after,
                    checks=dict(before_correct=best(before) in case['expected_card_ids'],
                                after_correct=best(after) in case['expected_card_ids'],
                                same_best=best(before)==best(after),
                                same_url=(before['response'].get('best_match') or {}).get('cardmarket_url') ==
                                         (after['response'].get('best_match') or {}).get('cardmarket_url')))
                records.append(record); handle.write(json.dumps(record) + '\n'); handle.flush()
                print(json.dumps(dict(id=case['id'], number=index+1, total=len(cases), checks=record['checks'],
                    before_ms=round(before['response']['timings_ms']['total_ms']),
                    after_ms=round(after['response']['timings_ms']['total_ms']),
                    original_title_only=after['evidence'].get('frame_selection', {}).get('ocr_complete_frame_title_only'))), flush=True)
    finally:
        pipeline.complete_frame_probe_allowed, pipeline.assess_printings = after_probe, after_print
        pipeline.complete_frame_title_supported = after_title
        runtime.close(); catalog.close()
    summary = dict(photos=len(records), before_correct=sum(r['checks']['before_correct'] for r in records),
        after_correct=sum(r['checks']['after_correct'] for r in records),
        regressions=[r['case']['id'] for r in records if r['checks']['before_correct'] and not r['checks']['after_correct']],
        changed_best_or_url=[r['case']['id'] for r in records if not r['checks']['same_best'] or not r['checks']['same_url']],
        before_median_ms=statistics.median(r['before']['response']['timings_ms']['total_ms'] for r in records),
        after_median_ms=statistics.median(r['after']['response']['timings_ms']['total_ms'] for r in records),
        limitations='Frozen regression panel and downsampled saved uploads; not unseen accuracy or staging P95.')
    a.output.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2)); print(json.dumps(summary), flush=True)
    assert not summary['regressions'], 'Do not publish a recognition regression'


if __name__ == '__main__':
    main()
