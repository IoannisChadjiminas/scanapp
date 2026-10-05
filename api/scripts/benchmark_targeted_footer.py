"""Offline crop experiment, never an active server setting or catalogue write."""
import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import statistics
import sys
import time

from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app.recognition.ocr as ocr_module
from app.recognition.artifacts import sha256_file
from app.recognition.rank import extract_collector_candidates


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit-dir', type=Path, required=True)
    p.add_argument('--models', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--per-kind', type=int, default=10)
    a = p.parse_args(); counts = Counter(); cases = []
    for case in json.loads((a.audit_dir/'cases.json').read_text()):
        if counts[case['kind']] < a.per_kind:
            cases.append(case); counts[case['kind']] += 1
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path = lambda self,*args,**kwargs: 'unused-benchmark-font'
    reader = ocr_module.CardOcr(str(a.models/'PP-OCRv6_det_small.onnx'),
        str(a.models/'PP-OCRv6_rec_small.onnx'), str(a.models/'ch_ppocr_mobile_v2.0_cls_mobile.onnx'), 1, 1)
    original_region = ocr_module._region
    records = []
    with a.output.open('x') as handle:
        for index, case in enumerate(cases):
            path = a.audit_dir/case['photo_file']; assert sha256_file(path) == case['sha256']
            with Image.open(path) as photo: image = photo.convert('RGB')
            outputs = {}
            for narrow in ([False, True] if index % 2 == 0 else [True, False]):
                ocr_module._region = (lambda image,y0,y1:
                    original_region(image, .88 if y0 == .82 else y0, y1)) if narrow else original_region
                start = time.perf_counter()
                try: observed = reader.read(image)
                finally: ocr_module._region = original_region
                outputs[narrow] = dict(ms=(time.perf_counter()-start)*1000, ocr=asdict(observed),
                    numbers=[asdict(hit) for hit in extract_collector_candidates([], hits=observed.hits)])
            before, after = outputs[False], outputs[True]
            same = (before['ocr']['name_text']==after['ocr']['name_text'] and before['numbers']==after['numbers'])
            row = dict(case=case, before=before, after=after, identity_evidence_equal=same)
            records.append(row); handle.write(json.dumps(row)+'\n'); handle.flush()
            print(json.dumps(dict(id=case['id'], number=index+1, total=len(cases), equal=same,
                before_ms=round(before['ms']), after_ms=round(after['ms']))), flush=True)
    summary = dict(photos=len(records), identity_evidence_equal=sum(r['identity_evidence_equal'] for r in records),
        changed=[r['case']['id'] for r in records if not r['identity_evidence_equal']],
        median_saved_ms=statistics.median(r['before']['ms']-r['after']['ms'] for r in records),
        deployment_eligible=all(r['identity_evidence_equal'] for r in records),
        limitations='OCR component experiment; even equal fields require a full matching replay before activation.')
    a.output.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2)); print(json.dumps(summary), flush=True)


if __name__ == '__main__': main()
