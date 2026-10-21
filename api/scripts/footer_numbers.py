"""A second, tighter collector-number read, the way the phone can do it.

The full-card Vision pass stays as it is. This adds a high-resolution read of
the footer strip and of the two bottom corners, cleans characters only inside
number patterns, and keeps a number only when the catalogue has that printed
number or that collector number in a set of the same total. Slabs drop label
words from the card name and fall back to the label number.

    python api/scripts/footer_numbers.py \\
        --stage0 data/latency/stage0-simulation-20261021/stage0.jsonl \\
        --catalog data/latency/stage0-simulation-20261021/kit/catalog.sqlite \\
        --totals data/catalogue-completion/staging-data-local-20261014/catalog.sqlite \\
        --vision /tmp/vision_text
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'api'))
sys.path.insert(0, str(REPO / 'api/scripts'))

from app.recognition.label_identity import number_key  # noqa: E402
from app.recognition.ocr import grading_label_line, slab_label_field  # noqa: E402
from simulate_stage0 import _client_text  # noqa: E402

BAND = 0.14
CORNER_W = 0.35
CORNER_H = 0.15
SCALE = 2.0
MIN_TEXT_HEIGHT = 0.015
# A number whose centre sits above this, on the full card, is attack damage.
FOOTER_FLOOR = 0.90

_DIGIT = str.maketrans({'O': '0', 'I': '1', 'L': '1', '|': '1', 'S': '5', 'B': '8', 'Z': '2'})
_LOOSE = re.compile(
    r'(?<![A-Z0-9])('
    r'(?:TG|GG|SV|RC)[0-9OILSBZ|]{1,3}\s*/\s*(?:TG|GG|SV|RC)[0-9OILSBZ|]{1,3}'
    r'|\d{0}[0-9OILSBZ|]{1,3}[A-Z]?\s*/\s*[0-9OILSBZ|]{1,3}'
    r'|(?:SWSH|SM|XY|BW)\s?-?\s?[0-9OILSBZ|]{2,4}'
    r'|SVP(?:\s*EN)?\s?-?\s?[0-9OILSBZ|]{3}'
    r'|[0-9OILSBZ|]{3}\s*/\s*(?:SV|S)\s*-\s*P'
    r')(?![A-Z0-9])',
    re.IGNORECASE,
)
_PLAIN = re.compile(
    r'(?<![A-Z0-9])('
    r'(?:TG|GG|SV|RC)\d{1,3}/(?:TG|GG|SV|RC)\d{2,3}'
    r'|\d{1,3}[A-Z]?/\d{1,3}'
    r'|(?:SWSH|SM|XY|BW)\d{2,4}'
    r'|SVP(?:EN)?\d{3}'
    r'|\d{3}/(?:SV|S)-P'
    r')(?![A-Z0-9])',
    re.IGNORECASE,
)
def group_of(row: dict) -> str:
    if str(row['id']).endswith('-screenshot'):
        return 'screenshot'
    if row.get('kind') in {'phone_capture', 'reported_phone'}:
        return 'phone'
    return row.get('kind') or 'unknown'


def norm(value: str | None) -> str:
    return re.sub(r'[\s-]', '', (value or '')).upper()


def gallery_once(value: str) -> str:
    return re.sub(r'^([A-Z]{1,4})(\d{1,4})/\1(\d{1,4})$', r'\1\2/\3', norm(value))


def clean_span(raw: str) -> str:
    """O→0 and the other swaps, and only on the digit positions of a number."""
    text = re.sub(r'\s*/\s*', '/', raw.upper())
    text = re.sub(r'\s+', '', text)
    held: list[str] = []

    def hold(match: re.Match) -> str:
        held.append(match.group(0))
        return f'\x00{len(held) - 1}\x00'

    text = re.sub(r'SV-P|S-P|SVP|SWSH|TG|GG|SV|RC|SM|XY|BW|EN', hold, text)
    text = text.translate(_DIGIT)

    def restore(match: re.Match) -> str:
        return held[int(match.group(1))]

    return gallery_once(re.sub(r'\x00(\d+)\x00', restore, text))


class Catalogue:
    def __init__(self, catalog: Path, totals: Path | None):
        import sqlite3
        db = sqlite3.connect(catalog)
        self.printed: set[str] = set()
        self.any_number: set[str] = set()
        self.by_key: dict[str, set[tuple[str, str]]] = defaultdict(set)
        denoms: dict[tuple[str, str], Counter] = defaultdict(Counter)
        for card_id, number, printed, language, set_id in db.execute(
                'SELECT id, collector_number, printed_collector_number, language, set_id FROM cards'):
            for value in (number, printed):
                if not value:
                    continue
                self.any_number.add(norm(value))
                self.any_number.add(gallery_once(value))
                key = number_key(str(value).split('/')[0])
                if key:
                    self.by_key[key].add((language or '', set_id or ''))
            if printed and '/' in printed:
                self.printed.add(norm(printed))
                self.printed.add(gallery_once(printed))
                tail = gallery_once(printed).split('/')[-1]
                if tail.isdigit():
                    denoms[(language or '', set_id or '')][int(tail)] += 1
        self.totals: dict[tuple[str, str], int] = {}
        if totals and totals.is_file():
            extra = sqlite3.connect(totals)
            try:
                for language, set_id, total in extra.execute(
                        'SELECT language, set_id, official_total FROM set_totals'):
                    self.totals[(language or '', set_id or '')] = int(total)
            except sqlite3.Error:
                pass
        for key, counter in denoms.items():
            self.totals.setdefault(key, counter.most_common(1)[0][0])

    def accepts(self, number: str | None) -> bool:
        if not number:
            return False
        forms = {norm(number), gallery_once(number)}
        if forms & self.printed or forms & self.any_number:
            return True
        head, _, denom = gallery_once(number).partition('/')
        key = number_key(head)
        if not key:
            return False
        if not denom:
            return key in self.by_key
        if not denom.isdigit():
            return False
        total = int(denom)
        return any(self.totals.get(pair) == total for pair in self.by_key.get(key, ()))


def labelish(text: str | None) -> bool:
    if not text:
        return False
    return bool(grading_label_line(text) or slab_label_field(text))


def boost(image: Image.Image) -> Image.Image:
    rgb = np.asarray(image.convert('RGB'))
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    lightness, green, blue = cv2.split(lab)
    lightness = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(lightness)
    blurred = cv2.GaussianBlur(lightness, (0, 0), 1.0)
    lightness = cv2.addWeighted(lightness, 1.5, blurred, -0.5, 0)
    merged = cv2.cvtColor(cv2.merge((lightness, green, blue)), cv2.COLOR_LAB2RGB)
    return Image.fromarray(merged)


def cuts(image: Image.Image) -> dict[str, Image.Image]:
    width, height = image.size
    footer_top = int(height * (1 - BAND))
    corner_top = int(height * (1 - CORNER_H))
    corner_x = int(width * CORNER_W)

    def zoom(box: tuple[int, int, int, int]) -> Image.Image:
        crop = image.crop(box)
        return crop.resize((max(1, round(crop.width * SCALE)), max(1, round(crop.height * SCALE))),
                           Image.Resampling.LANCZOS)

    return {
        'footer': zoom((0, footer_top, width, height)),
        'bl': zoom((0, corner_top, corner_x, height)),
        'br': zoom((width - corner_x, corner_top, width, height)),
        'contrast': zoom((0, footer_top, width, height)),
    }


def vision_batch(binary: Path, images: list[tuple[str, Path]]) -> dict[str, dict]:
    if not images:
        return {}
    reply = subprocess.run(
        [str(binary), '--min-height', str(MIN_TEXT_HEIGHT)],
        input=''.join(f'{path}\n' for _, path in images),
        capture_output=True, text=True, check=True)
    found = {}
    for line in reply.stdout.splitlines():
        item = json.loads(line)
        found[Path(item['path']).stem] = item
    return found


def candidates_from(lines: list[dict], source: str, *, cleanup: bool, card_floor: float | None) -> list[dict]:
    found = []
    pattern = _LOOSE if cleanup else _PLAIN
    for line in lines or []:
        centre = line['y'] + line['h'] / 2
        if card_floor is not None and centre < card_floor:
            continue
        text = line['text']
        matches = list(pattern.finditer(text))
        if cleanup and not matches:
            matches = list(_LOOSE.finditer(text))
        for match in matches:
            raw = match.group(1)
            number = clean_span(raw) if cleanup else gallery_once(raw)
            if not number:
                continue
            found.append({
                'number': number, 'conf': float(line.get('conf') or 0), 'source': source,
                'y': centre, 'raw': raw,
            })
    return found


def card_floor_for(source: str) -> float | None:
    """Footer-strip coordinates: reject the upper part of the strip (attack damage)."""
    if source != 'footer' and source != 'contrast':
        return None
    # The strip is the bottom BAND of the card. Map FOOTER_FLOOR back into the strip.
    return max(0.0, (FOOTER_FLOOR - (1 - BAND)) / BAND)


def rank(items: list[dict]) -> dict | None:
    if not items:
        return None
    priority = {'bl': 3, 'br': 3, 'footer': 2, 'contrast': 2, 'full': 1}

    def key(item: dict) -> tuple:
        return (priority.get(item['source'], 0), item['conf'], item['y'])

    return max(items, key=key)


def body_of(row: dict) -> dict:
    if not row.get('client_text'):
        return {}
    try:
        return json.loads(row['client_text'])
    except ValueError:
        return {}


def choose(row: dict, reads: dict[str, dict], catalogue: Catalogue, *,
           footer: bool, corners: bool, cleanup: bool, check: bool, contrast: bool, slabs: bool) -> dict:
    """One cumulative stage. A later crop is read only when the earlier one has no number."""
    current = body_of(row)
    full = current.get('number')
    rejected: list[str] = []

    def from_sources(sources: tuple[str, ...]) -> dict | None:
        pool: list[dict] = []
        for source in sources:
            item = reads.get(source)
            if not item or item.get('error'):
                continue
            pool.extend(candidates_from(item.get('lines') or [], source, cleanup=cleanup,
                                        card_floor=card_floor_for(source)))
        if check:
            kept = []
            for item in pool:
                if catalogue.accepts(item['number']):
                    kept.append(item)
                else:
                    rejected.append(item['number'])
            pool = kept
        return rank(pool)

    chosen = from_sources(('footer',)) if footer else None
    if chosen is None and corners:
        chosen = from_sources(('bl', 'br'))
    if chosen is None and contrast:
        chosen = from_sources(('contrast',))
    if chosen is None and full and (not check or catalogue.accepts(gallery_once(full))):
        chosen = {'number': gallery_once(full), 'conf': float(current.get('number_conf') or 0),
                  'source': 'full', 'y': 1.0, 'raw': full}
    name, name_conf = current.get('name'), current.get('name_conf')
    number = None if chosen is None else chosen['number']
    number_conf = None if chosen is None else chosen['conf']
    source = None if chosen is None else chosen['source']
    if slabs and (row.get('quad_role') == 'slab' or row.get('kind') == 'slab'):
        if labelish(name) and current.get('label_name') and not labelish(current.get('label_name')):
            name, name_conf = current.get('label_name'), current.get('label_name_conf')
        elif labelish(name):
            name, name_conf = None, None
        if number is None and current.get('label_number') and (
                not check or catalogue.accepts(current.get('label_number'))):
            number = gallery_once(current['label_number'])
            number_conf = current.get('label_number_conf') or 0
            source = 'label'
    return {
        'name': name, 'name_conf': name_conf, 'number': number, 'number_conf': number_conf,
        'source': source, 'rejected': rejected,
    }


def apply_choice(row: dict, choice: dict, total_ms: float, added: float) -> None:
    current = body_of(row)
    label = {key: current[key] for key in current if key.startswith('label_')}
    row['client_text'] = _client_text(choice['name'], choice['name_conf'], choice['number'],
                                       choice['number_conf'], total_ms, label)
    row['number_source'] = choice['source']
    row['footer_ms'] = round(added, 1)


def added_ms(reads: dict[str, dict], footer_hit: bool, corner_hit: bool) -> float:
    """Footer, then the two corners, then one contrast retry. Stop when a number is in hand."""
    total = float((reads.get('footer') or {}).get('ms') or 0)
    if footer_hit:
        return total
    total += float((reads.get('bl') or {}).get('ms') or 0) + float((reads.get('br') or {}).get('ms') or 0)
    if corner_hit:
        return total
    return total + float((reads.get('contrast') or {}).get('ms') or 0)


def reason_without(row: dict, reads: dict[str, dict], rejected: list[str]) -> str:
    if not row.get('crop_file'):
        return 'no card rectangle, so there is no footer to read'
    quality = {}
    if row.get('client_quality'):
        try:
            quality = json.loads(row['client_quality'])
        except ValueError:
            quality = {}
    footer = reads.get('footer') or {}
    lines = footer.get('lines') or []
    texts = ' '.join(line.get('text') or '' for line in lines)
    if rejected:
        return 'read ' + ', '.join(dict.fromkeys(rejected)) + ', none of them is a catalogue number'
    if not lines:
        if (quality.get('glare') or 0) >= 0.05:
            return 'footer strip came back empty, glare on the card'
        height = footer.get('height') or 0
        if height and height < 80:
            return 'footer strip came back empty, the card crop is tiny'
        if (quality.get('card_fraction') or 1) < 0.45:
            return 'footer strip came back empty, the card is cut off'
        return 'footer strip came back empty'
    if (quality.get('glare') or 0) >= 0.05:
        return f'footer text {texts[:80]!r} has no number, glare on the card'
    return f'footer text {texts[:80]!r} has no collector number'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage0', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--totals', type=Path)
    parser.add_argument('--vision', type=Path, required=True)
    parser.add_argument('--ablation', type=Path)
    args = parser.parse_args()
    root = args.stage0.parent
    rows = [json.loads(line) for line in args.stage0.read_text().splitlines()]
    catalogue = Catalogue(args.catalog, args.totals)
    round2 = {row['id']: body_of(row).get('number') for row in rows}
    images: list[tuple[str, Path]] = []
    scratch = tempfile.TemporaryDirectory()
    try:
        folder = Path(scratch.name)
        for row in rows:
            if not row.get('crop_file'):
                continue
            image = ImageOps.exif_transpose(Image.open(root / row['crop_file'])).convert('RGB')
            pieces = cuts(image)
            pieces['contrast'] = boost(pieces['contrast'])
            for source, piece in pieces.items():
                path = folder / f"{row['id']}__{source}.jpg"
                piece.save(path, 'JPEG', quality=90)
                images.append((f"{row['id']}__{source}", path))
        seen = vision_batch(args.vision, images)
    finally:
        scratch.cleanup()
    reads_by_id: dict[str, dict[str, dict]] = defaultdict(dict)
    for key, item in seen.items():
        if '__' not in key:
            continue
        case_id, source = key.rsplit('__', 1)
        reads_by_id[case_id][source] = item

    stages = (
        ('round2', dict(footer=False, corners=False, cleanup=False, check=False, contrast=False, slabs=False)),
        ('footer', dict(footer=True, corners=False, cleanup=False, check=False, contrast=False, slabs=False)),
        ('corners', dict(footer=True, corners=True, cleanup=False, check=False, contrast=False, slabs=False)),
        ('cleanup', dict(footer=True, corners=True, cleanup=True, check=False, contrast=False, slabs=False)),
        ('catalogue', dict(footer=True, corners=True, cleanup=True, check=True, contrast=False, slabs=False)),
        ('contrast', dict(footer=True, corners=True, cleanup=True, check=True, contrast=True, slabs=False)),
        ('slabs', dict(footer=True, corners=True, cleanup=True, check=True, contrast=True, slabs=True)),
    )
    stage_choices = {}
    for name, flags in stages:
        stage_choices[name] = {row['id']: choose(row, reads_by_id.get(row['id'], {}), catalogue, **flags) for row in rows}

    final = stage_choices['slabs']
    times = []
    missing = []
    for row in rows:
        choice = final[row['id']]
        reads = reads_by_id.get(row['id'], {})
        footer_lines = candidates_from((reads.get('footer') or {}).get('lines') or [], 'footer',
                                        cleanup=True, card_floor=card_floor_for('footer'))
        corner_lines = candidates_from((reads.get('bl') or {}).get('lines') or [], 'bl', cleanup=True, card_floor=None)
        corner_lines += candidates_from((reads.get('br') or {}).get('lines') or [], 'br', cleanup=True, card_floor=None)
        footer_valid = [item for item in footer_lines if catalogue.accepts(item['number'])]
        corner_valid = [item for item in corner_lines if catalogue.accepts(item['number'])]
        spent = added_ms(reads, bool(footer_valid), bool(corner_valid))
        if reads:
            times.append(spent)
        base_ms = body_of(row).get('ms') or 0
        apply_choice(row, choice, base_ms + spent, spent)
        sent = body_of(row).get('number')
        if not sent:
            missing.append({
                'id': row['id'], 'group': group_of(row),
                'reason': reason_without(row, reads, choice['rejected']),
                'round2': round2.get(row['id']),
            })
    args.stage0.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
    times.sort()

    def rate(choices: dict[str, dict]) -> dict:
        counts = {}
        for name in ('raw', 'slab', 'phone', 'screenshot'):
            subset = [row for row in rows if group_of(row) == name]
            got = sum(1 for row in subset if choices[row['id']].get('number'))
            counts[name] = {'photos': len(subset), 'with_number': got}
        counts['all'] = {'photos': len(rows), 'with_number': sum(item['with_number'] for item in counts.values())}
        return counts

    # A number counts only when the phone would actually send it. The final
    # stage is re-read from the written payload so server validation is included.
    def sent_rate() -> dict:
        counts = {}
        for name in ('raw', 'slab', 'phone', 'screenshot'):
            subset = [row for row in rows if group_of(row) == name]
            got = sum(1 for row in subset if body_of(row).get('number'))
            counts[name] = {'photos': len(subset), 'with_number': got}
        counts['all'] = {'photos': len(rows), 'with_number': sum(item['with_number'] for item in counts.values())}
        return counts

    summary = {
        'added_ms_median': round(times[len(times) // 2], 1) if times else None,
        'added_ms_p90': round(times[int(len(times) * 0.9)], 1) if times else None,
        'added_ms_mean': round(sum(times) / len(times), 1) if times else None,
        'photos_timed': len(times),
        'number_rate': {name: rate(choices) for name, choices in stage_choices.items()},
        'sent_rate': sent_rate(),
        'missing': missing,
        'sources': dict(Counter(choice['source'] for choice in final.values() if choice.get('number'))),
        'choices': {
            name: {case_id: {'number': choice.get('number'), 'name': choice.get('name'),
                             'name_conf': choice.get('name_conf'), 'number_conf': choice.get('number_conf')}
                   for case_id, choice in choices.items()}
            for name, choices in stage_choices.items()},
    }
    if args.ablation:
        args.ablation.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({key: summary[key] for key in summary if key not in {'missing', 'choices'}}, indent=2))
    print('missing', len(missing))


if __name__ == '__main__':
    main()
