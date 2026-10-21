"""Estimate a cheap stage-1 answer from simulated phone fields.

Stage 1 answers only when the phone vector's top card, the printed number and the
name are the same card, with a visual margin. Slabs use the label's name, number
and language. The search is brute-force cosine over the exported index.

Round 2, on by default:
- Fix A collapses a legacy id and its `en:` duplicate into one catalogue card.
- Fix B treats two languages of the same artwork as agreement when their
  reference vectors have cosine at least 0.84. That cut is the gap on this
  panel: same-artwork pairs sit at 0.85 and above, and the next different
  card in another language is 0.77. The text's card wins. A twin whose number
  repeats the text's number with a different set total is not accepted.

    python api/scripts/estimate_stage1.py --panel data/latency/stage0-simulation-20261021/stage0.jsonl \\
        --index data/latency/stage0-simulation-20261021/kit/vectors/pad \\
        --catalog data/latency/stage0-simulation-20261021/kit/catalog.sqlite \\
        --replay data/latency/stage0-simulation-20261021/replay.jsonl \\
        --log data/latency/stage0-simulation-20261021/server.log \\
        --out data/latency/stage0-simulation-20261021/stage1.json \\
        --duplicates-out docs/experiments/stage0-duplicate-pairs-20261021.csv
"""
from __future__ import annotations

import argparse
import base64
import csv
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
from app.recognition.rank import name_match, number_match, parse_collector  # noqa: E402


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
            'SELECT id, name, view_title, collector_number, printed_collector_number, language, set_id, set_name '
            'FROM cards'):
        item = dict(row)
        item['keys'] = {key for key in (number_key(item['collector_number']), number_key(item['printed_collector_number'])) if key}
        rows.append(item)
    return rows


def duplicate_pairs(cards: list[dict]) -> list[tuple[dict, dict]]:
    """Legacy id and `en:` id that are the same English card."""
    by_id = {card['id']: card for card in cards}
    pairs = []
    for card in cards:
        if not card['id'].startswith('en:'):
            continue
        bare = by_id.get(card['id'].split(':', 1)[1])
        if bare is None:
            continue
        if (card['name'], card['set_id'], card['collector_number'], card['printed_collector_number'], card['language']) != (
                bare['name'], bare['set_id'], bare['collector_number'], bare['printed_collector_number'], bare['language']):
            continue
        pairs.append((bare, card))
    return pairs


def collapse_hits(hits: list[dict], bare_ids: set[str]) -> list[dict]:
    """Keep the `en:` row when a candidate list contains both copies."""
    present = {card['id'] for card in hits}
    drop = {card['id'] for card in hits if card['id'] in bare_ids and f'en:{card["id"]}' in present}
    return [card for card in hits if card['id'] not in drop]


def prefer_en(card_id: str | None, bare_ids: set[str]) -> str | None:
    if card_id and card_id in bare_ids:
        return f'en:{card_id}'
    return card_id


def set_total_conflicts(text_number: str | None, card: dict) -> bool:
    """Same printed number, different set size. A different number is a language renumber."""
    text = parse_collector(text_number)
    if text is None or not text.denominator:
        return False
    for ident in (card.get('collector_number'), card.get('printed_collector_number')):
        parts = parse_collector(ident)
        if parts is None or not parts.denominator:
            continue
        if parts.prefix == text.prefix and parts.number == text.number and parts.denominator != text.denominator:
            return True
    return False


def ambiguity_kind(hits: list[dict]) -> str:
    names = {(card['name'], card['collector_number']) for card in hits}
    sets = {card['set_id'] for card in hits}
    languages = {card['language'] for card in hits}
    if len(names) == 1 and len(sets) > 1:
        return 'different_sets'
    if len(sets) == 1 and len(languages) == 1:
        return 'same_set'
    if len(languages) > 1 and len(names) == 1:
        return 'language_prints'
    if len({card['collector_number'] for card in hits}) == 1 and len(names) > 1:
        return 'same_number_different_names'
    return 'mixed'


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


