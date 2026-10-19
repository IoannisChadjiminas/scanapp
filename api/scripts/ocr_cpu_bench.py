"""Offline card-OCR CPU/accuracy bench for detector size and INT8 variants.

Runs CardOcr.read() on server-rectified cards from a frozen panel for one
variant and writes per-photo CPU time plus the OCR result fields that feed
recognition. Compare two outputs with --compare. Reads only; changes no flag.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageOps  # noqa: E402

from app.recognition.detect import detect_and_rectify  # noqa: E402
from app.recognition.ocr import CardOcr  # noqa: E402


def build(models, det_name, rec_name, side, limit_type):
    ocr = CardOcr(str(models / det_name), str(models / rec_name),
                  str(models / 'ch_ppocr_mobile_v2.0_cls_mobile.onnx'), 1, 1)
    if side is not None:
        det = ocr.engine.text_det
        for holder in (det, getattr(det, 'preprocess_op', None)):
            if holder is None:
                continue
            for attr in ('limit_side_len',):
                if hasattr(holder, attr):
                    setattr(holder, attr, side)
            if limit_type and hasattr(holder, 'limit_type'):
                holder.limit_type = limit_type
    return ocr


def run(a):
    panel = [json.loads(l) for l in a.panel.read_text().splitlines()]
    kinds = set(a.kinds.split(','))
    cases = [r['case'] for r in panel if r['case']['kind'] in kinds and r['case'].get('path')][:a.limit]
    ocr = build(a.models, a.det, a.rec, a.side, a.limit_type)
    if a.max_passes:
        # Counterfactual: engine calls past the budget return nothing, as if
        # the optional retry passes had been skipped.
        real_run, calls = ocr._run, [0]
        def budgeted(image):
            calls[0] += 1
            return real_run(image) if calls[0] <= a.max_passes else ([], [])
        ocr._run = budgeted
    rows = []
    for c in cases:
        image = ImageOps.exif_transpose(Image.open(a.root / c['path'])).convert('RGB')
        card, found = detect_and_rectify(image)
        if a.max_passes:
            calls[0] = 0
        cpu, wall = time.process_time(), time.perf_counter()
        res = ocr.read(card)
        rows.append(dict(id=c['id'], kind=c['kind'], found=found,
            cpu_ms=(time.process_time() - cpu) * 1000, wall_ms=(time.perf_counter() - wall) * 1000,
            passes=len(res.passes), name=res.name_text, collector=res.collector_text,
            lines=res.lines, hits=[[h.text, h.confidence, h.region] for h in res.hits],
            failed=res.failed))
        print(c['id'], round(rows[-1]['cpu_ms']), res.name_text, res.collector_text, flush=True)
        a.out.write_text('\n'.join(json.dumps(r) for r in rows))


def compare(a):
    base = {r['id']: r for r in map(json.loads, a.base.read_text().splitlines())}
    var = {r['id']: r for r in map(json.loads, a.variant.read_text().splitlines())}
    ids = sorted(base)
    norm = lambda s: ''.join((s or '').lower().split())
    same = dict(name=0, collector=0, lines=0)
    diffs = []
    for i in ids:
        b, v = base[i], var[i]
        n = norm(b['name']) == norm(v['name']); c = norm(b['collector']) == norm(v['collector'])
        l = sorted(map(norm, b['lines'])) == sorted(map(norm, v['lines']))
        same['name'] += n; same['collector'] += c; same['lines'] += l
        if not (n and c):
            diffs.append(dict(id=i, base=[b['name'], b['collector']], var=[v['name'], v['collector']]))
    cpu = lambda d: sorted(r['cpu_ms'] for r in d.values())
    q = lambda v, p: v[min(len(v) - 1, int(len(v) * p))]
    cb, cv = cpu(base), cpu(var)
    print(json.dumps(dict(photos=len(ids), same=same,
        cpu_ms_base=dict(p50=q(cb, .5), p90=q(cb, .9), mean=sum(cb) / len(cb)),
        cpu_ms_variant=dict(p50=q(cv, .5), p90=q(cv, .9), mean=sum(cv) / len(cv)),
        saved_pct=100 * (1 - sum(cv) / sum(cb)), diffs=diffs), indent=1))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--panel', type=Path, required=True)
    r.add_argument('--root', type=Path, required=True)
    r.add_argument('--models', type=Path, required=True)
    r.add_argument('--det', default='PP-OCRv6_det_small.onnx')
    r.add_argument('--rec', default='PP-OCRv6_rec_small.onnx')
    r.add_argument('--side', type=int)
    r.add_argument('--limit-type')
    r.add_argument('--kinds', default='raw,phone_capture,reported_phone')
    r.add_argument('--max-passes', type=int, default=0)
    r.add_argument('--limit', type=int, default=10**9)
    r.add_argument('--out', type=Path, required=True)
    c = sub.add_parser('compare')
    c.add_argument('base', type=Path)
    c.add_argument('variant', type=Path)
    a = p.parse_args()
    (run if a.cmd == 'run' else compare)(a)
