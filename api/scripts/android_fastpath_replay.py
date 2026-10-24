"""Offline replay of the Galaxy A55 157-photo panel through the stage 1 / 1b gate.

Rebuilds the ``client_text`` the phone sent from the captured ML Kit lines (the
app's own rules, ported in ``dart_card_text_port.py``), takes the phone's corners
and embedding where they exist, runs the real ``evaluate_stage1`` against the
local catalogue and artwork verifier, and scores early answers against the labels.

No uploads, result writes or network. Photos and OCR text stay local; only
aggregate counts and photo ids go in the output.

    OPENBLAS_NUM_THREADS=1 .venv/bin/python api/scripts/android_fastpath_replay.py \\
        --ocr /path/to/a55-fastpath-ocr-157.json --output out.json [--number-repair] ...

Each accepted fix has its own flag, default off, as in production.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from dataclasses import asdict
import json
import re
from pathlib import Path
import sqlite3
import sys
import time
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.recognition.local_match import FULL_ART_BOX, FULL_ART_RARITIES, LocalArtworkVerifier  # noqa: E402
from app.recognition.stage1_answer import evaluate_stage1  # noqa: E402
from app.recognition.stage1_gate import GateOptions, same_card  # noqa: E402
from app.scan_summary import parse_quad  # noqa: E402
from dart_card_text_port import CardText, Line  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MAIN = Path.home() / 'WebstormProjects/scanapp'
PARITY = 'data/latency/android-recognition-parity-20261023'
MODEL_ID = '2ddf6ec79e37/coreml-pal8'


RAW_NUMBER = re.compile(r'(?<![0-9])(?:[A-Za-z]{2,4}[0-9Oo]{2,3}|[0-9OoIl|]{1,4}[A-Za-z]?\s*[/T)]\s*[0-9OoIl|]{1,4}|[0-9OoIl|]{5,7})(?![0-9])')
YEAR = re.compile(r'^(?:19|20)\d\d$|^0?(?:19|20)\d\d$')


def raw_footer_number(on_card: list[Line]) -> str | None:
    """WHAT-IF ONLY: the most confident footer token that looks number-ish, unvalidated.

    The shipped app drops any number the bundled set totals do not hold, so the server
    never sees these. This measures what a future app sending the raw token could gain.
    """
    best = None
    for line in on_card:
        if line.centre_y < .80:
            continue
        for match in RAW_NUMBER.finditer(line.text):
            token = match.group(0).strip()
            digits = sum(c.isdigit() or c in 'OoIl|' for c in token)
            if digits >= 3 and not YEAR.match(token) and (best is None or (line.conf or 0) > best[0]):
                best = (line.conf or 0, token)
    return best[1] if best else None


def load_panel(data_root: Path, ocr_path: Path, set_totals_dart: Path, raw_number: bool = False):
    parity = data_root / PARITY
    per_photo = {row['id']: row for row in json.loads((parity / 'a55-fresh157-per-photo.json').read_text())['panel']}
    comparison = {row['id']: row for row in json.loads((parity / 'a55-per-photo-comparison.json').read_text())['rows']}
    vectors = {row['id']: row for row in json.loads((parity / 'a55-exact-quad-vectors-geometry-fixed.json').read_text())['results']}
    manifest = json.loads((parity / 'frozen-panel/manifest.json').read_text())['photos']
    capture = json.loads(ocr_path.read_text())['results']
    assert len(capture) == len(manifest) == len(per_photo) == 157
    card_text = CardText(str(set_totals_dart))
    rows = []
    for photo, shot in zip(manifest, capture):
        pid = photo['id']
        read = next(e['read'] for e in shot['phone_events'] if e['event'] == 'text.capture')
        lines = [Line(l['text'], l['x'], l['y'], l['w'], l['h'], l.get('confidence')) for l in read['lines']]
        live = per_photo[pid]
        quad = None
        flat = comparison[pid]['android_gallery_quad'] if live['quad_sent'] else None
        if flat:
            quad = [(flat[i], flat[i + 1]) for i in range(0, 8, 2)]
        on_card = card_text.lines_on_card(lines, read['width'], read['height'], quad)
        client_text = card_text.client_text(on_card) if on_card is not None else None
        if raw_number and on_card is not None:
            body = json.loads(client_text) if client_text else None
            if body and body.get('name') and not body.get('number'):
                body['number'] = raw_footer_number(on_card)
                client_text = json.dumps(body)
        # One live photo sent a quad that was never stored; without it neither quad nor vector can be replayed.
        vector = vectors.get(pid, {}).get('android_vector') if live['client_embedding_sent'] and quad else None
        rows.append({
            'id': pid, 'file': photo['photo_file'], 'expected': photo['expected_card_ids'],
            'client_text': client_text,
            'client_embedding': json.dumps({'model': MODEL_ID, 'vector': vector}) if vector else None,
            'quad': ','.join(f'{v:.5f}' for point in quad for v in point) if quad else None,
            'live': {'stage': live['android_stage'], 'text_sent': live['client_text_sent'],
                     'quad_sent': live['quad_sent'], 'embedding_sent': live['client_embedding_sent'],
                     'reason': (live.get('server_stage0') or {}).get('stage1_reason'),
                     'vector_top': (live.get('server_stage0') or {}).get('vector_top'),
                     'vector_top_score': (live.get('server_stage0') or {}).get('vector_top_score')},
        })
    return rows


def server_quad_vectors(rows, panel: Path, model: Path, cache: Path) -> dict[str, str]:
    """Stand-in phone vectors: the server's DINO on the exact gallery-quad crop (as exact-quad-server-vectors.py).

    The live phone vectors were not retained. The stored Android vectors used a fixture
    quad, not the gallery quad that was sent. The server model agrees with the phone
    model to about 0.998 cosine on the same crop.
    """
    if cache.exists():
        return json.loads(cache.read_text())
    from PIL import Image, ImageOps
    from app.recognition.detect import client_quad_rect, warp_to_rect
    from app.recognition.embed import DinoEmbedder
    embedder = DinoEmbedder(str(model), 1, 1)
    out = {}
    for row in rows:
        if not row['quad'] or not row['live']['embedding_sent']:
            continue
        vals = [float(x) for x in row['quad'].split(',')]
        with Image.open(panel / row['file']) as raw:
            image = ImageOps.exif_transpose(raw).convert('RGB')
        rect = client_quad_rect(image, list(zip(vals[::2], vals[1::2])))
        if rect is None:
            continue
        pts = rect.tolist()
        edge = lambda a, b: ((pts[a][0] - pts[b][0]) ** 2 + (pts[a][1] - pts[b][1]) ** 2) ** .5
        wide, tall = (edge(0, 1) + edge(3, 2)) / 2, (edge(0, 3) + edge(1, 2)) / 2
        if .53 <= min(wide, tall) / max(wide, tall) <= .648:
            def at(x, y):
                return tuple((pts[0][c] * (1 - x) + pts[1][c] * x) * (1 - y) + (pts[3][c] * (1 - x) + pts[2][c] * x) * y
                             for c in range(2))
            pts = [at(.06, .18), at(.94, .18), at(.94, .90), at(.06, .90)]
        crop = warp_to_rect(image, np.asarray(pts, dtype=np.float32))
        vector = embedder.embed(crop, 'pad').astype('<f2')
        out[row['id']] = base64.b64encode(vector.tobytes()).decode('ascii')
    cache.write_text(json.dumps(out))
    return out


def build_runtime(kit: Path, totals_json: Path, model: Path | None = None):
    ids = np.load(kit / 'vectors/pad/embedding_card_ids.npy', allow_pickle=False).astype(str).tolist()
    embeddings = np.asarray(np.load(kit / 'vectors/pad/embeddings.npy'), dtype=np.float32)
    embeddings /= np.clip(np.linalg.norm(embeddings, axis=1, keepdims=True), 1e-8, None)
    source = sqlite3.connect(f'file:{kit / "catalog.sqlite"}?mode=ro', uri=True)
    catalog = sqlite3.connect(':memory:')
    source.backup(catalog)
    source.close()
    catalog.row_factory = sqlite3.Row
    # The kit's set_totals table is empty; use the frozen public-only staging snapshot, as PR #67 did.
    catalog.executemany(
        'INSERT OR REPLACE INTO set_totals(language,set_id,official_total,fetched_at) VALUES (?,?,?,?)',
        [(r['language'], r['set_id'], r['official_total'], '2026-10-22') for r in json.loads(totals_json.read_text())])
    verifier = LocalArtworkVerifier(kit)
    verifier.reference_boxes = {row['id']: FULL_ART_BOX for row in catalog.execute('SELECT id,rarity FROM cards')
                                if str(row['rarity'] or '').casefold() in FULL_ART_RARITIES}
    runtime = SimpleNamespace(snapshot=SimpleNamespace(embeddings=embeddings, card_ids=ids), artwork_verifier=verifier)
    if model is not None:
        from app.recognition.embed import DinoEmbedder
        runtime.embedder = DinoEmbedder(str(model), 1, 1)  # the production thread settings
        runtime.require = lambda: (runtime.snapshot, runtime.embedder, None)
    return runtime, catalog


def run(rows, runtime, catalog, photos: Path, *, extra: dict) -> dict:
    # The shipped configuration (compose.dokploy.yaml): every earlier stage 1 flag on.
    flags = {'stage1_' + key: True for key in ('set_totals', 'normalize_duplicates', 'printing_groups',
                                                'promo_numbers', 'diagnostics')}
    settings = SimpleNamespace(stage1b_text_verify=True, **flags, **extra)
    found = {}
    cpu = {}
    phases: dict[str, dict[str, float]] = {}
    runtime.stage1_catalogue = None  # options differ between runs; load once per run, as the server does
    import app.recognition.stage1_answer as answer

    def timed(name, function):
        def wrapper(*args, **kwargs):
            started = time.process_time()
            try:
                return function(*args, **kwargs)
            finally:
                phases.setdefault(current[0], {})[name] = phases.get(current[0], {}).get(name, 0.) + time.process_time() - started
        return wrapper
    current = ['']
    originals = (answer._server_frame_vector, answer._artwork)
    answer._server_frame_vector = timed('frame_and_embed_s', originals[0])
    answer._artwork = timed('artwork_s', originals[1])
    # First photo pays the one-off catalogue load; warm it so timings describe a running server.
    answer._catalogue(runtime, catalog, GateOptions.from_settings(settings))
    for row in rows:
        current[0] = row['id']
        image = (photos / row['file']).read_bytes()
        started = time.process_time()
        decision = evaluate_stage1(settings=settings, runtime=runtime, catalog=catalog,
                                   client_text=row['client_text'], client_embedding=row['client_embedding'],
                                   card_quad=parse_quad(row['quad']), image_bytes=image)
        cpu[row['id']] = time.process_time() - started
        correct = None
        if decision.answered:
            offered = decision.printing_ids or (decision.card_id,)
            correct = any(same_card(card, expected) for card in offered for expected in row['expected'])
        found[row['id']] = {**asdict(decision), 'correct': correct}
    answer._server_frame_vector, answer._artwork = originals
    return {'decisions': found, 'cpu_s': cpu, 'phases_s': phases}


def summarize(result: dict, rows) -> dict:
    decisions = result['decisions']
    answered = [k for k, d in decisions.items() if d['answered']]
    return {
        'early_answers': len(answered),
        'by_stage': dict(Counter(decisions[k]['stage'] for k in answered)),
        'wrong': [k for k in answered if decisions[k]['correct'] is False],
        'reasons': dict(Counter(d['reason'] for d in decisions.values() if not d['answered'])),
        'answered_ids': answered,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ocr', type=Path, required=True, help='local A55 ML Kit capture (never committed)')
    parser.add_argument('--data-root', type=Path, default=MAIN)
    parser.add_argument('--set-totals-dart', type=Path, default=Path.home() / 'StudioProjects/PokeSingle/lib/data/set_totals.dart')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--vectors', choices=('android', 'server-gallery-quad'), default='server-gallery-quad')
    parser.add_argument('--vector-cache', type=Path, help='cache for the stand-in vectors (local, never committed)')
    parser.add_argument('--number-repair', action='store_true')
    parser.add_argument('--fuzzy-name', action='store_true')
    parser.add_argument('--server-frame', action='store_true')
    parser.add_argument('--whatif-raw-number', action='store_true', help='send the raw footer token when the app sent no number (needs an app change)')
    args = parser.parse_args()
    data = args.data_root
    panel = data / 'data/latency/stage0-simulation-20261021'
    rows = load_panel(data, args.ocr, args.set_totals_dart, args.whatif_raw_number)
    if args.vectors == 'server-gallery-quad':
        cache = args.vector_cache or args.output.with_name('gallery-quad-vectors.json')
        vectors = server_quad_vectors(rows, panel / 'panel', data / 'data/android-embedding-research-20261023/teacher/dinov2_small.onnx', cache)
        for row in rows:
            vector = vectors.get(row['id'])
            row['client_embedding'] = json.dumps({'model': MODEL_ID, 'vector': vector}) if vector else None
    runtime, catalog = build_runtime(panel / 'kit', ROOT / 'api/tests/fixtures/stage1-set-totals-20261022.json',
                                     data / 'data/android-embedding-research-20261023/teacher/dinov2_small.onnx')
    extra = {}
    for flag in ('number_repair', 'fuzzy_name'):
        if getattr(args, flag):
            extra['stage1_' + flag] = True
    if args.server_frame:
        extra['stage1b_server_frame'] = True
    result = run(rows, runtime, catalog, panel / 'panel', extra=extra)
    summary = summarize(result, rows)
    summary['text_sent_rebuilt'] = sum(r['client_text'] is not None for r in rows)
    summary['text_sent_live'] = sum(bool(r['live']['text_sent']) for r in rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'summary': summary, 'decisions': result['decisions'],
                                       'cpu_s': result['cpu_s'], 'phases_s': result['phases_s'], 'extra_flags': extra}, indent=1) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'answered_ids'}, indent=1))


if __name__ == '__main__':
    main()
