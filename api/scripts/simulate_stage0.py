"""Simulate the stage-0 fields a phone would send for the frozen panel.

Corners come from the server's detector, moved by at most 0.5% of the card's
short side. A slab sends that outline. Name, number, quality and the embedding
use the card window inside it. Text is Apple Vision `.accurate`. The embedding
is the Core ML 8-bit model `2ddf6ec79e37/coreml-pal8`.

    python api/scripts/simulate_stage0.py fields --out data/latency/stage0-simulation-20261021
    python api/scripts/simulate_stage0.py embed --out data/latency/stage0-simulation-20261021 \\
        --model coreml_pal8.mlpackage
    python api/scripts/simulate_stage0.py convert --onnx dinov2_small.onnx --model coreml_pal8.mlpackage

`fields` needs the API virtualenv (OpenCV, the recognition package, the vision_text
binary). `embed` and `convert` need coremltools and run without the API package.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import tempfile
import time
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

REPO = Path(__file__).resolve().parents[2]
MODEL_ID = '2ddf6ec79e37/coreml-pal8'
SLAB_LABEL_END = 0.18
SLAB_CARD_END = 0.90
SLAB_CARD_INSET = 0.06
ENGINE = 'apple-vision'
# The gallery detector's slab outline on the two screenshots. The server's
# detector finds no rectangle in the browser chrome around them.
RECORDED_SLAB = {
    'lugia-screenshot': '0.0156,0.1695,0.8716,0.1691,0.8720,0.7891,0.0156,0.7891',
    'charmander-screenshot': '0.2569,0.2969,0.7500,0.2930,0.7639,0.6875,0.2500,0.6797',
}

LUGIA = Path('/Users/ioannischadjiminas/.claude/uploads/43ee8635-fa88-4116-86c8-adb95df4186a/1299f40e-image.png')
CHARMANDER = Path('/Users/ioannischadjiminas/.claude/uploads/43ee8635-fa88-4116-86c8-adb95df4186a/e1a30482-image.png')
PANEL_JSONL = REPO / 'data/latency/staging-reference027-20261003/regression-cached.jsonl'
PHOTO_ROOTS = (
    REPO / 'data/catalogue-completion/20261004-01/frozen-replay',
    REPO / 'datasets/review/grading-fresh100-20261002',
    REPO / 'datasets/review/grading-fresh100-20261002/frozen-photos',
)

_GRADER = re.compile(r'\b(?:PSA|CGC|BGS|BECKETT|ACE|SGC|AGS|TAG|HGA|PI)\b', re.I)
_DESCRIPTOR = re.compile(
    r'^(?:PRISTINE|GEM\s*M(?:T|INT)|MINT\+?|NM[-/ ]?MT|NM[-/ ]?MINT\+?|'
    r'NEAR\s*MINT|UNIVERSAL\s*GRADE|GRADE|AUTHENTIC(?:ATED)?)$', re.I)
_YEAR = re.compile(r'^(?:19|20)\d{2}\b|pok[eé]mon\b.*\b(?:19|20)\d{2}\b', re.I)
_LANGUAGE = re.compile(r'\b(JP|JPN|JAPANESE|EN|ENG|ENGLISH|KO|KOR|KOREAN|ZH|CHN|CHINESE)\b', re.I)
_SUFFIX = re.compile(r'\b(?:EX|GX|VMAX|VSTAR|VUNION|V)\b', re.I)
_HASH = re.compile(r'#\s*(\d{1,4})(?:\s*(?:HOLO|REV|REVERSE))?\b', re.I)
_KEPT = re.compile(
    r'\b((?:[A-Z]{1,4})?\d{1,4}[A-Z]?(?:/(?:[A-Z]{1,4})?\d{1,4})|'
    r'(?:SWSH|SVP|SM|XY|BW|DP|HGSS|SV|TG|GG)-?\d{1,4}[A-Z]?)\b', re.I)
_GRADE_VALUE = re.compile(r'^(?:10|[1-9](?:\.5)?)$')
_INLINE_GRADE = re.compile(
    r'(?:GRADE|PRISTINE|MINT\+?|NM[-/ ]?MT|PSA|CGC|BGS|BECKETT|ACE|SGC|TAG)\s+(10|[1-9](?:\.5)?)\b', re.I)
_BARE_GRADE = re.compile(r'^(?:10|[1-9](?:\.5)?)$')
_LANGUAGES = {
    'JP': 'ja', 'JPN': 'ja', 'JAPANESE': 'ja', 'EN': 'en', 'ENG': 'en', 'ENGLISH': 'en',
    'KO': 'ko', 'KOR': 'ko', 'KOREAN': 'ko', 'ZH': 'zh', 'CHN': 'zh', 'CHINESE': 'zh',
}


def _letters(text: str) -> int:
    return sum(ch.isalpha() for ch in text)


def _number_of(text: str) -> str | None:
    hashed = _HASH.search(text)
    if hashed:
        return hashed.group(1)
    match = _KEPT.search(re.sub(r'\s', '', text))
    if match is None:
        return None
    found = match.group(1)
    if _BARE_GRADE.fullmatch(found) or re.fullmatch(r'\d{6,}', found):
        return None
    return found if len(found) <= 16 else None


def _set_like(text: str) -> bool:
    words = text.split()
    if len(words) < 2 or not any(ch.isalpha() for ch in text):
        return False
    if _DESCRIPTOR.match(text) or _YEAR.search(text) or re.search(r'\bHOLO\b', text, re.I):
        return False
    return True


def parse_slab_label(lines: list[dict]) -> dict:
    """The app's slab-label rules (`label_text.dart`), on Vision lines in slab space."""
    texts = []
    for line in lines:
        text = re.sub(r'\s+', ' ', line['text']).strip()
        if text:
            texts.append((text, line.get('conf')))
    grader = None
    for text, _conf in texts:
        found = _GRADER.search(text)
        if found:
            grader = found.group(0).upper()
            break
    grade = language = number = None
    number_conf = None
    names, sets = [], []
    for text, conf in texts:
        upper = text.upper()
        if language is None and (match := _LANGUAGE.search(upper)):
            language = _LANGUAGES[match.group(1).upper()]
        if grade is None:
            value = (_BARE_GRADE.fullmatch(upper).group(0) if _BARE_GRADE.fullmatch(upper) else None)
            inline = _INLINE_GRADE.search(upper)
            value = value or (inline.group(1) if inline else None)
            if value and _GRADE_VALUE.fullmatch(value) and not (grader == 'PSA' and value == '9.5'):
                grade = value
        found = _number_of(text)
        if number is None and found is not None:
            number, number_conf = found, conf
        if (_LANGUAGE.fullmatch(upper) or _HASH.search(upper) or _YEAR.search(upper)
                or _DESCRIPTOR.match(upper)
                or (found and found.upper() == re.sub(r'\s', '', upper))):
            continue
        if _GRADER.search(upper) and _letters(upper) < 6:
            continue
        parts = re.split(r'\s+-\s+', text)
        if len(parts) == 2 and (tail := _number_of(parts[1])):
            if number is None:
                number, number_conf = tail, conf
            head = parts[0].strip()
            if _set_like(head):
                sets.append(head)
            continue
        if _SUFFIX.search(upper) or len(upper.split()) == 1:
            if any(ch.isalpha() for ch in text):
                names.append((text, conf))
            continue
        if _set_like(text):
            sets.append(text.strip())
    chosen = None
    if names:
        suffixed = [item for item in names if _SUFFIX.search(item[0])]
        pool = suffixed or names
        chosen = min(pool, key=lambda item: len(item[0]))
    def clip(value, limit):
        value = (value or '').strip()
        return value[:limit] or None
    return {
        'label_name': clip(chosen[0], 64) if chosen else None,
        'label_name_conf': None if not chosen or chosen[1] is None else round(float(chosen[1]), 3),
        'label_number': number,
        'label_number_conf': None if number is None or number_conf is None else round(float(number_conf), 3),
        'label_set': clip(sets[0], 64) if sets else None,
        'label_language': language,
        'label_grader': clip(grader, 16) if grader else None,
        'label_grade': grade,
    }


