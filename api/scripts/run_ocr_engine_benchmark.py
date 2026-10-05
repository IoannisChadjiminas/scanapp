"""Offline current server engine on frozen inputs; model latency excludes I/O."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.ocr import CardOcr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--models', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path = lambda self, *a, **k: 'unused-benchmark-drawing-font'
    model_files = ['PP-OCRv6_det_small.onnx', 'PP-OCRv6_rec_small.onnx', 'ch_ppocr_mobile_v2.0_cls_mobile.onnx']
    reader = CardOcr(*(str(args.models / name) for name in model_files), 1, 1)
    requests = json.loads((args.audit / 'inputs.json').read_text())
    if args.limit:
        ids = list(dict.fromkeys(r['id'] for r in requests))[:args.limit]
        requests = [r for r in requests if r['id'] in ids]
    # Warm-up is recorded separately, never silently removed from a cold-start claim.
    with Image.open(args.audit / requests[0]['file']) as image:
        started = time.perf_counter()
        reader.engine(np.asarray(image.convert('RGB')))
        warmup_ms = (time.perf_counter() - started) * 1000
    with args.output.open('x') as handle:
        for number, request in enumerate(requests, 1):
            file = args.audit / request['file']
            assert hashlib.sha256(file.read_bytes()).hexdigest() == request['sha256']
            with Image.open(file) as image:
                pixels = np.asarray(image.convert('RGB'))
            started = time.perf_counter()
            result = reader.engine(pixels)
            elapsed = (time.perf_counter() - started) * 1000
            texts = getattr(result, 'txts', None)
            scores = getattr(result, 'scores', None)
            boxes = getattr(result, 'boxes', None)
            lines = []
            for index, value in enumerate(texts if texts is not None else []):
                lines.append(dict(text=value, confidence=float(scores[index]) if scores is not None else None,
                                  box=np.asarray(boxes[index]).tolist() if boxes is not None else None))
            record = dict(**request, engine='server_ppocr_v6', ms=round(elapsed, 2), lines=lines)
            handle.write(json.dumps(record, ensure_ascii=False) + '\n'); handle.flush()
            if request['profile'] == 'footer':
                print(json.dumps(dict(photo=request['id'], completed=number, total=len(requests))), flush=True)
    args.output.with_suffix('.metadata.json').write_text(json.dumps(dict(
        warmup_ms=warmup_ms, ort_intra_threads=1, ort_inter_threads=1,
        models={name:hashlib.sha256((args.models / name).read_bytes()).hexdigest() for name in model_files},
        scope='Engine extraction only, not adaptive production pipeline or final match latency'), indent=2))


if __name__ == '__main__':
    main()
