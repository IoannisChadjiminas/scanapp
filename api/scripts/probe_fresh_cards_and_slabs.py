"""Unmodified local recognition on original frozen photos; no network or persistent writes."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import Settings
from app.db import init_results
from app.recognition.artwork import ArtworkIndex
from app.recognition.pipeline import recognize_bytes
from benchmark_printing_crops import load_readonly_runtime

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--code-snapshot',type=Path,required=True)
    parser.add_argument('--case-id',action='append',default=[],help='Diagnostic subset only; not a complete accuracy run')
    parser.add_argument('--diagnostics',type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    def hashes():
        paths=list((root/'api/app').rglob('*.py'))+list((root/'api/app/recognition/assets/grading-logos').glob('*'))
        return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}
    before=hashes()
    with args.code_snapshot.open('x') as handle:json.dump({'code_hashes':before,'unchanged_after_run':False},handle,indent=2)
    sources=json.loads(args.sources.read_text())
    # Source truth is never passed to recognize_bytes or retrieval/ranking.
    settings=Settings(data_dir=Path('/data'),catalogue_backend='sqlite',enable_matched=True,store_captures=False)
    source=sqlite3.connect('file:/data/catalog.sqlite?mode=ro',uri=True)
    catalog=sqlite3.connect(':memory:');source.backup(catalog);source.close()
    catalog.row_factory=sqlite3.Row;catalog.execute('PRAGMA query_only=ON')
    runtime=load_readonly_runtime(settings,catalog)
    runtime.artwork_index=ArtworkIndex.load(Path('/data/artwork'),snapshot=runtime.snapshot,
        model_path=settings.dinov2_path,known_ids={r[0] for r in catalog.execute('SELECT id FROM cards')},
        known_languages={r[0]:r[1] or 'en' for r in catalog.execute('SELECT id,language FROM cards')})
    results=sqlite3.connect(':memory:');results.row_factory=sqlite3.Row;init_results(results)
    results.execute("INSERT INTO sessions VALUES ('fresh100','test','test')");results.commit()
    if args.diagnostics:
        import app.recognition.pipeline as pipeline
        args.diagnostics.mkdir(parents=True,exist_ok=False)
        def capture(**record):
            folder=args.diagnostics/current_id;folder.mkdir(exist_ok=True)
            record['query_image'].save(folder/'query.png')
            keep={k:record[k] for k in ('image_stats','ocr','predicted','visual','timings','versions')}
            (folder/'scan.json').write_text(json.dumps(keep,indent=2))
        pipeline.save_scan_capture=capture
    photos=[p for p in sources['photos'] if not args.case_id or p['id'] in args.case_id]
    if args.case_id and set(args.case_id)!={p['id'] for p in photos}:
        parser.error('Unknown diagnostic case ID')
    for photo in photos:
        current_id=photo['id']
        payload=(root/photo['path']).read_bytes()
        assert hashlib.sha256(payload).hexdigest()==photo['sha256']
        response=recognize_bytes(payload,settings=settings,runtime=runtime,catalog=catalog,results=results,
            session_id='fresh100',skip_detect=False,language='auto',store_capture=bool(args.diagnostics))
        print(json.dumps({'id':photo['id'],'response':response.model_dump(mode='json')}),flush=True)
    assert before==hashes(),'runtime changed during benchmark; discard run'
    args.code_snapshot.write_text(json.dumps({'code_hashes':before,'unchanged_after_run':True,
        'sources_sha256':hashlib.sha256(args.sources.read_bytes()).hexdigest(),
        'evaluation_scope':'diagnostic_subset' if args.case_id else 'complete_frozen_batch',
        'case_ids':[p['id'] for p in photos]},indent=2))

if __name__=='__main__':main()
