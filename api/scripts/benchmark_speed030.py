"""Paired offline scan audit: same catalogue, pixels, models and thresholds.

No remote credentials, catalogue mutation, persisted scan or feature rebuild.
Alternates execution order and reports grading availability separately.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import statistics
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.db import init_results
from app.planetscale import CloudCatalogConnection, protect_catalogue
from app.recognition.artifacts import ArtifactSnapshot, sha256_file, validate_embeddings
from app.recognition.pipeline import recognize_bytes
from app.recognition.runtime import Runtime


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit-dir', type=Path, required=True)
    p.add_argument('--extra-audit', type=Path)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--per-kind', type=int, default=10)
    a = p.parse_args(); cv2.setNumThreads(1)
    cases = []; counts = Counter()
    for case in json.loads((a.audit_dir/'cases.json').read_text()):
        if counts[case['kind']] < a.per_kind:
            cases.append((case, a.audit_dir)); counts[case['kind']] += 1
    if a.extra_audit:
        cases.extend((case, a.extra_audit) for case in
                     json.loads((a.extra_audit/'cases.json').read_text()))
    for case, root in cases:
        assert sha256_file(root/case['photo_file']) == case['sha256']
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path = lambda self,*args,**kwargs: 'unused-benchmark-drawing-font'
    manifest = json.loads((a.candidate/'vectors/manifest.json').read_text())
    embeddings = np.load(a.candidate/'vectors/embeddings.npy', mmap_mode='r')
    ids = np.load(a.candidate/'vectors/embedding_card_ids.npy'); validate_embeddings(embeddings, ids)
    assert sha256_file(a.candidate/'vectors/embeddings.npy') == manifest['embeddings_sha256']
    assert sha256_file(a.candidate/'vectors/embedding_card_ids.npy') == manifest['ids_sha256']
    snapshot = ArtifactSnapshot(**{key:manifest[key] for key in (
        'preprocess_config','use_ocr','catalogue_version','model_revision','model_name',
        'embedding_dim','card_count','indexed_count','missing_images','embeddings_sha256','ids_sha256')},
        embeddings=embeddings, card_ids=ids, manifest=manifest, bundle_dir=a.candidate/'vectors')
    source = sqlite3.connect(f'file:{a.candidate}/catalog.sqlite?mode=ro', uri=True)
    catalog = sqlite3.connect(':memory:', factory=CloudCatalogConnection); catalog.row_factory=sqlite3.Row
    source.backup(catalog); source.close(); protect_catalogue(catalog)
    settings = Settings(_env_file=None, data_dir=Path('/data'), store_captures=False,
        use_grading=True, parallel_grading=True, grading_at_card_deadline=True,
        ocr_complete_frame_first=True, ocr_adaptive_footer=True,
        ocr_parallel_regions=True, ocr_parallel_footer_halves=True,
        reference_features_dir=a.candidate/'features', artwork_bundle_dir=a.candidate/'artwork')
    runtime = Runtime(settings); runtime.load(snapshot); runtime.bind_card_languages(catalog); runtime.require()
    records = []
    try:
        with a.output.open('x') as handle:
            for index, (case, root) in enumerate(cases):
                outputs = {}
                for candidate in ([False, True] if index % 2 == 0 else [True, False]):
                    settings.ocr_staged_original = candidate
                    settings.ocr_card_priority = candidate
                    runtime.ocr.card_priority = candidate
                    previews = []
                    results = sqlite3.connect(':memory:'); results.row_factory=sqlite3.Row; init_results(results)
                    results.execute("INSERT INTO sessions VALUES('probe','test','test')"); results.commit()
                    start = time.perf_counter(); cv2.setRNGSeed(0)
                    response = recognize_bytes((root/case['photo_file']).read_bytes(),
                        settings=settings, runtime=runtime, catalog=catalog, results=results,
                        session_id='probe', store_capture=False, _progress_observer=lambda payload:
                        previews.append(dict(received_ms=(time.perf_counter()-start)*1000, **payload)))
                    evidence = json.loads(results.execute('SELECT ocr_json FROM scans').fetchone()[0]); results.close()
                    outputs[candidate] = dict(response=response.model_dump(mode='json'), evidence=evidence,
                                              previews=previews)
                    assert runtime.grading_slots.acquire(timeout=60), 'No optional backlog'
                    runtime.grading_slots.release()
                before, after = outputs[False], outputs[True]
                def best(output): return (output['response'].get('best_match') or {}).get('card_id')
                checks = dict(best_card=best(before)==best(after),
                    url=(before['response'].get('best_match') or {}).get('cardmarket_url') ==
                        (after['response'].get('best_match') or {}).get('cardmarket_url'),
                    status=before['response']['status']==after['response']['status'],
                    printing=before['response'].get('printing_review')==after['response'].get('printing_review'))
                record = dict(case=case, before=before, after=after, checks=checks)
                records.append(record); handle.write(json.dumps(record)+'\n'); handle.flush()
                print(json.dumps(dict(id=case['id'], number=index+1, total=len(cases),
                    checks=checks, before_ms=round(before['response']['timings_ms']['total_ms']),
                    after_ms=round(after['response']['timings_ms']['total_ms']),
                    staged=after['evidence'].get('frame_selection',{}).get('ocr_staged_footer_supported'))), flush=True)
    finally:
        runtime.close(); catalog.close()
    summary = dict(photos=len(records), exact_match_contracts=sum(all(r['checks'].values()) for r in records),
        changed=[dict(id=r['case']['id'], checks=r['checks']) for r in records if not all(r['checks'].values())],
        before_median_ms=statistics.median(r['before']['response']['timings_ms']['total_ms'] for r in records),
        after_median_ms=statistics.median(r['after']['response']['timings_ms']['total_ms'] for r in records),
        median_saved_ms=statistics.median(r['before']['response']['timings_ms']['total_ms']-
                                         r['after']['response']['timings_ms']['total_ms'] for r in records),
        grading_changes=[r['case']['id'] for r in records if r['before']['response']['grading']!=r['after']['response']['grading']],
        limitations='Small frozen paired panel, not unseen accuracy or staging P95. Grading availability can change at the card deadline.')
    a.output.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2)); print(json.dumps(summary), flush=True)
    assert not summary['changed'], 'Match/URL/printing contract changed; do not deploy without reviewing'


if __name__ == '__main__': main()