def search_top(scores: np.ndarray, ids: np.ndarray) -> tuple[str, float, str, float]:
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


def same_mask(ids: np.ndarray, card_id: str) -> np.ndarray:
    bare = card_id.split(':', 1)[1] if card_id.startswith('en:') else card_id
    return (ids == card_id) | (ids == bare) | (ids == f'en:{bare}')


def pair_margin(scores: np.ndarray, ids: np.ndarray, top_id: str, text_id: str, top_score: float) -> tuple[float, str]:
    """Gap from the twin pair to the next card that is neither copy."""
    rest = np.where(same_mask(ids, top_id) | same_mask(ids, text_id), -2.0, scores)
    slot = int(np.argmax(rest))
    return top_score - float(rest[slot]), str(ids[slot])


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
    if row.get('twin_block') == 'set_total':
        return 'set_total_conflict'
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


def evaluate(rows, scores, ids, index, position, by_key, by_id, exact, replay, bare_ids, *, collapse, twins, twin_cosine):
    evaluated = []
    for slot, row in enumerate(rows):
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
        if collapse:
            hits = collapse_hits(hits, bare_ids)
        # A slab label that names no language still has to be one card.
        if slab and text_source == 'label' and label_language is None and len(hits) != 1:
            narrowed = [card for card in hits if card['language'] == 'en']
            hits = narrowed if len(narrowed) == 1 else hits
        photo_scores = scores[:, slot]
        vector_id = second = margin = top_score = None
        if row.get('_has_vector'):
            vector_id, top_score, second, second_score = search_top(photo_scores, ids)
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
        ref_cosine = None
        if vector_id and text_id and vector_id in position and text_id in position:
            ref_cosine = float(index[position[vector_id]] @ index[position[text_id]])
        twin_block = None
        via = None
        if twins and vector_id and text_id and not same_card(vector_id, text_id) and ref_cosine is not None and ref_cosine >= twin_cosine:
            vector_card, text_card = exact.get(vector_id), exact.get(text_id)
            languages_differ = bool(vector_card and text_card and (vector_card.get('language') or '') != (text_card.get('language') or ''))
            if languages_differ and set_total_conflicts(text_number, vector_card):
                twin_block = 'set_total'
            elif languages_differ and top_score is not None:
                margin, second = pair_margin(photo_scores, ids, vector_id, text_id, top_score)
                via = 'twin'
        same = bool(vector_id and text_id and same_card(vector_id, text_id) and margin is not None and margin > 0)
        twin_ok = via == 'twin' and margin is not None and margin > 0
        if same:
            via = 'same'
        agreed = same or twin_ok
        if twin_ok:
            answer_id = text_id
        elif same:
            answer_id = prefer_en(text_id, bare_ids) if collapse else text_id
        else:
            answer_id = None
        correct = bool(answer_id) and matches_expected(answer_id, expected)
        pipeline = replay.get(row['id']) or {}
        item = {
            'id': row['id'], 'group': group_of(row), 'quad_role': row.get('quad_role'),
            'expected': expected, 'vector_id': vector_id, 'second_id': second, 'margin': margin,
            'answer_id': answer_id, 'via': via if agreed else None,
            'ref_cosine': ref_cosine, 'twin_block': twin_block,
            'text_source': text_source, 'text_name': text_name, 'text_number': text_number,
            'text_language': text_language, 'text_status': text_status, 'text_id': text_id,
            'name_conf': name_conf, 'number_conf': number_conf,
            'sharpness': quality.get('sharpness'), 'glare': quality.get('glare'),
            'card_fraction': quality.get('card_fraction'),
            'truth_name': truth.get('name'), 'truth_number': truth.get('number'),
            'name_right': name_right, 'number_right': number_right,
            'vector_right': matches_expected(vector_id, expected),
            'text_right': matches_expected(text_id, expected),
            'agreed': agreed, 'correct': correct,
            'pipeline_status': pipeline.get('status'), 'pipeline_card': pipeline.get('card_id'),
            'pipeline_correct': matches_expected(pipeline.get('card_id'), expected),
            'pipeline_cpu_ms': pipeline.get('cpu_ms'),
        }
        if text_status == 'ambiguous':
            item['ambiguity'] = ambiguity_kind(hits)
            item['candidates'] = [
                {'id': card['id'], 'name': card['name'], 'set_id': card['set_id'],
                 'number': card['collector_number'], 'language': card['language']}
                for card in hits]
        item['reason'] = reason_for(item, by_id)
        evaluated.append(item)
    return evaluated


