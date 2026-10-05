"""Pair CPU recognition batch sizes on frozen pixels, without changing models.

No service, catalogue, result database, thresholds, or image pixels are changed.
This is a selection pilot, not a deployment or end-to-end accuracy claim.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.ocr import CardOcr


def observation(result):
    texts = getattr(result, 'txts', None)
    scores = getattr(result, 'scores', None)
    return dict(texts=list(texts) if texts is not None else [],
                scores=[float(s) for s in scores] if scores is not None else [],
                stages_ms=[round(float(t) * 1000, 3) if t is not None else None
                           for t in getattr(result, 'elapse_list', [])])


def compare(reference, candidate):
    same_text = reference['texts'] == candidate['texts']
    compatible = same_text and len(reference['scores']) == len(candidate['scores'])
    deltas = [abs(a-b) for a, b in zip(reference['scores'], candidate['scores'])] if compatible else []
    crossings = [threshold for threshold in (.50, .55, .70, .85, .90, .95)
                 if compatible and any((a >= threshold) != (b >= threshold)
                     for a, b in zip(reference['scores'], candidate['scores']))]
    return dict(equal_text=same_text, equal_score_count=compatible,
                max_score_delta=max(deltas, default=0.) if compatible else None,
                confidence_threshold_crossings=crossings)


def distribution(values):
    values = sorted(values)
    return dict(n=len(values), median_ms=round(statistics.median(values), 2),
                p95_ms=round(values[math.ceil(.95 * len(values))-1], 2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--models', type=Path, default=Path('/data/models'))
    p.add_argument('--per-stratum', type=int, default=2)
    p.add_argument('--batch-sizes', nargs='+', type=int, default=[6, 1, 2])
    p.add_argument('--rounds', type=int, default=2)
    a = p.parse_args()
    assert a.rounds >= 1 and 6 in a.batch_sizes and all(b > 0 for b in a.batch_sizes)
    a.output.mkdir(parents=True, exist_ok=False)
    inputs = json.loads((a.inputs_dir / 'inputs.json').read_text())
    labels = json.loads((a.inputs_dir / 'labels.json').read_text())
    chosen = set()
    for predicate in (lambda r:r['truth']['kind']=='raw' and r['source']=='seller_photo',
                      lambda r:r['truth']['kind']=='slab',
                      lambda r:r['source']=='saved_phone_photo'):
        chosen.update(r['id'] for r in [r for r in labels if predicate(r)][:a.per_stratum])
    requests = [r for r in inputs if r['id'] in chosen]
    cv2.setNumThreads(1)
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path = lambda self, *args, **kwargs:'unused-profile-drawing-font'
    reader = CardOcr(*(str(a.models / name) for name in
        ('PP-OCRv6_det_small.onnx','PP-OCRv6_rec_small.onnx','ch_ppocr_mobile_v2.0_cls_mobile.onnx')), 1, 1)
    assert reader.engine.text_rec.rec_batch_num == 6, 'Baseline is not the current default'
    # Record engine configuration so a later repeat cannot silently change it.
    config = dict(min_side_len=reader.engine.min_side_len, max_side_len=reader.engine.max_side_len,
                  rec_image_shape=list(reader.engine.text_rec.rec_image_shape),
                  models={name:hashlib.sha256((a.models/name).read_bytes()).hexdigest()
                      for name in ('PP-OCRv6_det_small.onnx','PP-OCRv6_rec_small.onnx','ch_ppocr_mobile_v2.0_cls_mobile.onnx')})
    with Image.open(a.inputs_dir / requests[0]['file']) as image:
        reader.engine(np.asarray(image.convert('RGB')))
    records = []
    with (a.output/'paired.jsonl').open('x') as handle:
        for repeat in range(a.rounds):
            ordered = requests if repeat % 2 == 0 else list(reversed(requests))
            for index, request in enumerate(ordered):
                file = a.inputs_dir / request['file']
                assert hashlib.sha256(file.read_bytes()).hexdigest() == request['sha256']
                with Image.open(file) as image:
                    pixels = np.asarray(image.convert('RGB'))
                batches = a.batch_sizes if (index + repeat) % 2 == 0 else list(reversed(a.batch_sizes))
                paired = {}
                for batch in batches:
                    reader.engine.text_rec.rec_batch_num = batch
                    started = time.perf_counter()
                    out = reader.engine(pixels)
                    paired[str(batch)] = dict(**observation(out), ms=round((time.perf_counter()-started)*1000, 3))
                record = dict(input=request, round=repeat, results=paired,
                    comparison={str(b):compare(paired['6'], paired[str(b)]) for b in a.batch_sizes if b != 6})
                records.append(record)
                handle.write(json.dumps(record, ensure_ascii=False)+'\n'); handle.flush()
                print(json.dumps(dict(id=request['id'], profile=request['profile'], round=repeat,
                    timings={b:r['ms'] for b,r in paired.items()}, comparisons=record['comparison'])), flush=True)
    summary = dict(photos=len(chosen), profiles=len(requests), rounds=a.rounds, configuration=config,
                   results={}, limitations='Paired engine-only selection pilot on local CPU, not live staging latency or final matching accuracy.')
    for batch in a.batch_sizes:
        entry = dict(latency=distribution([r['results'][str(batch)]['ms'] for r in records]),
            by_profile={profile:distribution([r['results'][str(batch)]['ms'] for r in records if r['input']['profile']==profile])
                        for profile in ('full','card','title','footer')})
        if batch != 6:
            entry.update(text_changes=[dict(id=r['input']['id'], profile=r['input']['profile'], round=r['round'])
                for r in records if not r['comparison'][str(batch)]['equal_text']],
                threshold_crossings=[dict(id=r['input']['id'], profile=r['input']['profile'], round=r['round'])
                    for r in records if r['comparison'][str(batch)]['confidence_threshold_crossings']],
                paired_median_speedup=round(statistics.median(r['results']['6']['ms']/r['results'][str(batch)]['ms']
                    for r in records), 3))
        summary['results'][str(batch)] = entry
    (a.output/'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