def holder_shaped(corners: np.ndarray) -> bool:
    tl, tr, br, bl = corners
    wide = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2
    tall = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2
    if wide <= 0 or tall <= 0:
        return False
    ratio = min(wide, tall) / max(wide, tall)
    return 0.53 <= ratio <= 0.648


def slab_window(corners: np.ndarray) -> np.ndarray:
    def at(across: float, down: float) -> np.ndarray:
        top = corners[0] * (1 - across) + corners[1] * across
        bottom = corners[3] * (1 - across) + corners[2] * across
        return top * (1 - down) + bottom * down
    right = 1 - SLAB_CARD_INSET
    return np.stack([
        at(SLAB_CARD_INSET, SLAB_LABEL_END), at(right, SLAB_LABEL_END),
        at(right, SLAB_CARD_END), at(SLAB_CARD_INSET, SLAB_CARD_END),
    ]).astype(np.float32)


def corners_from_fractions(quad: str, size: tuple[int, int]) -> np.ndarray:
    width, height = size
    parts = [float(item) for item in quad.split(',')]
    return np.array([[parts[i] * (width - 1), parts[i + 1] * (height - 1)] for i in range(0, 8, 2)], np.float32)


def full_frame(image: Image.Image) -> np.ndarray:
    width, height = image.size
    return np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], np.float32)