def answer_brief(item: dict) -> dict:
    return {
        'id': item['id'], 'group': item['group'], 'card': item.get('answer_id'),
        'vector_id': item['vector_id'], 'text_id': item['text_id'],
        'margin': None if item['margin'] is None else round(float(item['margin']), 4),
        'ref_cosine': None if item.get('ref_cosine') is None else round(float(item['ref_cosine']), 4),
        'via': item.get('via'), 'correct': item['correct'],
        'expected': item['expected'], 'text_name': item['text_name'], 'text_number': item['text_number'],
    }


def at_margin(evaluated: list[dict], minimum: float) -> dict:
    chosen = [item for item in evaluated if item['agreed'] and item['margin'] is not None and item['margin'] >= minimum]

    def pack(name: str) -> dict:
        subset = [item for item in evaluated if item['group'] == name]
        picked = [item for item in chosen if item['group'] == name]
        return {
            'photos': len(subset),
            'answered': len(picked),
            'correct': sum(item['correct'] for item in picked),
            'wrong': sum(not item['correct'] for item in picked),
        }

    return {
        'answered': len(chosen),
        'correct': sum(item['correct'] for item in chosen),
        'wrong': sum(not item['correct'] for item in chosen),
        'share': round(len(chosen) / max(1, len(evaluated)), 4),
        'groups': {name: pack(name) for name in ('raw', 'slab', 'phone', 'screenshot')},
        'answers': [answer_brief(item) for item in chosen],
    }


def reading_row(item: dict) -> dict:
    return {
        'id': item['id'], 'group': item['group'], 'reason': item['reason'],
        'read_name': item['text_name'], 'read_number': item['text_number'],
        'truth_name': item.get('truth_name'), 'truth_number': item.get('truth_number'),
        'text_source': item['text_source'], 'expected': item['expected'],
        'vector_id': item['vector_id'], 'text_id': item['text_id'],
    }


