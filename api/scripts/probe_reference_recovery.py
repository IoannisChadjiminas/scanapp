"""Read-only candidate regression. No persistent sessions/scans or publication."""
import argparse
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import sys
import time
import cv2
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.db import init_catalog,init_results
from app.planetscale import load_cloud_catalogue, CloudCatalogConnection
from app.recognition.artifacts import sha256_file
from app.recognition.pipeline import recognize_bytes
from app.recognition.runtime import Runtime


def card(response):
    cid=(response.get('best_match') or {}).get('card_id')
    return 'en:'+cid if cid and ':' not in cid else cid


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit-dir',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--baseline',type=Path)
    p.add_argument('--reported-only',action='store_true')
    p.add_argument('--features-dir',type=Path,required=True)
    p.add_argument('--output-name',default=None)
    a=p.parse_args();cv2.setNumThreads(1)
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path=lambda self,*args,**kwargs:'unused-benchmark-drawing-font'
    settings=Settings(store_captures=False,portfolio_database_url='',enable_matched=True,
        parallel_grading=True,grading_at_card_deadline=True,ocr_complete_frame_first=True)
    parent=sqlite3.connect(':memory:');parent.row_factory=sqlite3.Row;init_catalog(parent)
    snapshot=load_cloud_catalogue(settings,parent);parent.close()
    manifest=json.loads((a.candidate/'vectors/manifest.json').read_text())
    full=a.candidate/'vectors'
    assert sha256_file(full/'embeddings.npy')==manifest['embeddings_sha256']
    assert sha256_file(full/'embedding_card_ids.npy')==manifest['ids_sha256']
    snapshot=replace(snapshot,embeddings=np.load(full/'embeddings.npy',mmap_mode='r'),
        card_ids=np.load(full/'embedding_card_ids.npy'),manifest=manifest,
        catalogue_version=manifest['catalogue_version'],indexed_count=manifest['indexed_count'],
        missing_images=manifest['missing_images'],embeddings_sha256=manifest['embeddings_sha256'],
        ids_sha256=manifest['ids_sha256'])
    catalog=sqlite3.connect(f'file:{a.candidate}/catalog.sqlite?mode=ro',uri=True,
                           factory=CloudCatalogConnection);catalog.row_factory=sqlite3.Row
    settings.reference_features_dir=a.features_dir;settings.artwork_bundle_dir=a.candidate/'artwork'
    runtime=Runtime(settings);runtime.load(snapshot);runtime.bind_card_languages(catalog);runtime.require()
    cases=json.loads((a.audit_dir/'cases.json').read_text())
    if a.reported_only:cases=[c for c in cases if c['kind']=='reported_phone']
    baseline={r['case']['id']:r['after'] for r in
        (json.loads(line) for line in a.baseline.read_text().splitlines())} if a.baseline else {}
    records=[]
    filename=a.output_name or ('reported.jsonl' if a.reported_only else 'regression.jsonl')
    assert Path(filename).name==filename and filename.endswith('.jsonl')
    output=a.audit_dir/filename
    try:
        with output.open('x') as handle:
            for number,case in enumerate(cases,1):
                path=a.audit_dir/case['photo_file'];assert sha256_file(path)==case['sha256']
                result=sqlite3.connect(':memory:');result.row_factory=sqlite3.Row;init_results(result)
                result.execute("INSERT INTO sessions VALUES('recovery-probe','test','test')");result.commit()
                cv2.setRNGSeed(0)
                response=recognize_bytes(path.read_bytes(),settings=settings,runtime=runtime,catalog=catalog,
                    results=result,session_id='recovery-probe',store_capture=False).model_dump(mode='json')
                evidence=json.loads(result.execute('SELECT ocr_json FROM scans WHERE id=?',(response['id'],)).fetchone()[0])
                result.close()
                record=dict(case=case,after=response,evidence=evidence,before=baseline.get(case['id']))
                records.append(record);handle.write(json.dumps(record)+'\n');handle.flush()
                print(json.dumps(dict(case=case['id'],number=number,total=len(cases),card_id=card(response),
                    status=response['status'],total_ms=response['timings_ms']['total_ms'],
                    cache_hits=response['timings_ms'].get('ocr_cache_hits'),stamp=evidence.get('stamp_printing_hint'))),flush=True)
                assert runtime.grading_slots.acquire(timeout=10),'Optional work must stop without backlog'
                runtime.grading_slots.release()
    finally:runtime.close();catalog.close()
    scored=[r for r in records if r['case']['expected_card_ids']]
    lost=[r['case']['id'] for r in scored if r['before'] and card(r['before']) in r['case']['expected_card_ids']
          and card(r['after']) not in r['case']['expected_card_ids']]
    summary=dict(photos=len(records),counts=dict(Counter(r['case']['kind'] for r in records)),
        correct_by_kind={kind:dict(correct=sum(card(r['after']) in r['case']['expected_card_ids'] for r in scored if r['case']['kind']==kind),
            scorable=sum(r['case']['kind']==kind for r in scored)) for kind in {r['case']['kind'] for r in records}},
        lost_correct_matches=lost,versions=runtime.versions(),baseline_reused=bool(baseline),
        grading_changes=[dict(case=r['case']['id'],before=r['before'].get('grading'),after=r['after'].get('grading'))
            for r in records if r['before'] and any(r['before'].get('grading',{}).get(k)!=r['after'].get('grading',{}).get(k)
                for k in ('company','grade','certification_number'))],
        limitations='Frozen regression and saved/recompressed phone photos; not unseen accuracy or a latency guarantee')
    output.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)
    assert not lost,'Previously correct matches regressed'
    assert all(card(r['after']) in r['case']['expected_card_ids'] for r in records if r['case']['kind']=='reported_phone'), 'Reported cases still wrong'

if __name__=='__main__':main()