def jitter(corners: np.ndarray, case_id: str, amount: float = 0.005) -> np.ndarray:
    side = min(np.linalg.norm(corners[1] - corners[0]), np.linalg.norm(corners[3] - corners[0]))
    rng = np.random.default_rng(zlib.crc32(case_id.encode()))
    return (corners + rng.uniform(-amount, amount, corners.shape) * side).astype(np.float32)


def fractions(corners: np.ndarray, size: tuple[int, int]) -> str:
    width, height = size
    return ','.join(f'{x / (width - 1):.4f},{y / (height - 1):.4f}' for x, y in corners)


def shoelace(quad: str) -> float | None:
    parts = [float(item) for item in quad.split(',')]
    if len(parts) != 8:
        return None
    pts = list(zip(parts[0::2], parts[1::2]))
    twice = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1]))
    return round(min(1.0, abs(twice) / 2), 3)


def measure_quality(image: Image.Image, corners: np.ndarray) -> dict:
    width, height = image.size
    xs = np.clip(corners[:, 0], 0, width - 1)
    ys = np.clip(corners[:, 1], 0, height - 1)
    left, top = int(xs.min()), int(ys.min())
    right, bottom = int(np.ceil(xs.max())), int(np.ceil(ys.max()))
    cropped = image.crop((left, top, max(left + 1, right), max(top + 1, bottom)))
    long_edge = max(cropped.size)
    if long_edge > 512:
        scale = 512 / long_edge
        cropped = cropped.resize((max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale))),
                                 Image.Resampling.BILINEAR)
    rgb = np.asarray(cropped.convert('RGB'), dtype=np.float64)
    luma = np.clip(np.round(rgb.mean(axis=2)), 0, 255)
    if luma.shape[0] < 3 or luma.shape[1] < 3:
        return {}
    padded = np.pad(luma, 1, mode='reflect')
    centre = padded[1:-1, 1:-1]
    lap = padded[:-2, 1:-1] + padded[2:, 1:-1] + padded[1:-1, :-2] + padded[1:-1, 2:] - 4 * centre
    sharpness = max(0.0, float(lap.var()))
    h, w = luma.shape
    left_i, top_i = int(w * 0.12), int(h * 0.12)
    inner = luma[top_i:h - top_i or h, left_i:w - left_i or w]
    glare = 0.0 if inner.size == 0 else float((inner >= 250).mean())
    return {'sharpness': round(sharpness, 1), 'glare': round(glare, 3)}


