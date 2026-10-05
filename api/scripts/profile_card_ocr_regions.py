"""Read-only OCR profiling of saved input/query frames; no result DB writes."""
import argparse
import json
from pathlib import Path
import sys

import cv2
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.ocr import CardOcr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-dir', type=Path, required=True)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    from rapidocr.utils.vis_res import VisRes
    VisRes.get_font_path = lambda self, *a, **k: 'unused-benchmark-drawing-font'
    reader = CardOcr('/data/models/PP-OCRv6_det_small.onnx',
        '/data/models/PP-OCRv6_rec_small.onnx', '/data/models/ch_ppocr_mobile_v2.0_cls_mobile.onnx', 1, 1)
    records = []
    for path in sorted((args.audit_dir/'images').glob('*.jpg')):
        with Image.open(path) as image:
            result = reader.read(image)
        record = {'photo': path.name, 'name': result.name_text, 'collector': result.collector_text,
            'failed': result.failed, 'passes': result.passes,
            'hits': [vars(h) for h in result.hits]}
        records.append(record)
        print(json.dumps(record), flush=True)
    (args.audit_dir/'ocr-profile.json').write_text(json.dumps(records, indent=2))


if __name__ == '__main__':
    main()
