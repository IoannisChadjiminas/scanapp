"""Simulate the phone's on-device card text read (client_text) for a frozen photo panel.

Apple Vision on this Mac stands in for iOS on-device OCR. Each photo is cropped
to the card the way the phone would see it after straightening (the server's own
detector is the proxy for the phone's rectangle finder); a photo without a card
found gets no hint, as on the phone. Vision reads the crop, and the same rules the
app would use pick the name from the title band and the collector number from the
footer band.

    swiftc -O scripts/vision_text.swift -o /tmp/vision_text
    python scripts/simulate_client_text.py --panel cases.json --root panel/ \\
        --vision /tmp/vision_text --out hints.jsonl [--raw raw.jsonl] [--fast]

Writes one row per case: the client_text JSON the phone would send (or null), the
crop used, Vision's time, and how the hint compares with the panel's manual truth.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.client_text import parse_client_text  # noqa: E402
from app.recognition.detect import server_frame_rect, warp_to_rect  # noqa: E402
from app.recognition.rank import name_match, number_match  # noqa: E402

TITLE_BAND = .20      # top of the straightened card
FOOTER_BAND = .80     # bottom of the straightened card
HP = re.compile(r'(?:\bHP\s*\d{2,3}|\d{2,3}\s*HP\b)', re.IGNORECASE)
BADGE = re.compile(
    r'^(?:basic|stage\s*\d|stage\d|trainer|supporter|item|stadium|tool|energy|'
    r'evolves\s+from.*|put\s+.*|たね|進化|1\s*進化|2\s*進化|ポケモンのどうぐ|サポート|グッズ|スタジアム)$',
    re.IGNORECASE)
FRACTION = re.compile(r'(?<![A-Z0-9])((?:[A-Z]{1,4})?\d{1,4}\s*/\s*(?:[A-Z]{1,4})?\d{1,4})(?!\d)',
                      re.IGNORECASE)
PROMO = re.compile(r'\b((?:SWSH|SVP|SM|XY|BW|DP|HGSS|SV)\s?-?\d{2,4})\b')
# A stage badge in front of the name on the same line ("STAGE1 Parasect", "BASIC Pikachu").
LEADING_BADGE = re.compile(r'^(?:BASI[CGS]|STAGE\s?[0-9IZT|]?)\s+(?=\w)', re.IGNORECASE)
# Holder label words that sit in a slab's title band but are never a card name.
GRADER = re.compile(r'\b(?:PSA|BGS|BECKETT|CGC|TAG|ACE|AGS|GRADE|GEM\s*MT|MINT|NM[-/ ]?MT)\b',
                    re.IGNORECASE)


def card_crop(path):
    """The straightened card and how it was found, or (None, 'no_card').

    A card-shaped upload with no card edge found is read as it is: that is the
    phone's own crop to the framing guide. Anything else gets no hint.
    """
    image = ImageOps.exif_transpose(Image.open(path)).convert('RGB')
    rect = server_frame_rect(image)
    if rect is not None:
        return warp_to_rect(image, rect), 'server_warp'
    if .62 <= image.width / image.height <= .80:
        return image, 'as_uploaded'
    return None, 'no_card'


def pick_name(lines):
    """The tallest non-badge line in the title band, without its HP."""
    best = None
    for line in lines:
        if line['y'] + line['h'] / 2 > TITLE_BAND:
            continue
        text = LEADING_BADGE.sub('', HP.sub('', line['text'])).strip(' .,:;-*')
        if not text or BADGE.match(text) or GRADER.search(text):
            continue
        letters = sum(c.isalpha() for c in text)
        digits = sum(c.isdigit() for c in text)
        cjk = any(ord(c) > 0x2E80 for c in text)
        # A styled "HP 70" glyph is the tallest thing in the band; keep word-like lines only.
        if letters < (2 if cjk else 3) or digits >= letters:
            continue
        key = (line['h'], line['conf'])
        if best is None or key > best[0]:
            best = (key, text[:64], line['conf'])
    return (best[1], best[2]) if best else (None, None)


def pick_number(lines):
    """A collector fraction or promo code in the footer band, the most confident first."""
    found = []
    for line in lines:
        if line['y'] + line['h'] / 2 < FOOTER_BAND:
            continue
        for pattern in (FRACTION, PROMO):
            # Gallery prefixes are often read with a letter O for zero (TGO1/TG30).
            text = re.sub(r'\b(TG|GG)([0-9O]{1,3})\b',
                          lambda m: m.group(1) + m.group(2).replace('O', '0'), line['text'])
            for match in pattern.finditer(text):
                found.append((line['conf'], -line['x'], re.sub(r'\s', '', match.group(1)).upper()))
    if not found:
        return None, None
    conf, _, text = max(found)
    return text, conf


def client_text(lines, ms, engine):
    name, name_conf = pick_name(lines)
    number, number_conf = pick_number(lines)
    if name is None and number is None:
        return None
    body = dict(v=1, engine=engine, name=name, name_conf=None if name is None else round(name_conf, 3),
                number=number, number_conf=None if number is None else round(number_conf, 3),
                ms=int(round(ms)))
    raw = json.dumps(body, ensure_ascii=False, separators=(',', ':'))
    hint, reason = parse_client_text(raw)
    if hint is None:
        # What the phone would send must also pass the server's validation.
        body['number' if reason == 'bad_number' else 'name'] = None
        raw = json.dumps(body, ensure_ascii=False, separators=(',', ':'))
        if parse_client_text(raw)[0] is None:
            return None
    return raw


def comparable(number):
    """The panel's truth in the form the server's parser takes (TG01/TG30 as TG01/30)."""
    return re.sub(r'^([A-Z]{1,4})(\d{1,4})/\1(\d{1,4})$', r'\1\2/\3', number.replace(' ', '').upper())


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--panel', type=Path, required=True)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--vision', type=Path, required=True, help='compiled vision_text binary')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--raw', type=Path, help='also keep every Vision line here')
    p.add_argument('--fast', action='store_true', help="Vision's fast level instead of accurate")
    a = p.parse_args()
    cases = json.loads(a.panel.read_text())
    engine = 'apple-vision-fast' if a.fast else 'apple-vision'
    with tempfile.TemporaryDirectory() as scratch:
        crops, how = {}, {}
        for case in cases:
            crop, how[case['id']] = card_crop(a.root / case['photo_file'])
            if crop is not None:
                # The phone straightens to a JPEG before upload; read the same kind of image.
                target = Path(scratch) / f"{case['id']}.jpg"
                crop.save(target, 'JPEG', quality=90)
                crops[case['id']] = (target, crop.size)
        command = [str(a.vision), *(['--fast'] if a.fast else [])]
        reply = subprocess.run(command, input='\n'.join(str(t) for t, _ in crops.values()) + '\n',
                               capture_output=True, text=True, check=True)
        vision = {Path(r['path']).stem: r for r in map(json.loads, reply.stdout.splitlines())}
    raw_handle = a.raw.open('w') if a.raw else None
    with a.out.open('w') as handle:
        for case in cases:
            truth = case.get('manual_truth') or {}
            seen = vision.get(case['id'])
            text = client_text(seen['lines'], seen['ms'], engine) if seen and 'error' not in seen else None
            hint = parse_client_text(text)[0] if text else None
            row = dict(id=case['id'], kind=case['kind'], client_text=text,
                       crop=how[case['id']],
                       crop_size=list(crops[case['id']][1]) if case['id'] in crops else None,
                       vision_ms=round(seen['ms'], 1) if seen else None,
                       truth_name=truth.get('name'), truth_number=truth.get('number'),
                       name_agrees=(name_match(hint.name, truth['name'])
                                    if hint and hint.name and truth.get('name') else None),
                       number_agrees=(number_match([hint.number], comparable(truth['number'])) is True
                                      if hint and hint.number and truth.get('number') else None))
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
            if raw_handle and seen:
                raw_handle.write(json.dumps(dict(id=case['id'], **seen), ensure_ascii=False) + '\n')
    if raw_handle:
        raw_handle.close()


if __name__ == '__main__':
    main()