def _find_photo(photo_file: str) -> Path | None:
    name = Path(photo_file).name
    for root in PHOTO_ROOTS:
        for candidate in (root / photo_file, root / name, root / 'photos' / name, root / 'frozen-photos' / name):
            if candidate.is_file():
                return candidate
    return None


def build_panel(out: Path) -> tuple[Path, Path]:
    panel = out / 'panel'
    photos = panel / 'photos'
    photos.mkdir(parents=True, exist_ok=True)
    cases = []
    missing = []
    for line in PANEL_JSONL.read_text().splitlines():
        case = json.loads(line)['case']
        source = _find_photo(case['photo_file'])
        if source is None:
            missing.append(case['id'])
            continue
        dest = photos / Path(case['photo_file']).name
        if not dest.exists():
            dest.symlink_to(source)
        truth = case.get('manual_truth') or {}
        cases.append({
            'id': case['id'], 'kind': case['kind'], 'photo_file': f"photos/{dest.name}",
            'expected_card_ids': case.get('expected_card_ids') or [],
            'manual_truth': truth,
        })
    extras = (
        ('lugia-screenshot', LUGIA, 'ja:CLF-017', {'name': 'ルギアex', 'number': '017/032', 'language': 'ja'}),
        ('charmander-screenshot', CHARMANDER, 'en:sm3-18a', {'name': 'Charmander', 'number': '18a/147', 'language': 'en'}),
    )
    for case_id, source, expected, truth in extras:
        if not source.is_file():
            missing.append(case_id)
            continue
        dest = photos / f'{case_id}.jpg'
        if not dest.exists():
            Image.open(source).convert('RGB').save(dest, 'JPEG', quality=95)
        cases.append({
            'id': case_id, 'kind': 'slab', 'photo_file': f'photos/{dest.name}',
            'expected_card_ids': [expected], 'manual_truth': {'kind': 'slab', **truth},
        })
    if missing:
        raise SystemExit(f'missing photos: {missing}')
    cases_path = out / 'cases.json'
    cases_path.write_text(json.dumps(cases, ensure_ascii=False, indent=2))
    return panel, cases_path


def _split_slab(lines: list[dict]) -> tuple[list[dict], list[dict]]:
    label, card = [], []
    span = SLAB_CARD_END - SLAB_LABEL_END
    for line in lines:
        centre = line['y'] + line['h'] / 2
        if centre < SLAB_LABEL_END:
            label.append(line)
        elif centre <= SLAB_CARD_END:
            card.append({**line, 'y': min(1.0, max(0.0, (line['y'] - SLAB_LABEL_END) / span)),
                         'h': line['h'] / span})
    return label, card


def _client_text(name, name_conf, number, number_conf, ms, label: dict) -> str | None:
    from app.recognition.client_text import parse_client_text
    body = {'v': 1, 'engine': ENGINE, 'name': name,
            'name_conf': None if name is None else round(float(name_conf), 3),
            'number': number, 'number_conf': None if number is None else round(float(number_conf), 3),
            'ms': int(round(ms))}
    label = {key: value for key, value in label.items() if value is not None}
    if label:
        body['v'] = 2
        body.update(label)
    raw = json.dumps(body, ensure_ascii=False, separators=(',', ':'))
    if len(raw.encode()) > 768 and label:
        body = {key: value for key, value in body.items() if not key.startswith('label_')}
        body['v'] = 1
        raw = json.dumps(body, ensure_ascii=False, separators=(',', ':'))
    if len(raw.encode()) > 768:
        body['name'] = body['name_conf'] = None
        raw = json.dumps(body, ensure_ascii=False, separators=(',', ':'))
    hint, reason = parse_client_text(raw)
    if hint is None and reason in {'bad_number', 'bad_name'}:
        body['number' if reason == 'bad_number' else 'name'] = None
        if reason == 'bad_number':
            body['number_conf'] = None
        else:
            body['name_conf'] = None
        raw = json.dumps(body, ensure_ascii=False, separators=(',', ':'))
        hint, _reason = parse_client_text(raw)
    if hint is None and not label:
        return None
    return raw


