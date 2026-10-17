"""Compare recovery off/on with real models and a read-only cloud snapshot.

Run from a matching API image with its configured models/reference bundles.
Catalogue loading uses the existing guarded read-only integration. All scan
results live in SQLite memory; captures, feedback and price reads stay off.
Retained review JPEGs are lossy copies, not original upload bytes.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.db import init_catalog, init_results
from app.planetscale import CloudCatalogConnection, load_cloud_catalogue
from app.recognition.artifacts import sha256_file
from app.recognition.pipeline import recognize_bytes
from app.recognition.runtime import Runtime


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,action='append',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        parser.error('output must be a new file')
    settings=Settings().model_copy(update=dict(store_captures=False,use_grading=False,
        parallel_grading=False,grading_at_card_deadline=False,structured_layout_recovery=True))
    catalog=sqlite3.connect(':memory:',factory=CloudCatalogConnection)
    catalog.row_factory=sqlite3.Row
    results=sqlite3.connect(':memory:');results.row_factory=sqlite3.Row
    init_catalog(catalog);init_results(results)
    results.execute("INSERT INTO sessions VALUES('layout-replay','replay','replay')")
    # Set totals are a separate local cache; copy only this public metadata.
    with sqlite3.connect(f'file:{settings.catalog_sqlite}?mode=ro',uri=True) as source:
        for row in source.execute('SELECT language,set_id,official_total,fetched_at FROM set_totals'):
            catalog.execute('INSERT INTO set_totals VALUES(?,?,?,?)',tuple(row))
    catalog.commit()
    runtime=Runtime(settings)
    try:
        snapshot=load_cloud_catalogue(settings,catalog)
        runtime.load(snapshot);runtime.bind_card_languages(catalog)
        if not runtime.ready:
            raise RuntimeError('Replay runtime is not ready')
        rows=[]
        for path in args.image:
            comparisons={}
            for enabled in (False,True):
                runtime.ocr.compact_footer_recovery=enabled
                config=settings.model_copy(update={'structured_layout_recovery':enabled})
                response=recognize_bytes(path.read_bytes(),settings=config,runtime=runtime,
                    catalog=catalog,results=results,session_id='layout-replay',store_capture=False,
                    graded=False)
                raw=results.execute('SELECT ocr_json,timings_json FROM scans WHERE id=?',(response.id,)).fetchone()
                evidence=json.loads(raw['ocr_json'])
                comparisons['candidate' if enabled else 'baseline']=dict(
                    status=response.status.value,
                    card_id=response.best_match.card_id if response.best_match else None,
                    confidence=response.confidence.model_dump(mode='json'),
                    collector_text=evidence.get('collector_text'),
                    status_reasons=evidence['status_reasons'],
                    layout_matches=evidence['layout_matches'],
                    layout_review_supported=evidence['layout_review_supported'],
                    ocr_passes=evidence['passes'],timings=json.loads(raw['timings_json']))
                print(json.dumps(dict(image=path.name,enabled=enabled,
                    status=response.status.value,
                    card_id=response.best_match.card_id if response.best_match else None)),flush=True)
            rows.append(dict(image=path.name,sha256=sha256_file(path),**comparisons))
        report=dict(cases=rows,thresholds=runtime.threshold_config(),
            catalogue_version=snapshot.catalogue_version,
            catalogue_writes=False,operational_writes=False,capture_writes=False,
            limitations='Retained review JPEGs; sequential warm-cache replay, not a latency benchmark or a general accuracy estimate.')
        with args.output.open('x') as handle:
            json.dump(report,handle,indent=2)
    finally:
        runtime.close();catalog.close();results.close()


if __name__=='__main__':
    main()
