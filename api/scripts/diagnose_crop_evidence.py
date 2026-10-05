"""Offline forced-frame diagnostic, not accuracy evaluation or runtime policy."""
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from app.config import Settings
from app.db import init_results
from app.recognition.pipeline import _recognize_bytes_once
from benchmark_printing_crops import load_readonly_runtime

settings=Settings(data_dir=Path('/data'),catalogue_backend='sqlite',
    artwork_bundle_dir=None,enable_matched=True,store_captures=False)
catalog=sqlite3.connect('file:/data/catalog.sqlite?mode=ro',uri=True)
catalog.row_factory=sqlite3.Row
runtime=load_readonly_runtime(settings,catalog)
results=sqlite3.connect(':memory:')
results.row_factory=sqlite3.Row
init_results(results)
results.execute("INSERT INTO sessions VALUES ('diagnostic','test','test')")
results.commit()
for raw in sys.argv[1:]:
    path=Path(raw)
    with Image.open(path) as image:
        evaluation=_recognize_bytes_once(path.read_bytes(),settings=settings,runtime=runtime,
            catalog=catalog,results=results,session_id='diagnostic',store_capture=False,
            _frame_override=('line_diagnostic',image.convert('RGB')))
    print(json.dumps({'file':path.name,'status':evaluation.response.status.value,
        'best_match':evaluation.response.best_match.model_dump() if evaluation.response.best_match else None,
        'lead':evaluation.lead,'name_confidence':evaluation.name_confidence,
        'numbers':[vars(h) for h in evaluation.numbers],
        'evidence':{k:v for k,v in evaluation.evidence.items() if k in
            ('hits','local_artwork_matches','framing_review_supported','query_size')},
        'ocr':evaluation.response.ocr.model_dump()},ensure_ascii=False),flush=True)
