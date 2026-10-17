"""Paired recognition regression, with in-memory results and read-only data.

Run only in an isolated resource-limited API-image container. The manifest
freezes photo hashes, panel membership and existing expected card identities.
Grading is disabled: this runner measures recognition, not grade extraction.
"""
import argparse
from copy import deepcopy
from contextlib import contextmanager
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
from app.config import Settings
from app.db import init_catalog, init_results
from app.planetscale import CloudCatalogConnection, load_cloud_catalogue
from app.recognition.artifacts import sha256_file
from app.recognition.runtime import Runtime
from app.recognition import rank, pipeline, ocr_budget, ocr_framing


@contextmanager
def collector_rules(extractor):
    # These are every importer of the only changed pre-existing recognition
    # function. New OCR/layout paths are separately gated by the recovery flag.
    # No grading worker or concurrent scan runs during this paired comparison.
    modules=(rank, pipeline, ocr_budget, ocr_framing)
    previous=[m.extract_collector_candidates for m in modules]
    try:
        for module in modules:
            module.extract_collector_candidates=extractor
        yield
    finally:
        for module, original in zip(modules, previous):
            module.extract_collector_candidates=original


@contextmanager
def exact_pixel_inference_cache(runtime):
    """Reuse literal model outputs only within this one paired photograph.

    Both recognition policies still run fully. Different crops, resize filters,
    rotations, readers and model preprocessing are different cache keys. No
    identity decisions, confidence values or cross-photo evidence are cached.
    """
    observations={}
    vectors={}
    originals=[]
    def pixels(image):
        return image.mode,image.size,hashlib.sha256(image.tobytes()).digest()
    readers=[runtime.ocr,getattr(runtime.ocr,'region_reader',None)]
    for reader in readers:
        if reader is None:continue
        original=reader._run
        def read(image, original=original, reader=reader):
            key=(id(reader),*pixels(image))
            if key not in observations:observations[key]=deepcopy(original(image))
            return deepcopy(observations[key])
        originals.append((reader,'_run',original));reader._run=read
    embedder=runtime.embedder
    original_embed,original_many=embedder.embed,embedder.embed_many
    def embed(image,mode):
        key=(mode,*pixels(image))
        if key not in vectors:vectors[key]=original_embed(image,mode).copy()
        return vectors[key].copy()
    def embed_many(images,mode):
        keys=[(mode,*pixels(image)) for image in images]
        if not all(k in vectors for k in keys):
            for key,vector in zip(keys,original_many(images,mode)):
                vectors[key]=vector.copy()
        return [vectors[k].copy() for k in keys]
    originals.extend([(embedder,'embed',original_embed),(embedder,'embed_many',original_many)])
    embedder.embed,embedder.embed_many=embed,embed_many
    try:yield
    finally:
        for obj,name,method in originals:setattr(obj,name,method)


def normalize_card(value):
    return 'en:'+value if value and ':' not in value else value


