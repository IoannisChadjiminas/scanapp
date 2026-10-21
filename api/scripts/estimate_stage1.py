"""Estimate a cheap stage-1 answer from simulated phone fields.

Stage 1 answers only when the phone vector's top card, the printed number and the
name are the same card, with a visual margin. Slabs use the label's name, number
and language. The search is brute-force cosine over the exported index.

    python api/scripts/estimate_stage1.py --panel data/latency/stage0-simulation-20261021/stage0.jsonl \\
        --index data/latency/stage0-simulation-20261021/kit/vectors/pad \\
        --catalog data/latency/stage0-simulation-20261021/kit/catalog.sqlite \\
        --replay data/latency/stage0-simulation-20261021/replay.jsonl \\
        --log data/latency/stage0-simulation-20261021/server.log \\
        --out data/latency/stage0-simulation-20261021/stage1.json
"""
from __future__ import annotations

import argparse
import base64
import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'api'))
from app.recognition.label_identity import number_key  # noqa: E402
from app.recognition.rank import name_match, number_match  # noqa: E402


def same_card(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    if left.startswith('en:') and left.split(':', 1)[1] == right:
        return True
    if right.startswith('en:') and right.split(':', 1)[1] == left:
        return True
    return False


def matches_expected(card_id: str | None, expected: list[str]) -> bool:
    return any(same_card(card_id, item) for item in expected)


def group_of(row: dict) -> str:
    if str(row['id']).endswith('-screenshot'):
        return 'screenshot'
    if row.get('kind') in {'phone_capture', 'reported_phone'}:
        return 'phone'
    return row.get('kind') or 'unknown'


def decode_vector(raw: str | None) -> np.ndarray | None:
    if not raw:
        return None
    try:
        body = json.loads(raw)
        data = base64.b64decode(body['vector'])
    except (ValueError, KeyError, TypeError):
        return None
    vector = np.frombuffer(data, dtype='<f2').astype(np.float32)
    if vector.shape != (384,) or not np.isfinite(vector).all():
        return None
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else None


def load_cards(path: Path) -> list[dict]:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    rows = []
    for row in db.execute(
            'SELECT id, name, view_title, collector_number, printed_collector_number, language, set_name '
            'FROM cards'):
        item = dict(row)
        item['keys'] = {key for key in (number_key(item['collector_number']), number_key(item['printed_collector_number'])) if key}
        rows.append(item)
    return rows


def number_ok(phone: str | None, card: dict) -> bool:
    if not phone:
        return False
    identifiers = [card['collector_number'], card['printed_collector_number']]
    results = [number_match([phone], item) for item in identifiers if item]
    if any(result is True for result in results):
        return True
    if any(result is False for result in results):
        return False
    return number_key(phone) in card['keys']


def name_ok(phone: str | None, card: dict) -> bool:
    if not phone:
        return False
    return name_match(phone, card['name']) or bool(card['view_title'] and name_match(phone, card['view_title']))


def lookup(by_key: dict[str, list[dict]], name: str | None, number: str | None, language: str | None) -> list[dict]:
    if not name or not number:
        return []
    pool = by_key.get(number_key(number) or '', [])
    return [card for card in pool if number_ok(number, card) and name_ok(name, card)
            and (language is None or card['language'] == language)]


def text_fields(row: dict) -> dict:
    body = {}
    if row.get('client_text'):
        try:
            body = json.loads(row['client_text'])
        except ValueError:
            body = {}
    quality = {}
    if row.get('client_quality'):
        try:
            quality = json.loads(row['client_quality'])
        except ValueError:
            quality = {}
    return body, quality


def search_top(index: np.ndarray, ids: np.ndarray, vector: np.ndarray) -> tuple[str, float, str, float]:
    scores = index @ vector
    order = np.argpartition(-scores, 6)[:6]
    order = order[np.argsort(-scores[order])]
    top = str(ids[order[0]])
    second = top
    second_score = float(scores[order[0]])
    for slot in order[1:]:
        candidate = str(ids[slot])
        if not same_card(candidate, top):
            second, second_score = candidate, float(scores[slot])
            break
    return top, float(scores[order[0]]), second, second_score


def reason_for(row: dict, cards_by_id: dict) -> str:
    if row.get('vector_id') is None:
        return 'no_embedding'
    if not row.get('text_name') or not row.get('text_number'):
        if row.get('name_right') is False:
            return 'text_misread'
        if row.get('number_right') is False:
            return 'number_misread'
        return 'no_text'
    if row.get('text_status') == 'ambiguous':
        return 'ambiguous_text'
    if row.get('text_status') != 'unique':
        if row.get('number_right') is False:
            return 'number_misread'
        if row.get('name_right') is False:
            return 'text_misread'
        return 'no_catalogue_hit'
    if row.get('agreed'):
        return 'wrong_agreement' if not row.get('correct') else 'agree'
    vector, text = cards_by_id.get(row['vector_id']), cards_by_id.get(row['text_id'])
    if vector and text and vector['language'] != text['language'] and number_ok(row['text_number'], vector) and name_ok(row['text_name'], vector):
        return 'same_artwork_twin'
    if row.get('vector_right') and not row.get('text_right'):
        return 'number_misread' if row.get('number_right') is False else 'text_misread'
    if row.get('text_right') and not row.get('vector_right'):
        return 'vector_wrong'
    if row.get('number_right') is False:
        return 'number_misread'
    if row.get('name_right') is False:
        return 'text_misread'
    return 'disagree'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--panel', type=Path, required=True)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--replay', type=Path)
    parser.add_argument('--log', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.panel.read_text().splitlines()]
    ids = np.load(args.index / 'embedding_card_ids.npy', allow_pickle=False).astype(str)
    index = np.asarray(np.load(args.index / 'embeddings.npy', mmap_mode='r'), dtype=np.float32)
    index = index / np.clip(np.linalg.norm(index, axis=1, keepdims=True), 1e-8, None)
    cards = load_cards(args.catalog)
    by_key: dict[str, list[dict]] = {}
    for card in cards:
        for key in card['keys']:
            by_key.setdefault(key, []).append(card)
    by_id = {}
    for card in cards:
        by_id[card['id']] = card
        if card['id'].startswith('en:'):
            by_id.setdefault(card['id'].split(':', 1)[1], card)
    replay = {}
    if args.replay and args.replay.is_file():
        replay = {row['id']: row for row in map(json.loads, args.replay.read_text().splitlines())}
    started = time.perf_counter()
    evaluated = []
    for row in rows:
        body, quality = text_fields(row)
        slab = row.get('quad_role') == 'slab' or row.get('kind') == 'slab'
        label_name, label_number = body.get('label_name'), body.get('label_number')
        label_language = body.get('label_language')
        card_name, card_number = body.get('name'), body.get('number')
        if slab and label_name and label_number:
            text_name, text_number, text_language = label_name, label_number, label_language
            name_conf = body.get('label_name_conf') or 0
            number_conf = body.get('label_number_conf') or 0
            text_source = 'label'
        else:
            text_name, text_number, text_language = card_name, card_number, None
            name_conf = body.get('name_conf') or 0
            number_conf = body.get('number_conf') or 0
            text_source = 'card'
        hits = lookup(by_key, text_name, text_number, text_language)
        # A slab label that names no language still has to be one card.
        if slab and text_source == 'label' and label_language is None and len(hits) != 1:
            narrowed = [card for card in hits if card['language'] == 'en']
            hits = narrowed if len(narrowed) == 1 else hits
        vector = decode_vector(row.get('client_embedding'))
        vector_id = second = margin = None
        if vector is not None:
            vector_id, top_score, second, second_score = search_top(index, ids, vector)
            margin = top_score - second_score
        truth = row.get('manual_truth') or {}
        expected = row.get('expected') or []
        expected_cards = [by_id[item] for item in expected if item in by_id]
        name_right = None if not text_name or not truth.get('name') else name_match(text_name, truth['name']) or any(
            name_ok(text_name, card) for card in expected_cards)
        number_right = None if not text_number else any(number_ok(text_number, card) for card in expected_cards) or (
            bool(truth.get('number')) and number_match([text_number], truth['number']) is True)
        if len(hits) == 1:
            text_status, text_id = 'unique', hits[0]['id']
        elif len(hits) > 1:
            text_status, text_id = 'ambiguous', None
        else:
            text_status, text_id = 'none', None
        agreed = bool(vector_id and text_id and same_card(vector_id, text_id) and margin is not None and margin > 0)
        correct = agreed and matches_expected(vector_id, expected)
        pipeline = replay.get(row['id']) or {}
        item = {
            'id': row['id'], 'group': group_of(row), 'quad_role': row.get('quad_role'),
            'expected': expected, 'vector_id': vector_id, 'second_id': second, 'margin': margin,
            'text_source': text_source, 'text_name': text_name, 'text_number': text_number,
            'text_language': text_language, 'text_status': text_status, 'text_id': text_id,
            'name_conf': name_conf, 'number_conf': number_conf,
            'sharpness': quality.get('sharpness'), 'glare': quality.get('glare'),
            'card_fraction': quality.get('card_fraction'),
            'name_right': name_right, 'number_right': number_right,
            'vector_right': matches_expected(vector_id, expected),
            'text_right': matches_expected(text_id, expected),
            'agreed': agreed, 'correct': correct,
            'pipeline_status': pipeline.get('status'), 'pipeline_card': pipeline.get('card_id'),
            'pipeline_correct': matches_expected(pipeline.get('card_id'), expected),
            'pipeline_cpu_ms': pipeline.get('cpu_ms'),
        }
        item['reason'] = reason_for(item, by_id)
        evaluated.append(item)
    search_ms = (time.perf_counter() - started) * 1000 / max(1, len(evaluated))

    def keep(item, margin, name_conf, number_conf, sharpness, glare, skip_slabs):
        if not item['agreed']:
            return False
        if skip_slabs and item['quad_role'] == 'slab':
            return False
        if item['margin'] is None or item['margin'] < margin:
            return False
        if (item['name_conf'] or 0) < name_conf or (item['number_conf'] or 0) < number_conf:
            return False
        if sharpness and (item['sharpness'] is None or item['sharpness'] < sharpness):
            return False
        if glare < 1 and (item['glare'] is None or item['glare'] > glare):
            return False
        return True

    best = None
    for skip_slabs in (False, True):
        for margin in (0.0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.2):
            for name_conf in (0.0, 0.5, 0.9):
                for number_conf in (0.0, 0.5, 0.9):
                    for sharpness in (0, 30, 80):
                        for glare in (1.0, 0.05, 0.02):
                            chosen = [item for item in evaluated
                                      if keep(item, margin, name_conf, number_conf, sharpness, glare, skip_slabs)]
                            wrong = [item for item in chosen if not item['correct']]
                            if wrong:
                                continue
                            score = (len(chosen), -int(skip_slabs), -margin, -name_conf, -number_conf, -sharpness, glare)
                            gate = {
                                'margin': margin, 'name_conf': name_conf, 'number_conf': number_conf,
                                'min_sharpness': sharpness, 'max_glare': glare, 'skip_slabs': skip_slabs,
                                'kept': len(chosen), 'wrong': 0,
                                'ids': [item['id'] for item in chosen],
                            }
                            if best is None or score > best[0]:
                                best = (score, gate)
    answered = [item for item in evaluated if item['agreed']]
    wrongs = [item for item in answered if not item['correct']]
    sharpness_values = sorted(item['sharpness'] for item in evaluated if item['sharpness'] is not None)
    def tercile(value):
        if value is None or not sharpness_values:
            return 'unknown'
        low, high = sharpness_values[len(sharpness_values) // 3], sharpness_values[2 * len(sharpness_values) // 3]
        if value < low:
            return 'soft'
        if value < high:
            return 'middle'
        return 'sharp'

    def pack(subset):
        return {
            'photos': len(subset),
            'answered': sum(item['agreed'] for item in subset),
            'correct': sum(item['correct'] for item in subset),
            'wrong': sum(item['agreed'] and not item['correct'] for item in subset),
        }

    groups = {}
    for name in ('raw', 'slab', 'phone', 'screenshot'):
        groups[name] = pack([item for item in evaluated if item['group'] == name])
    buckets = {}
    for name in ('soft', 'middle', 'sharp'):
        buckets[name] = pack([item for item in evaluated if tercile(item['sharpness']) == name])
    pipeline_cpu = [item['pipeline_cpu_ms'] for item in evaluated if item.get('pipeline_cpu_ms')]
    log_counts = Counter()
    if args.log and args.log.is_file():
        for line in args.log.read_text(errors='replace').splitlines():
            if ' stage0 ' in f' {line}' or line.startswith('INFO') and 'stage0 ' in line:
                if 'stage0 ' not in line:
                    continue
                log_counts['lines'] += 1
                for token in line.split():
                    if token.startswith('embedding='):
                        log_counts[token] += 1
                    elif token.startswith('quality='):
                        log_counts[token] += 1
                    elif token.startswith('text='):
                        log_counts[token] += 1
                    elif token.startswith('label='):
                        log_counts[token] += 1
                    elif token.startswith('would='):
                        log_counts[token] += 1
    summary = {
        'photos': len(evaluated),
        'answered': len(answered),
        'correct': sum(item['correct'] for item in answered),
        'wrong': len(wrongs),
        'wrongs': [{key: item[key] for key in ('id', 'group', 'vector_id', 'text_id', 'expected', 'margin', 'text_name', 'text_number')}
                   for item in wrongs],
        'reasons': dict(Counter(item['reason'] for item in evaluated if item['reason'] != 'agree')),
        'groups': groups,
        'sharpness_buckets': buckets,
        'sharpness_cuts': [sharpness_values[len(sharpness_values) // 3], sharpness_values[2 * len(sharpness_values) // 3]] if sharpness_values else [],
        'gate': None if best is None else {key: value for key, value in best[1].items() if key != 'ids'},
        'gate_ids': [] if best is None else best[1]['ids'],
        'stage1_cpu_ms_mean': round(search_ms, 2),
        'pipeline_cpu_ms_mean': round(float(np.mean(pipeline_cpu)), 1) if pipeline_cpu else None,
        'pipeline_cpu_ms_p50': round(float(np.median(pipeline_cpu)), 1) if pipeline_cpu else None,
        'pipeline_correct': sum(item['pipeline_correct'] for item in evaluated),
        'stage0_log': dict(log_counts),
        'photos_detail': evaluated,
    }
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({key: summary[key] for key in summary if key not in {'photos_detail', 'gate_ids'}}, indent=2))


if __name__ == '__main__':
    main()
