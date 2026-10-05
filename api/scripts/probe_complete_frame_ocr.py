"""Read-only OCR-framing regression on frozen photos and saved phone captures."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import resource
import sqlite3
import statistics
import sys
import time

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.db import init_catalog, init_results
from app.planetscale import CloudCatalogConnection, load_cloud_catalogue
from app.recognition.pipeline import recognize_bytes
from app.recognition.runtime import Runtime


def identity(response):
    return (response.get('best_match') or {}).get('card_id')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-dir', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--phone-captures-only', action='store_true')
    args = parser.parse_args()
    cv2.setNumThreads(1)
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path = lambda self, *a, **k: 'unused-benchmark-drawing-font'
    settings = Settings(store_captures=False, portfolio_database_url='', enable_matched=True,
                        parallel_grading=True, grading_at_card_deadline=True)
    assert settings.catalogue_backend == 'planetscale' and settings.reference_features_dir
    catalog = sqlite3.connect(':memory:',factory=CloudCatalogConnection)
    catalog.row_factory = sqlite3.Row
    init_catalog(catalog)
    print(json.dumps({'phase':'read_only_catalogue_load'}),flush=True)
    snapshot = load_cloud_catalogue(settings,catalog)
    runtime = Runtime(settings)
    runtime.load(snapshot)
    runtime.bind_card_languages(catalog)
    runtime.require()
    cases = json.loads((args.audit_dir/'cases.json').read_text())
    if args.phone_captures_only:
        cases = [c for c in cases if c['kind']=='phone_capture']
    if args.limit:
        cases = cases[:args.limit]
    baseline = {r['case']['id']:r for r in
        (json.loads(line) for line in args.baseline.read_text().splitlines())} if args.baseline else {}
    records = []
    try:
        with (args.audit_dir/'ocr-framing.jsonl').open('x') as handle:
            for number, case in enumerate(cases,1):
                path = args.audit_dir/case['photo_file']
                assert path.resolve().is_relative_to(args.audit_dir.resolve())
                assert hashlib.sha256(path.read_bytes()).hexdigest()==case['sha256']
                pair = {}
                if case['id'] in baseline:
                    old = baseline[case['id']]
                    assert old['case']['sha256']==case['sha256']
                    assert all(old['parallel']['versions'].get(k)==v for k,v in runtime.versions().items() if k!='ocr')
                    pair['before'] = old['parallel']
                modes = (True,) if pair else ((False,True) if number%2 else (True,False))
                details = {}
                for enabled in modes:
                    settings.ocr_complete_frame_first=enabled
                    label = 'after' if enabled else 'before'
                    results = sqlite3.connect(':memory:')
                    results.row_factory = sqlite3.Row
                    init_results(results)
                    results.execute("INSERT INTO sessions VALUES ('ocr-framing','test','test')")
                    results.commit()
                    cv2.setRNGSeed(0)
                    try:
                        response = recognize_bytes(path.read_bytes(),settings=settings,runtime=runtime,
                            catalog=catalog,results=results,session_id='ocr-framing',language='auto',
                            store_capture=False).model_dump(mode='json')
                        evidence = json.loads(results.execute('SELECT ocr_json FROM scans WHERE id=?',
                            (response['id'],)).fetchone()['ocr_json'])
                        pair[label] = response
                        details[label] = {'passes':evidence.get('passes'),
                            'frame_selection':evidence.get('frame_selection')}
                    finally:
                        results.close()
                    assert runtime.grading_slots.acquire(timeout=10), 'Optional worker must stop without backlog'
                    runtime.grading_slots.release()
                    print(json.dumps({'case':case['id'],'number':number,'total':len(cases),'mode':label,
                        'card_id':identity(response),'status':response['status'],
                        'total_ms':response['timings_ms']['total_ms'],'ocr_ms':response['timings_ms']['ocr_ms'],
                        'complete_frame':evidence['frame_selection'].get('ocr_complete_frame_used'),
                        'passes':len(evidence.get('passes',[]))}),flush=True)
                record = {'case':case,**pair,'details':details}
                records.append(record)
                handle.write(json.dumps(record)+'\n'); handle.flush()
    finally:
        runtime.close(); catalog.close()
    scored = [r for r in records if r['case']['expected_card_ids']]
    def canonical(card_id):
        return 'en:'+card_id if card_id and ':' not in card_id else card_id
    lost = [r['case']['id'] for r in scored
        if canonical(identity(r['before'])) in r['case']['expected_card_ids']
        and canonical(identity(r['after'])) not in r['case']['expected_card_ids']]
    changed = [dict(case=r['case']['id'],before=identity(r['before']),after=identity(r['after']),
        before_status=r['before']['status'],after_status=r['after']['status']) for r in records
        if identity(r['before'])!=identity(r['after']) or r['before']['status']!=r['after']['status']]
    summary = {'photos':len(records),'counts':dict(Counter(r['case']['kind'] for r in records)),
        'scorable':len(scored), 'correct':{mode:sum(canonical(identity(r[mode])) in r['case']['expected_card_ids']
            for r in scored) for mode in ('before','after')}, 'lost_correct_matches':lost,
        'identity_or_status_changes':changed,
        'latency_ms':{mode:{field: {'median':round(statistics.median(r[mode]['timings_ms'][field] for r in records),2),
            'max':max(r[mode]['timings_ms'][field] for r in records)} for field in ('total_ms','ocr_ms')}
            for mode in ('before','after')},
        'complete_frame_used':sum(r['details']['after']['frame_selection'].get('ocr_complete_frame_used',False) for r in records),
        'peak_rss_mib':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1),
        'baseline_reused':bool(baseline),'versions':runtime.versions(),
        'limitations':'Saved captures are downsampled/recompressed JPEGs. Frozen corpus baseline reused if provided; not unseen accuracy or a latency SLA.'}
    (args.audit_dir/'ocr-framing-summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary),flush=True)
    assert not lost, 'Do not deploy: previously correct matches regressed'


if __name__=='__main__':
    main()