def summarize(rows):
    panels={}
    regressions=[]
    improvements=[]
    changes=[]
    for row in rows:
        before,after=row['baseline'],row['candidate']
        a,b=normalize_card(before['card_id']),normalize_card(after['card_id'])
        expected=row['case']['expected_card_ids']
        members=row['case'].get('members') or [dict(panel=p,expected_card_ids=expected) for p in row['case']['panels']]
        lost=any(m['expected_card_ids'] and a in m['expected_card_ids'] and b not in m['expected_card_ids'] for m in members)
        improved=any(m['expected_card_ids'] and a not in m['expected_card_ids'] and b in m['expected_card_ids'] for m in members)
        if lost:regressions.append(row['case']['id'])
        if improved:improvements.append(row['case']['id'])
        if (a,before['status']) != (b,after['status']):
            changes.append(dict(id=row['case']['id'],before=[a,before['status']],
                                after=[b,after['status']],expected=expected))
        for member in members:
            name=member['panel'];truth=member['expected_card_ids']
            stats=panels.setdefault(name,dict(photos=0,scorable=0,baseline_correct=0,
                candidate_correct=0,lost_correct=0,improvements=0,changed_identity_or_status=0))
            stats['photos']+=1
            stats['scorable']+=bool(truth)
            stats['baseline_correct']+=bool(truth and a in truth)
            stats['candidate_correct']+=bool(truth and b in truth)
            stats['lost_correct']+=bool(truth and a in truth and b not in truth)
            stats['improvements']+=bool(truth and a not in truth and b in truth)
            stats['changed_identity_or_status']+=((a,before['status']) != (b,after['status']))
    return dict(completed=len(rows),panels=panels,lost_correct_matches=regressions,
        improvements=improvements,changed_identity_or_status=changes)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--photos-root',type=Path,required=True)
    parser.add_argument('--baseline-rank',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--limit',type=int)
    args=parser.parse_args()
    manifest=json.loads(args.manifest.read_text())
    cases=manifest['cases']
    if args.limit:cases=cases[:args.limit]
    root=args.photos_root.resolve()
    for case in cases:
        photo=(root/case['photo_file']).resolve()
        if not photo.is_relative_to(root) or sha256_file(photo)!=case['sha256']:
            raise ValueError('Frozen photo hash/path mismatch: '+case['id'])
    spec=importlib.util.spec_from_file_location('layout_regression_original_rank',args.baseline_rank)
    original=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=original
    spec.loader.exec_module(original)
    candidate_extractor=rank.extract_collector_candidates
    rows=[]
    if args.output.exists():
        if not args.resume:parser.error('output exists; use --resume for the same frozen run')
        rows=[json.loads(line) for line in args.output.read_text().splitlines() if line]
        lookup={c['id']:c for c in cases}
        if any(r['case']!=lookup.get(r['case']['id']) for r in rows):
            raise ValueError('Resume manifest differs')
    completed={r['case']['id'] for r in rows}
    cv2.setNumThreads(1)
    # Text visualization is unused; avoid font network requests during OCR.
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path=lambda self,*a,**k:'unused-regression-drawing-font'
    settings=Settings().model_copy(update=dict(store_captures=False,use_grading=False,
        parallel_grading=False,grading_at_card_deadline=False,structured_layout_recovery=True))
    catalog=sqlite3.connect(':memory:',factory=CloudCatalogConnection)
    catalog.row_factory=sqlite3.Row;init_catalog(catalog)
    with sqlite3.connect(f'file:{settings.catalog_sqlite}?mode=ro',uri=True) as source:
        catalog.executemany('INSERT INTO set_totals VALUES(?,?,?,?)',
            source.execute('SELECT language,set_id,official_total,fetched_at FROM set_totals'))
    catalog.commit()
    runtime=Runtime(settings)
    metadata_path=args.output.with_suffix('.metadata.json')
    summary_path=args.output.with_suffix('.summary.json')
    try:
        snapshot=load_cloud_catalogue(settings,catalog)
        metadata=dict(manifest_sha256=sha256_file(args.manifest),baseline_rank_sha256=sha256_file(args.baseline_rank),
            candidate_rank_sha256=sha256_file(Path(rank.__file__)),catalogue_version=snapshot.catalogue_version,
            catalogue_import_id=settings.planetscale_import_id,thresholds=runtime.threshold_config(),
            grading_enabled=False,catalogue_writes=False,operational_writes=False,
            limitations='Known convenience photos; baseline recovery off with original rank extractor. Not unseen accuracy, grading QA or a latency benchmark.')
        if metadata_path.exists() and json.loads(metadata_path.read_text())!=metadata:
            raise ValueError('Resume runtime/catalogue changed')
        metadata_path.write_text(json.dumps(metadata,indent=2))
        runtime.load(snapshot);runtime.bind_card_languages(catalog);runtime.require()
        print(json.dumps(dict(phase='ready',photos=len(cases),already_completed=len(rows))),flush=True)
        with args.output.open('a' if args.resume else 'x') as handle:
            for case in cases:
                if case['id'] in completed:continue
                with exact_pixel_inference_cache(runtime):
                    pair=evaluate_pair(case, root, settings, runtime, catalog, original.extract_collector_candidates, candidate_extractor)
                row=dict(case=case,inference_cache='exact-pixels-within-paired-photo',**pair)
                handle.write(json.dumps(row)+'\n');handle.flush();rows.append(row)
                summary=summarize(rows);summary['total']=len(cases)
                summary_path.write_text(json.dumps(summary,indent=2))
                print(json.dumps(dict(completed=len(rows),total=len(cases),id=case['id'],
                    before=[pair['baseline']['card_id'],pair['baseline']['status']],
                    after=[pair['candidate']['card_id'],pair['candidate']['status']],
                    lost_correct=len(summary['lost_correct_matches']))),flush=True)
                gc.collect()
        summary=summarize(rows);summary['total']=len(cases)
        summary_path.write_text(json.dumps(summary,indent=2))
        print(json.dumps(summary),flush=True)
    finally:runtime.close();catalog.close()


def evaluate_pair(case, root, settings, runtime, catalog, baseline_extractor, candidate_extractor):
    pair={}
    for enabled in (False,True):
        config=settings.model_copy(update={'structured_layout_recovery':enabled})
        results=sqlite3.connect(':memory:');results.row_factory=sqlite3.Row
        init_results(results)
        results.execute("INSERT INTO sessions VALUES('photo-regression','test','test')")
        cv2.setRNGSeed(0)
        started=time.perf_counter()
        try:
            with collector_rules(candidate_extractor if enabled else baseline_extractor):
                response=pipeline.recognize_bytes((root/case['photo_file']).read_bytes(),
                    settings=config,runtime=runtime,catalog=catalog,results=results,
                    session_id='photo-regression',store_capture=False,graded=False)
            raw=json.loads(results.execute('SELECT ocr_json FROM scans WHERE id=?',(response.id,)).fetchone()[0])
            pair['candidate' if enabled else 'baseline']=dict(
                card_id=response.best_match.card_id if response.best_match else None,
                status=response.status.value,response=response.model_dump(mode='json'),
                evidence=raw,elapsed_ms=round((time.perf_counter()-started)*1000))
        finally:results.close()
    return pair

if __name__=='__main__':main()
