"""Conservative OCR corroboration of official English asset hypotheses.

This creates an audit only. No catalogue or vector writes. OCR misses stay
pending; asset-path and image-byte checks are additional, not substitutes.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.ocr import CardOcr
from app.recognition.artifacts import sha256_file
from PIL import Image


def compact(text):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', text).lower())


def identity_agrees(row, names, numbers):
    expected = compact(row['name'])
    name_ok = any(score is not None and score >= .85 and compact(text) == expected
                  for text, score in names)
    collector = row['collector_number'].upper()
    number_ok = False
    for text, score in numbers:
        if score is None or score < .85:
            continue
        # Require a fraction numerator, not an isolated number that could be
        # the copyright year, denominator, attack damage, or promo identifier.
        for numerator in re.findall(r'(?<![A-Za-z0-9])([A-Za-z]*\d+)\s*/\s*[A-Za-z]*\d+', text):
            if numerator.upper() == collector:
                number_ok = True
    return name_ok and number_ok


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--discovery', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--start', type=int, default=0)
    p.add_argument('--end', type=int)
    p.add_argument('--reuse-audit', type=Path)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError('Audit output already exists')
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path = lambda *a, **k: 'unused-audit-font'
    ocr = CardOcr('/data/models/PP-OCRv6_det_small.onnx',
                  '/data/models/PP-OCRv6_rec_small.onnx',
                  '/data/models/ch_ppocr_mobile_v2.0_cls_mobile.onnx', 1, 1)
    records = []
    reused = {} if not args.reuse_audit else {r['card_id']: r for r in json.loads(args.reuse_audit.read_text())['records']}
    downloaded = [r for r in json.loads(args.discovery.read_text())['records'] if 'file' in r]
    for row in downloaded[args.start:args.end]:
        path = args.discovery.parent / 'images' / row['file']
        if sha256_file(path) != row['sha256']:
            raise ValueError('Discovery image checksum changed')
        previous = reused.get(row['id'])
        if previous and previous['image_sha256'] == row['sha256']:
            records.append(previous)
            continue
        with Image.open(path) as im:
            image = im.convert('RGB').resize((735, 1026))
        names, scores = ocr._run(image.crop((0, 0, 735, 230)))
        numbers, nscores = ocr._run(image.crop((0, 841, 735, 1026)))
        name_hits = list(zip(names, scores))
        number_hits = list(zip(numbers, nscores))
        # Audit contains only identity-region OCR, never the rules box.
        out = {'card_id': row['id'], 'name_hits': name_hits, 'number_hits': number_hits,
               'status': 'ocr_corroborated' if identity_agrees(row, name_hits, number_hits)
                         else 'manual_review', 'image_sha256': row['sha256']}
        records.append(out)
        print(json.dumps({'card_id': row['id'], 'status': out['status']}), flush=True)
        args.output.with_suffix('.checkpoint.json').write_text(json.dumps({'records': records}))
    args.output.write_text(json.dumps({'discovery_sha256': sha256_file(args.discovery),
                                     'records': records}, indent=2))


if __name__ == '__main__':
    main()