def write_duplicate_csv(path: Path, catalog: Path, index_ids: set[str]) -> dict:
    db = sqlite3.connect(catalog)
    db.row_factory = sqlite3.Row
    cards = [dict(row) for row in db.execute(
        'SELECT id, name, set_id, set_name, collector_number, printed_collector_number, language, '
        'image_path, cardmarket_id, cardmarket_url FROM cards')]
    pairs = duplicate_pairs(cards)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        'bare_id', 'en_id', 'name', 'set_id', 'set_name', 'collector_number', 'printed_collector_number', 'language',
        'bare_image_path', 'en_image_path', 'bare_in_index', 'en_in_index',
        'bare_cardmarket_id', 'en_cardmarket_id', 'bare_cardmarket_url', 'en_cardmarket_url',
    ]
    both = only_bare = only_en = neither = 0
    cardmarket_both = cardmarket_differ = cardmarket_bare_only = cardmarket_en_only = 0
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for bare, en in sorted(pairs, key=lambda item: item[1]['id']):
            bare_in, en_in = bare['id'] in index_ids, en['id'] in index_ids
            if bare_in and en_in:
                both += 1
            elif bare_in:
                only_bare += 1
            elif en_in:
                only_en += 1
            else:
                neither += 1
            bare_market, en_market = bare.get('cardmarket_id'), en.get('cardmarket_id')
            if bare_market and en_market:
                cardmarket_both += 1
                if str(bare_market) != str(en_market):
                    cardmarket_differ += 1
            elif bare_market:
                cardmarket_bare_only += 1
            elif en_market:
                cardmarket_en_only += 1
            writer.writerow({
                'bare_id': bare['id'], 'en_id': en['id'], 'name': en['name'], 'set_id': en['set_id'],
                'set_name': en['set_name'], 'collector_number': en['collector_number'],
                'printed_collector_number': en['printed_collector_number'], 'language': en['language'],
                'bare_image_path': bare.get('image_path'), 'en_image_path': en.get('image_path'),
                'bare_in_index': bare_in, 'en_in_index': en_in,
                'bare_cardmarket_id': bare_market, 'en_cardmarket_id': en_market,
                'bare_cardmarket_url': bare.get('cardmarket_url'), 'en_cardmarket_url': en.get('cardmarket_url'),
            })
    return {
        'pairs': len(pairs),
        'both_in_index': both,
        'only_bare_in_index': only_bare,
        'only_en_in_index': only_en,
        'neither_in_index': neither,
        'cardmarket_on_both': cardmarket_both,
        'cardmarket_ids_differ': cardmarket_differ,
        'cardmarket_bare_only': cardmarket_bare_only,
        'cardmarket_en_only': cardmarket_en_only,
        'csv': str(path),
    }


