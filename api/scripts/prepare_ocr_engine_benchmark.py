"""Freeze identical OCR inputs and separate labels; no catalogue mutation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

from PIL import Image, ImageOps
import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.detect import detect_and_rectify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root, args.output
    output.mkdir(parents=True, exist_ok=False)
    (output / 'inputs').mkdir()
    cv2.setNumThreads(1)
    frozen = root / 'data/catalogue-completion/20261004-01/frozen-replay'
    phone = root / 'data/catalogue-completion/20261004-01/english-scanner-fix-001/phone-panel'
    catalog = sqlite3.connect(f'file:{root}/data/catalogue-completion/20261004-01/replay-candidate/catalog.sqlite?mode=ro', uri=True)
    catalog.row_factory = sqlite3.Row
    cases = [(case, frozen, 'seller_photo') for case in json.loads((frozen / 'cases.json').read_text())[:100]]
    cases += [(case, phone, 'saved_phone_photo') for case in json.loads((phone / 'cases.json').read_text())]
    corrections = json.loads((root / 'docs/grading-fresh100-card-truth-20261002.json').read_text()).get('annotation_corrections', [])
    labels, inputs = [], []
    for case, directory, source in cases:
        payload = (directory / case['photo_file']).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == case['sha256']
        truth = case.get('manual_truth', {}).copy()
        for correction in corrections:
            if case['id'] == correction['id']:
                truth['number'] = correction['correct_number']
        card_ids = case.get('expected_card_ids', [])
        row = catalog.execute('SELECT name, language, printed_collector_number, collector_number FROM cards WHERE id=?',
                              (card_ids[0],)).fetchone() if card_ids else None
        if row:
            truth['printed_name'] = row['name']
            truth.setdefault('language', row['language'])
            truth.setdefault('name', row['name'])
            truth.setdefault('number', row['printed_collector_number'] or row['collector_number'])
        elif truth.get('language') == 'en':
            truth['printed_name'] = truth['name']
        truth.setdefault('kind', 'raw')
        with Image.open(directory / case['photo_file']) as original:
            image = ImageOps.exif_transpose(original).convert('RGB')
        card, detected = detect_and_rectify(image)
        ocr_card = card
        if card.width < 450:
            scale = min(3., 600 / card.width)
            ocr_card = card.resize((round(card.width * scale), round(card.height * scale)), Image.Resampling.LANCZOS)
        profiles = {'full': image, 'card': card,
                    'title': ocr_card.crop((0, 0, ocr_card.width, max(1, round(ocr_card.height * .22)))),
                    'footer': ocr_card.crop((0, round(ocr_card.height * .82), ocr_card.width, ocr_card.height))}
        labels.append(dict(id=case['id'], source=source, source_sha256=case['sha256'], truth=truth,
                           expected_card_ids=card_ids, geometry_detected=detected))
        for profile, patch in profiles.items():
            file = f"inputs/{case['id']}.{profile}.png"
            patch.save(output / file, format='PNG')
            inputs.append(dict(id=case['id'], profile=profile, file=file,
                               sha256=hashlib.sha256((output / file).read_bytes()).hexdigest(),
                               width=patch.width, height=patch.height,
                               script='japanese' if truth.get('language') == 'ja' else 'latin'))
    (output / 'labels.json').write_text(json.dumps(labels, ensure_ascii=False, indent=2))
    (output / 'inputs.json').write_text(json.dumps(inputs, ensure_ascii=False, indent=2))
    (output / 'scope.json').write_text(json.dumps(dict(
        photos=len(labels), inputs=len(inputs),
        primary_scope='OCR extraction on identical lossless PNG pixels; labels not supplied to recognizers',
        limitations='Previously reviewed convenience corpus, not unseen accuracy. Geometry-only crops may miss text; full/card/title/footer are separate tasks. No live camera/upload or final API replacement claims.',
        script_selection='Existing user language used; automatic language/script detection is not evaluated.',
        catalogue_mode='read-only label enrichment only'), indent=2))
    print(json.dumps(dict(photos=len(labels), inputs=len(inputs))), flush=True)


if __name__ == '__main__':
    main()
