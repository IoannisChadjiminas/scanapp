"""Offline frozen replay from the validated repeatable-read export. No external writes.
Derived from probe_reference_recovery.py; runtime, feature and model guards are unchanged.
"""
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
    p.add_argument('--case-id',action='append',default=[],help='Replay only these frozen case IDs')
    p.add_argument('--adaptive-footer',action='store_true')
    p.add_argument('--parallel-regions',action='store_true')
    a=p.parse_args();cv2.setNumThreads(1)
    cases=json.loads((a.audit_dir/'cases.json').read_text())
    if a.reported_only:cases=[c for c in cases if c['kind']=='reported_phone']
    if a.case_id:cases=[c for c in cases if c['id'] in a.case_id]
    assert cases and (not a.case_id or len(cases)==len(set(a.case_id)))
    # Verify the entire photo inventory before loading large artifacts or doing
    # any scans; mixed frozen panels can contain more than one photo directory.
    for case in cases:
        assert sha256_file(a.audit_dir/case['photo_file'])==case['sha256']
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path=lambda self,*args,**kwargs:'unused-benchmark-drawing-font'
    settings=Settings(store_captures=False,portfolio_database_url='',enable_matched=True,
        parallel_grading=True,grading_at_card_deadline=True,ocr_complete_frame_first=True)
    settings.ocr_adaptive_footer = a.adaptive_footer
    settings.ocr_parallel_regions = a.parallel_regions
    manifest=json.loads((a.candidate/'vectors/manifest.json').read_text())
    from app.recognition.artifacts import ArtifactSnapshot, validate_embeddings
    offline_embeddings=np.load(a.candidate/'vectors/embeddings.npy',mmap_mode='r')
    offline_ids=np.load(a.candidate/'vectors/embedding_card_ids.npy')
    validate_embeddings(offline_embeddings,offline_ids)
    snapshot=ArtifactSnapshot(preprocess_config=manifest['preprocess_config'],use_ocr=manifest['use_ocr'],
        catalogue_version=manifest['catalogue_version'],model_revision=manifest['model_revision'],
        model_name=manifest['model_name'],embedding_dim=manifest['embedding_dim'],
        card_count=manifest['card_count'],indexed_count=manifest['indexed_count'],missing_images=manifest['missing_images'],
        embeddings_sha256=manifest['embeddings_sha256'],ids_sha256=manifest['ids_sha256'],
        embeddings=offline_embeddings,card_ids=offline_ids,manifest=manifest,bundle_dir=a.candidate/'vectors')
    full=a.candidate/'vectors'
    assert sha256_file(full/'embeddings.npy')==manifest['embeddings_sha256']
    assert sha256_file(full/'embedding_card_ids.npy')==manifest['ids_sha256']
    snapshot=replace(snapshot,embeddings=np.load(full/'embeddings.npy',mmap_mode='r'),
        card_ids=np.load(full/'embedding_card_ids.npy'),manifest=manifest,
        catalogue_version=manifest['catalogue_version'],indexed_count=manifest['indexed_count'],
        missing_images=manifest['missing_images'],embeddings_sha256=manifest['embeddings_sha256'],
        ids_sha256=manifest['ids_sha256'])
    source=sqlite3.connect(f'file:{a.candidate}/catalog.sqlite?mode=ro',uri=True)
    # The deployed cloud reader serves its validated snapshot from memory.
    # Disk-backed candidate scans add unrelated repeated listing-query I/O.
    catalog=sqlite3.connect(':memory:',factory=CloudCatalogConnection)
    catalog.row_factory=sqlite3.Row
    source.backup(catalog);source.close()
    settings.reference_features_dir=a.features_dir;settings.artwork_bundle_dir=a.candidate/'artwork'
    from app.planetscale import protect_catalogue
    protect_catalogue(catalog)
    catalog.catalogue_readonly=True
    runtime=Runtime(settings);runtime.load(snapshot);runtime.bind_card_languages(catalog);runtime.require()
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
                assert runtime.grading_slots.acquire(timeout=60),'Optional work must stop without backlog'
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
