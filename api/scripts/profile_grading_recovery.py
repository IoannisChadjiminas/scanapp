"""Read-only single-photo grading profile; no catalogue or results connection."""
import argparse
from collections import Counter
from functools import wraps
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.ocr import CardOcr
from app.recognition import label_vision
from staging_parallel_grading_probe import SessionProbe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-dir', type=Path, required=True)
    parser.add_argument('--case-id', required=True)
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument('--logo-companies', nargs='+', choices=['ace','ags','tag','psa','beckett'],
                        help='Diagnostic-only logo-template subset; does not change literal OCR parsing')
    args = parser.parse_args()
    cv2.setNumThreads(1)
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path = lambda self, *a, **k: 'unused-benchmark-drawing-font'
    reader = CardOcr('/data/models/PP-OCRv6_det_small.onnx',
                     '/data/models/PP-OCRv6_rec_small.onnx',
                     '/data/models/ch_ppocr_mobile_v2.0_cls_mobile.onnx', 1, 1)
    if args.logo_companies:
        masks = label_vision._logo_masks()
        selected = {key:value for key,value in masks.items()
                    if key.split('-')[0] in args.logo_companies}
        assert selected
        label_vision._logo_masks = lambda: selected
    rows = [json.loads(line) for line in (args.audit_dir/'parallel-paired.jsonl').read_text().splitlines()]
    record = next(r for r in rows if r['case']['id'] == args.case_id)
    path = args.audit_dir/record['case']['photo_file']
    assert path.resolve().is_relative_to(args.audit_dir.resolve())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record['case']['sha256']
    events, totals, counts = [], Counter(), Counter()
    from threading import Lock
    for component in ('det', 'cls', 'rec'):
        model = getattr(reader.engine, 'text_'+component)
        model.session = SessionProbe(model.session, component, events, Lock())

    def timed(name, function):
        @wraps(function)
        def call(*a, **k):
            start = time.perf_counter()
            try:
                return function(*a, **k)
            finally:
                totals[name] += (time.perf_counter()-start)*1000
                counts[name] += 1
        return call
    for name in ('_logo_matches', 'label_panels', 'text_label_panel', 'contrast_label', 'grade_regions'):
        setattr(label_vision, name, timed(name, getattr(label_vision, name)))
    cv2.matchTemplate = timed('matchTemplate_nested_in_logo', cv2.matchTemplate)
    reader._grading_lines = timed('grading_lines_includes_ocr', reader._grading_lines)
    reader._grading_tokens = timed('grading_tokens_includes_ocr', reader._grading_tokens)
    reports = []
    with Image.open(path) as image:
        for number in range(args.repeats):
            totals.clear(); counts.clear(); events.clear()
            start = time.perf_counter()
            result = reader.read_grading(image).model_dump(mode='json')
            elapsed = (time.perf_counter()-start)*1000
            model_ms = sum(e['ms'] for e in events)
            logo_ms = totals['_logo_matches']
            memory = {}
            for name in ('memory.current','memory.peak','memory.swap.current','memory.events'):
                p = Path('/sys/fs/cgroup')/name
                if p.exists():
                    memory[name] = p.read_text().strip()
            report = {'case_id':args.case_id, 'repeat':number+1, 'total_ms':round(elapsed,2),
                'diagnostic_logo_companies': args.logo_companies,
                'grading_unchanged':result == record['parallel']['grading'],
                'function_ms':{k:round(v,2) for k,v in totals.items()}, 'calls':dict(counts),
                'ocr_model_ms':round(model_ms,2), 'logo_matching_ms':round(logo_ms,2),
                'other_ms_excluding_logo_and_ocr_models':round(elapsed-model_ms-logo_ms,2),
                'memory':memory, 'grading':result,
                'note':'Nested function times must not be added together; isolated single-reader test, not complete live scan latency.'}
            reports.append(report)
            print(json.dumps(report), flush=True)
    suffix = '-'+ '-'.join(args.logo_companies) if args.logo_companies else ''
    with (args.audit_dir/('grading-recovery-profile'+suffix+'.json')).open('x') as handle:
        json.dump(reports,handle,indent=2)
    assert all(r['grading_unchanged'] for r in reports)


if __name__ == '__main__':
    main()