def _pick_import():
    """Import the panel's name/number rules from the existing text simulator."""
    sys.path.insert(0, str(REPO / 'api'))
    sys.path.insert(0, str(REPO / 'api/scripts'))
    import simulate_client_text as text
    return text.pick_name, text.pick_number


def fields_main(out: Path, vision: Path) -> None:
    sys.path.insert(0, str(REPO / 'api'))
    pick_name, pick_number = _pick_import()
    from app.recognition.detect import _frame_rects, warp_to_rect
    import cv2
    panel, cases_path = build_panel(out)
    cases = json.loads(cases_path.read_text())
    crops = out / 'crops'
    crops.mkdir(exist_ok=True)
    prepared = []
    with tempfile.TemporaryDirectory() as scratch:
        vision_paths = []
        for case in cases:
            image = ImageOps.exif_transpose(Image.open(panel / case['photo_file'])).convert('RGB')
            rects = _frame_rects(np.asarray(image), 8)
            truth_kind = (case.get('manual_truth') or {}).get('kind')
            slab = case['kind'] == 'slab' or truth_kind == 'slab'
            outline = role = None
            aspect = image.width / image.height
            if case['id'] in RECORDED_SLAB:
                outline, role = corners_from_fractions(RECORDED_SLAB[case['id']], image.size), 'slab'
            elif rects:
                holders = [rect for rect in rects if holder_shaped(rect)]
                if slab and holders:
                    outline = max(holders, key=lambda rect: float(cv2.contourArea(rect)))
                    role = 'slab'
                else:
                    outline, role = rects[0], 'card'
            elif slab and 0.53 <= aspect <= 0.648:
                outline, role = full_frame(image), 'slab'
            elif 0.62 <= aspect <= 0.80:
                # The phone's own crop, already the card. Same rule as simulate_client_text.
                outline, role = full_frame(image), 'card'
            row = {
                'id': case['id'], 'kind': case['kind'], 'expected': case.get('expected_card_ids') or [],
                'manual_truth': case.get('manual_truth') or {}, 'card_quad': None, 'quad_role': role,
                'client_text': None, 'client_quality': None, 'crop_file': None,
            }
            if outline is not None:
                outline = jitter(outline, case['id'])
                window = slab_window(outline) if role == 'slab' else outline
                row['card_quad'] = fractions(outline, image.size)
                quality = measure_quality(image, window)
                fraction = shoelace(row['card_quad'])
                if fraction is not None:
                    quality['card_fraction'] = fraction
                row['client_quality'] = json.dumps(quality, separators=(',', ':')) if quality else None
                vision_path = Path(scratch) / f"{case['id']}.jpg"
                warp_to_rect(image, outline if role == 'slab' else window).save(vision_path, 'JPEG', quality=90)
                vision_paths.append(vision_path)
                embed_path = crops / f"{case['id']}.jpg"
                warp_to_rect(image, window).save(embed_path, 'JPEG', quality=90)
                row['crop_file'] = str(embed_path.relative_to(out))
            prepared.append(row)
        reply = subprocess.run([str(vision)], input=''.join(f'{path}\n' for path in vision_paths),
                               capture_output=True, text=True, check=True)
        if reply.returncode != 0:
            raise SystemExit(reply.stderr)
        seen = {Path(item['path']).stem: item for item in map(json.loads, reply.stdout.splitlines())}
    for row in prepared:
        item = seen.get(row['id'])
        if not item or 'error' in item:
            continue
        lines = item['lines']
        label = {}
        if row['quad_role'] == 'slab':
            label_lines, lines = _split_slab(lines)
            label = parse_slab_label(label_lines)
        name, name_conf = pick_name(lines)
        number, number_conf = pick_number(lines)
        row['client_text'] = _client_text(name, name_conf, number, number_conf, item['ms'], label)
        row['vision_ms'] = round(item['ms'], 1)
    (out / 'stage0.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in prepared))
    print(f'fields {len(prepared)} -> {out / "stage0.jsonl"}', flush=True)


def encode(vector: np.ndarray) -> str:
    unit = np.asarray(vector, np.float32).reshape(-1)
    unit = unit / np.linalg.norm(unit)
    return base64.b64encode(unit.astype('<f2').tobytes()).decode('ascii')


def prepare_nchw(image: Image.Image) -> np.ndarray:
    rgb = image.convert('RGB')
    scale = 224 / max(rgb.size)
    resized = rgb.resize((max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale))), Image.Resampling.BICUBIC)
    canvas = Image.new('RGB', (224, 224), (0, 0, 0))
    canvas.paste(resized, ((224 - resized.width) // 2, (224 - resized.height) // 2))
    array = np.asarray(canvas, dtype=np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    return np.transpose((array - mean) / std, (2, 0, 1))[None, ...]


def embed(out: Path, model: Path) -> None:
    import coremltools as ct
    ml = ct.models.MLModel(str(model), compute_units=ct.ComputeUnit.ALL)
    rows = [json.loads(line) for line in (out / 'stage0.jsonl').read_text().splitlines()]
    warmup = next((row for row in rows if row.get('crop_file')), None)
    if warmup:
        ml.predict({'pixel_values': prepare_nchw(Image.open(out / warmup['crop_file']))})
    for row in rows:
        if not row.get('crop_file'):
            continue
        started = time.perf_counter()
        vector = np.asarray(ml.predict({'pixel_values': prepare_nchw(Image.open(out / row['crop_file']))})['embedding'],
                            np.float32)
        row['client_embedding'] = json.dumps({'model': MODEL_ID, 'vector': encode(vector)}, separators=(',', ':'))
        row['embed_ms'] = round((time.perf_counter() - started) * 1000, 1)
    (out / 'stage0.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows))
    print(f'embed {sum(1 for row in rows if row.get("client_embedding"))} vectors', flush=True)


def convert(onnx_path: Path, model: Path) -> None:
    import coremltools as ct
    import coremltools.optimize.coreml as cto
    import onnx
    import torch
    from onnx2torch import convert as onnx_to_torch
    loaded = onnx.load(str(onnx_path))
    # Opset 17 leaves an omitted Clip max as an empty input name. onnx2torch
    # treats that as a dynamic bound. Dropping it keeps the lower bound only.
    # The position-embedding resize is cubic. Core ML's PyTorch front end has
    # no bicubic upsample; linear on that one grid stays within 0.001 cosine
    # of the server model, before 8-bit palettization.
    for node in loaded.graph.node:
        if node.op_type == 'Resize':
            for attr in node.attribute:
                if attr.name == 'mode' and attr.s == b'cubic':
                    attr.s = b'linear'
        if node.op_type == 'Clip' and any(not item for item in node.input):
            kept = [item for item in node.input if item]
            del node.input[:]
            node.input.extend(kept)
    traced = torch.jit.trace(onnx_to_torch(loaded).eval(), torch.zeros(1, 3, 224, 224))
    example = torch.zeros(1, 3, 224, 224)
    ml = ct.convert(traced, inputs=[ct.TensorType(name='pixel_values', shape=example.shape)],
                    outputs=[ct.TensorType(name='embedding')], convert_to='mlprogram',
                    compute_precision=ct.precision.FLOAT16, minimum_deployment_target=ct.target.iOS17)
    ml = cto.palettize_weights(ml, cto.OptimizationConfig(
        global_config=cto.OpPalettizerConfig(nbits=8, mode='kmeans')))
    model.parent.mkdir(parents=True, exist_ok=True)
    ml.save(str(model))
    print('saved', model, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('fields', 'embed', 'convert'))
    parser.add_argument('--out', type=Path, default=REPO / 'data/latency/stage0-simulation-20261021')
    parser.add_argument('--vision', type=Path, default=Path('/tmp/vision_text'))
    parser.add_argument('--model', type=Path)
    parser.add_argument('--onnx', type=Path)
    args = parser.parse_args()
    if args.mode == 'fields':
        fields_main(args.out, args.vision)
    elif args.mode == 'embed':
        embed(args.out, args.model)
    else:
        convert(args.onnx, args.model)


if __name__ == '__main__':
    main()
