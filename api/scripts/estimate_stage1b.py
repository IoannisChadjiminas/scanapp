"""Stage 1b: when the phone's text names one card and stage 1 abstained, check that card's artwork.

The full pipeline is not run. One local artwork verification, on the phone's
corners, against that one reference. A strong visual contradiction (another
card ahead by 0.05) is never answered.

    python api/scripts/estimate_stage1b.py \\
        --panel data/latency/stage0-simulation-20261021/stage0.jsonl \\
        --photos data/latency/stage0-simulation-20261021/panel \\
        --cases data/latency/stage0-simulation-20261021/cases.json \\
        --index data/latency/stage0-simulation-20261021/kit/vectors/pad \\
        --catalog data/latency/stage0-simulation-20261021/kit/catalog.sqlite \\
        --references data/latency/stage0-simulation-20261021/kit \\
        --replay data/latency/stage0-simulation-20261021/replay.jsonl \\
        --out data/latency/stage0-simulation-20261021/stage1b.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

import sys
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'api'))
sys.path.insert(0, str(REPO / 'api/scripts'))

from app.recognition.detect import warp_to_rect  # noqa: E402
from app.recognition.local_match import FULL_ART_BOX, FULL_ART_RARITIES, LocalArtworkVerifier  # noqa: E402
from estimate_stage1 import (  # noqa: E402
    at_margin, collapse_hits, decode_vector, duplicate_pairs, evaluate, group_of, load_cards,
    lookup, matches_expected, same_card,
)

TWIN_COSINE = 0.84
CONTRADICTION = 0.05
STAGE1_MARGIN = 0.02
SWEEP = (10, 15, 20, 25, 30, 40, 60)


def corners_of(quad: str, size: tuple[int, int]) -> np.ndarray:
    width, height = size
    parts = [float(item) for item in quad.split(',')]
    return np.array([[parts[i] * (width - 1), parts[i + 1] * (height - 1)] for i in range(0, 8, 2)], np.float32)


def one_card(hits: list[dict], language: str | None, index, position) -> tuple[dict | None, str]:
    """Exactly one card, or one language of a twin pair. Anything else abstains."""
    if len(hits) == 1:
        return hits[0], 'unique'
    if len(hits) < 2 or not language:
        return None, 'ambiguous' if hits else 'none'
    for left in range(len(hits)):
        for right in range(left + 1, len(hits)):
            a, b = hits[left], hits[right]
            if (a.get('language') or '') == (b.get('language') or ''):
                return None, 'ambiguous'
            if a['id'] not in position or b['id'] not in position:
                return None, 'ambiguous'
            cosine = float(index[position[a['id']]] @ index[position[b['id']]])
            if cosine < TWIN_COSINE:
                return None, 'ambiguous'
    chosen = [card for card in hits if card.get('language') == language]
    if len(chosen) == 1:
        return chosen[0], 'twin_language'
    return None, 'ambiguous'


def contradiction(photo_scores, ids, position, index, exact, top_id: str | None, top_score: float | None, text_id: str):
    """True when a different, non-twin card leads the text card by at least 0.05.

    A twin is the round 2 pair: reference cosine at least 0.84 and different languages.
    """
    if not top_id or top_score is None or text_id not in position:
        return False, None
    gap = float(top_score) - float(photo_scores[position[text_id]])
    if same_card(top_id, text_id):
        return False, gap
    twin = False
    if top_id in position:
        cosine = float(index[position[top_id]] @ index[position[text_id]])
        top_card, text_card = exact.get(top_id), exact.get(text_id)
        languages = {top_card.get('language') if top_card else None, text_card.get('language') if text_card else None}
        twin = cosine >= TWIN_COSINE and None not in languages and len(languages) == 2
    return (not twin) and gap >= CONTRADICTION, gap


def reference_path(kit: Path, image_path: str | None) -> Path | None:
    if not image_path:
        return None
    path = kit / 'reference-images' / Path(image_path).name
    return path if path.is_file() else None


def check_artwork(verifier, photo: Image.Image, quad: str | None, reference: tuple[str, str]) -> dict:
    """Verify the phone's warped corners, then one propose_frame retry on the upload."""
    started = time.perf_counter()
    warped_ms = frame_ms = 0.0
    match = None
    how = None
    if quad:
        warp_started = time.perf_counter()
        warped = warp_to_rect(photo, corners_of(quad, photo.size))
        found = verifier.verify(warped, [reference])
        warped_ms = (time.perf_counter() - warp_started) * 1000
        if found:
            match, how = found[0], 'phone_quad'
    if match is None:
        frame_started = time.perf_counter()
        aligned = verifier.propose_frame(photo, reference)
        found = verifier.verify(aligned, [reference]) if aligned is not None else []
        frame_ms = (time.perf_counter() - frame_started) * 1000
        if found:
            match, how = found[0], 'propose_frame'
    return {
        'verified': match is not None,
        'how': how,
        'inliers': None if match is None else match.inliers,
        'artwork_inliers': None if match is None else match.artwork_inliers,
        'warp_ms': round(warped_ms, 1),
        'frame_ms': round(frame_ms, 1),
        'verify_ms': round((time.perf_counter() - started) * 1000, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--panel', type=Path, required=True)
    parser.add_argument('--photos', type=Path, required=True)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--references', type=Path, required=True, help='kit directory that contains reference-images/')
    parser.add_argument('--replay', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.panel.read_text().splitlines()]
    photos = {case['id']: args.photos / case['photo_file'] for case in json.loads(args.cases.read_text())}
    replay = {row['id']: row for row in map(json.loads, args.replay.read_text().splitlines())}
    ids = np.load(args.index / 'embedding_card_ids.npy', allow_pickle=False).astype(str)
    index = np.asarray(np.load(args.index / 'embeddings.npy', mmap_mode='r'), dtype=np.float32)
    index = index / np.clip(np.linalg.norm(index, axis=1, keepdims=True), 1e-8, None)
    cards = load_cards(args.catalog)
    by_key: dict[str, list] = {}
    for card in cards:
        for key in card['keys']:
            by_key.setdefault(key, []).append(card)
    by_id, exact = {}, {}
    for card in cards:
        exact[card['id']] = card
        by_id[card['id']] = card
        if card['id'].startswith('en:'):
            by_id.setdefault(card['id'].split(':', 1)[1], card)
    bare_ids = {bare['id'] for bare, _en in duplicate_pairs(cards)}
    position: dict[str, int] = {}
    for slot, card_id in enumerate(ids.tolist()):
        position.setdefault(str(card_id), slot)
    vectors = np.zeros((len(rows), index.shape[1]), np.float32)
    for slot, row in enumerate(rows):
        vector = decode_vector(row.get('client_embedding'))
        row['_has_vector'] = vector is not None and vector.shape == (index.shape[1],)
        if row['_has_vector']:
            vectors[slot] = vector
    search_started = time.perf_counter()
    scores = index @ vectors.T
    search_ms = (time.perf_counter() - search_started) * 1000 / max(1, len(rows))
    evaluated = evaluate(rows, scores, ids, index, position, by_key, by_id, exact, replay, bare_ids,
                         collapse=True, twins=True, twin_cosine=TWIN_COSINE)
    stage1 = at_margin(evaluated, STAGE1_MARGIN)
    answered = {item['id'] for item in stage1['answers']}

    catalog = sqlite3.connect(args.catalog)
    catalog.row_factory = sqlite3.Row
    paths = {str(row['id']): row['image_path'] for row in catalog.execute('SELECT id, image_path FROM cards')}
    for card in cards:
        card['image_path'] = paths.get(card['id'])
    verifier = LocalArtworkVerifier(args.references)
    verifier.reference_boxes = {
        str(row['id']): FULL_ART_BOX for row in catalog.execute('SELECT id, rarity FROM cards')
        if str(row['rarity'] or '').casefold() in FULL_ART_RARITIES}

    attempts = []
    for slot, (item, row) in enumerate(zip(evaluated, rows)):
        if item['id'] in answered:
            continue
        lookup_started = time.perf_counter()
        hits = lookup(by_key, item['text_name'], item['text_number'], item['text_language'])
        hits = collapse_hits(hits, bare_ids)
        card, how = one_card(hits, item['text_language'], index, position)
        lookup_ms = (time.perf_counter() - lookup_started) * 1000
        record = {
            'id': item['id'], 'group': item['group'], 'quad_role': row.get('quad_role'),
            'expected': item['expected'], 'text_name': item['text_name'], 'text_number': item['text_number'],
            'lookup': how, 'lookup_ms': round(lookup_ms, 3), 'search_ms': round(search_ms, 3),
            'vector_id': item['vector_id'], 'vector_margin': item['margin'],
            'pipeline_cpu_ms': item.get('pipeline_cpu_ms'),
            'pipeline_total_ms': (replay.get(item['id']) or {}).get('timings', {}).get('total_ms'),
        }
        if card is None:
            record['reason'] = 'no_unique_text' if how == 'none' else 'ambiguous_text'
            attempts.append(record)
            continue
        record['card'] = card['id']
        top_score = None
        if row.get('_has_vector') and item['vector_id'] in position:
            top_score = float(scores[position[item['vector_id']], slot])
        blocked, gap = contradiction(scores[:, slot], ids, position, index, exact,
                                     item['vector_id'], top_score, card['id'])
        record['vector_gap'] = None if gap is None else round(gap, 4)
        record['contradiction'] = blocked
        path = reference_path(args.references, card.get('image_path'))
        if path is None:
            record['reason'] = 'no_reference'
            attempts.append(record)
            continue
        photo_path = photos.get(item['id'])
        if photo_path is None or not photo_path.is_file() or not row.get('card_quad'):
            record['reason'] = 'no_phone_corners'
            attempts.append(record)
            continue
        photo = ImageOps.exif_transpose(Image.open(photo_path)).convert('RGB')
        artwork = check_artwork(verifier, photo, row.get('card_quad'), (card['id'], str(path)))
        record.update(artwork)
        record['correct'] = matches_expected(card['id'], item['expected'])
        if blocked:
            record['reason'] = 'visual_contradiction'
        elif not artwork['verified']:
            record['reason'] = 'artwork_miss'
        else:
            record['reason'] = 'verified'
        attempts.append(record)
        print(f"{item['id']} {record['reason']} {card['id']} inliers={artwork['artwork_inliers']} {artwork['verify_ms']:.0f}ms",
              flush=True)

    verified = [item for item in attempts if item.get('reason') == 'verified']

    def at_inliers(minimum: int) -> dict:
        picked = [item for item in verified if (item.get('artwork_inliers') or 0) >= minimum and not item['contradiction']]
        # contradiction is already excluded from reason==verified. Keep the filter explicit.
        return {
            'minimum': minimum,
            'answered': len(picked),
            'correct': sum(item['correct'] for item in picked),
            'wrong': sum(not item['correct'] for item in picked),
        }

    sweep = [at_inliers(minimum) for minimum in SWEEP]
    safe = [row for row in sweep if row['wrong'] == 0]
    recommended = max(safe, key=lambda row: row['answered'])['minimum'] if safe else None
    # The verifier already refuses fewer than 10 artwork inliers. Prefer that floor when it is safe.
    if any(row['minimum'] == 10 and row['wrong'] == 0 for row in sweep):
        recommended = 10
    answers = [item for item in verified if recommended is not None and (item.get('artwork_inliers') or 0) >= recommended]
    near = [item for item in attempts if item.get('reason') == 'visual_contradiction' and item.get('verified')]
    if recommended and recommended > 10:
        near.extend(item for item in verified if (item.get('artwork_inliers') or 0) < recommended)

    def pack(name: str, picked: list[dict]) -> dict:
        return {
            'answered': sum(item['group'] == name for item in picked),
            'wrong': sum(item['group'] == name and not item['correct'] for item in picked),
        }

    combined_ids = answered | {item['id'] for item in answers}
    # Stage 1 answers are correct by the round 3 run; add stage 1b.
    stage1_by_group = stage1['groups']
    summary = {
        'stage1': {'answered': stage1['answered'], 'wrong': stage1['wrong'], 'groups': stage1_by_group},
        'stage1b': {
            'answered': len(answers),
            'correct': sum(item['correct'] for item in answers),
            'wrong': sum(not item['correct'] for item in answers),
            'threshold': recommended,
            'groups': {name: pack(name, answers) for name in ('raw', 'slab', 'phone', 'screenshot')},
        },
        'together': len(combined_ids),
        'sweep': sweep,
        'search_ms_per_photo': round(search_ms, 3),
        'answers': [{
            'id': item['id'], 'group': item['group'], 'quad_role': item['quad_role'], 'card': item['card'],
            'correct': item['correct'], 'inliers': item['inliers'], 'artwork_inliers': item['artwork_inliers'],
            'how': item['how'], 'vector_id': item['vector_id'], 'vector_margin': item['vector_margin'],
            'vector_gap': item['vector_gap'], 'verify_ms': item['verify_ms'],
            'lookup_ms': item['lookup_ms'], 'search_ms': item['search_ms'],
            'pipeline_cpu_ms': item['pipeline_cpu_ms'], 'pipeline_total_ms': item['pipeline_total_ms'],
        } for item in answers],
        'near_misses': [{
            'id': item['id'], 'group': item['group'], 'card': item.get('card'), 'reason': item['reason'],
            'artwork_inliers': item.get('artwork_inliers'), 'vector_id': item.get('vector_id'),
            'vector_gap': item.get('vector_gap'), 'correct': item.get('correct'),
        } for item in near],
        'pipeline_reasons': {},
    }
    reasons: dict[str, int] = {}
    by_group: dict[str, dict[str, int]] = {}
    for item in attempts:
        if item['id'] in {row['id'] for row in answers}:
            reason = 'stage1b_answered'
        else:
            reason = item['reason']
            reasons[reason] = reasons.get(reason, 0) + 1
        bucket = by_group.setdefault(item['group'], {})
        bucket[reason] = bucket.get(reason, 0) + 1
    reasons['stage1_answered'] = stage1['answered']
    summary['pipeline_reasons'] = reasons
    summary['reasons_by_group'] = by_group
    summary['answer_how'] = {}
    for item in answers:
        summary['answer_how'][item['how']] = summary['answer_how'].get(item['how'], 0) + 1
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({key: summary[key] for key in (
        'stage1', 'stage1b', 'together', 'sweep', 'pipeline_reasons', 'reasons_by_group', 'answer_how')}, indent=2))


if __name__ == '__main__':
    main()