def stage0_log_counts(path: Path | None) -> dict:
    counts = Counter()
    if path is None or not path.is_file():
        return {}
    for line in path.read_text(errors='replace').splitlines():
        if 'stage0 ' not in line:
            continue
        counts['lines'] += 1
        for token in line.split():
            if token.startswith(('embedding=', 'quality=', 'text=', 'label=', 'would=')):
                counts[token] += 1
    return dict(counts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--panel', type=Path, required=True)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--replay', type=Path)
    parser.add_argument('--log', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--duplicates-out', type=Path)
    parser.add_argument('--twin-cosine', type=float, default=0.84)
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
    exact = {}
    for card in cards:
        exact[card['id']] = card
        by_id[card['id']] = card
        if card['id'].startswith('en:'):
            by_id.setdefault(card['id'].split(':', 1)[1], card)
    bare_ids = {bare['id'] for bare, _en in duplicate_pairs(cards)}
    position = {}
    for slot, card_id in enumerate(ids.tolist()):
        position.setdefault(str(card_id), slot)
    replay = {}
    if args.replay and args.replay.is_file():
        replay = {row['id']: row for row in map(json.loads, args.replay.read_text().splitlines())}
    vectors = np.zeros((len(rows), index.shape[1]), dtype=np.float32)
    for slot, row in enumerate(rows):
        vector = decode_vector(row.get('client_embedding'))
        row['_has_vector'] = vector is not None
        if vector is not None:
            vectors[slot] = vector
    started = time.perf_counter()
    scores = index @ vectors.T
    common = dict(scores=scores, ids=ids, index=index, position=position, by_key=by_key, by_id=by_id,
                  exact=exact, replay=replay, bare_ids=bare_ids, twin_cosine=args.twin_cosine)
    modes = {
        'round1': evaluate(rows, collapse=False, twins=False, **common),
        'A': evaluate(rows, collapse=True, twins=False, **common),
        'B': evaluate(rows, collapse=False, twins=True, **common),
        'AB': evaluate(rows, collapse=True, twins=True, **common),
    }
    search_ms = (time.perf_counter() - started) * 1000 / max(1, len(rows))
    comparison = {}
    for name, evaluated in modes.items():
        comparison[name] = {'margin_gt_0': at_margin(evaluated, 0.0), 'margin_ge_0.02': at_margin(evaluated, 0.02)}
    sweep = []
    for cosine in (0.75, 0.80, 0.84, 0.90, 0.95, 0.98):
        evaluated = modes['AB'] if cosine == args.twin_cosine else evaluate(
            rows, collapse=True, twins=True, twin_cosine=cosine, scores=scores, ids=ids, index=index,
            position=position, by_key=by_key, by_id=by_id, exact=exact, replay=replay, bare_ids=bare_ids)
        wide, gate = at_margin(evaluated, 0.0), at_margin(evaluated, 0.02)
        sweep.append({
            'cosine': cosine,
            'margin_gt_0': {key: wide[key] for key in ('answered', 'correct', 'wrong')},
            'margin_ge_0.02': {key: gate[key] for key in ('answered', 'correct', 'wrong')},
        })
    ab = modes['AB']
    round1_gate = {item['id'] for item in comparison['round1']['margin_ge_0.02']['answers']}
    round1_wide = {item['id'] for item in comparison['round1']['margin_gt_0']['answers']}
    gate_answers = comparison['AB']['margin_ge_0.02']['answers']
    wide_answers = comparison['AB']['margin_gt_0']['answers']
    pipeline_cpu = [item['pipeline_cpu_ms'] for item in ab if item.get('pipeline_cpu_ms')]
    summary = {
        'round': 2,
        'twin_cosine': args.twin_cosine,
        'photos': len(ab),
        'stage1_cpu_ms_mean': round(search_ms, 2),
        'pipeline_cpu_ms_mean': round(float(np.mean(pipeline_cpu)), 1) if pipeline_cpu else None,
        'pipeline_cpu_ms_p50': round(float(np.median(pipeline_cpu)), 1) if pipeline_cpu else None,
        'pipeline_correct': sum(item['pipeline_correct'] for item in ab),
        'comparison': comparison,
        'threshold_sweep': sweep,
        'new_at_gate': [item for item in gate_answers if item['id'] not in round1_gate],
        'new_at_any_margin': [item for item in wide_answers if item['id'] not in round1_wide],
        'wrongs_any_margin': [item for item in wide_answers if not item['correct']],
        'wrongs_at_gate': [item for item in gate_answers if not item['correct']],
        'reasons': dict(Counter(item['reason'] for item in ab if item['reason'] != 'agree')),
        'ambiguous': [
            {'id': item['id'], 'group': item['group'], 'kind': item.get('ambiguity'),
             'read_name': item['text_name'], 'read_number': item['text_number'], 'candidates': item.get('candidates')}
            for item in ab if item['reason'] == 'ambiguous_text'],
        'reading': [reading_row(item) for item in ab if item['reason'] in {'no_text', 'text_misread', 'number_misread'}],
        'vector_wrong': [reading_row(item) for item in ab if item['reason'] == 'vector_wrong'],
        'set_total_conflict': [reading_row(item) for item in ab if item['reason'] == 'set_total_conflict'],
        'stage0_log': stage0_log_counts(args.log),
        'photos_detail': ab,
    }
    if args.duplicates_out:
        summary['duplicates'] = write_duplicate_csv(args.duplicates_out, args.catalog, set(ids.tolist()))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    printable = {
        'photos': summary['photos'],
        'twin_cosine': summary['twin_cosine'],
        'stage1_cpu_ms_mean': summary['stage1_cpu_ms_mean'],
        'comparison': {
            name: {cut: {key: body[key] for key in ('answered', 'correct', 'wrong', 'share', 'groups')}
                   for cut, body in cuts.items()}
            for name, cuts in comparison.items()},
        'threshold_sweep': sweep,
        'new_at_gate': summary['new_at_gate'],
        'wrongs_any_margin': summary['wrongs_any_margin'],
        'wrongs_at_gate': summary['wrongs_at_gate'],
        'reasons': summary['reasons'],
        'ambiguous_kinds': dict(Counter(item['kind'] for item in summary['ambiguous'])),
        'duplicates': summary.get('duplicates'),
    }
    print(json.dumps(printable, indent=2))


if __name__ == '__main__':
    main()
