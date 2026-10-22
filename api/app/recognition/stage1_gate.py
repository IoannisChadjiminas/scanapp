"""Stage 1 and stage 1b, the rules measured in the stage 0 simulation.

Stage 1 answers when the phone's vector and its text name the same card, with
a margin of at least 0.02. Duplicate ids collapse. An English/Japanese twin
pair agrees and the text's card wins. Stage 1b, only after that abstains,
checks the artwork of the one card the text names, and refuses when another
card leads by 0.05 or more.

Neither function reads the network or the scan tables.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
import time

import numpy as np

from app.recognition.client_embedding import parse_client_embedding
from app.recognition.label_identity import number_key
from app.recognition.rank import name_match, number_match, parse_collector

TWIN_COSINE = 0.84
STAGE1_MARGIN = 0.02
CONTRADICTION = 0.05
MIN_INLIERS = 10


@dataclass(frozen=True)
class Decision:
    answered: bool
    stage: str | None
    card_id: str | None
    margin: float | None
    inliers: int | None
    reason: str
    ms: float


def _empty(reason: str, started: float, *, margin: float | None = None) -> Decision:
    return Decision(False, None, None, margin, None, reason, (time.perf_counter() - started) * 1000)


def same_card(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    bare = left.split(':', 1)[1] if left.startswith('en:') else left
    return right in {bare, f'en:{bare}', left}


def text_fields(raw: str | None) -> tuple[str | None, str | None, str | None, bool]:
    """Name, number, language, and whether the slab label supplied them."""
    if not raw:
        return None, None, None, False
    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError):
        return None, None, None, False
    if not isinstance(body, dict):
        return None, None, None, False
    label_name, label_number = body.get('label_name'), body.get('label_number')
    if isinstance(label_name, str) and isinstance(label_number, str) and label_name.strip() and label_number.strip():
        language = body.get('label_language')
        return label_name.strip(), label_number.strip(), language if isinstance(language, str) else None, True
    name = body.get('name') if isinstance(body.get('name'), str) else None
    number = body.get('number') if isinstance(body.get('number'), str) else None
    return name, number, None, False


def number_ok(phone: str | None, card: dict) -> bool:
    if not phone:
        return False
    identifiers = [card.get('collector_number'), card.get('printed_collector_number')]
    results = [number_match([phone], item) for item in identifiers if item]
    if any(result is True for result in results):
        return True
    if any(result is False for result in results):
        return False
    return number_key(phone) in set(card.get('keys') or ())


def name_ok(phone: str | None, card: dict) -> bool:
    if not phone:
        return False
    return name_match(phone, card.get('name') or '') or bool(
        card.get('view_title') and name_match(phone, card['view_title']))


def lookup(by_key: dict[str, list[dict]], name: str | None, number: str | None,
           language: str | None) -> list[dict]:
    if not name or not number:
        return []
    pool = by_key.get(number_key(number) or '', [])
    return [card for card in pool if number_ok(number, card) and name_ok(name, card)
            and (language is None or card.get('language') == language)]


def collapse_hits(hits: list[dict], bare_ids: set[str]) -> list[dict]:
    present = {card['id'] for card in hits}
    drop = {card['id'] for card in hits if card['id'] in bare_ids and f'en:{card["id"]}' in present}
    return [card for card in hits if card['id'] not in drop]


def set_total_conflicts(text_number: str | None, card: dict) -> bool:
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


def load_catalogue(conn: sqlite3.Connection) -> tuple[dict[str, list[dict]], dict[str, dict], set[str]]:
    cards = []
    for row in conn.execute(
            'SELECT id, name, view_title, collector_number, printed_collector_number, language, set_id, image_path '
            'FROM cards'):
        item = dict(row)
        item['keys'] = {key for key in (
            number_key(item['collector_number']), number_key(item['printed_collector_number'])) if key}
        cards.append(item)
    by_id = {card['id']: card for card in cards}
    bare_ids = set()
    for card in cards:
        if not card['id'].startswith('en:'):
            continue
        bare = by_id.get(card['id'].split(':', 1)[1])
        if bare is None:
            continue
        same = all(card.get(key) == bare.get(key) for key in (
            'name', 'set_id', 'collector_number', 'printed_collector_number', 'language'))
        if same:
            bare_ids.add(bare['id'])
    by_key: dict[str, list[dict]] = {}
    for card in cards:
        for key in card['keys']:
            by_key.setdefault(key, []).append(card)
    return by_key, by_id, bare_ids


def _top(scores: np.ndarray, ids: list[str]) -> tuple[str, float, float]:
    order = np.argpartition(-scores, min(6, len(scores) - 1))[:6]
    order = order[np.argsort(-scores[order])]
    top = ids[int(order[0])]
    top_score = float(scores[int(order[0])])
    second = top_score
    for slot in order[1:]:
        if not same_card(ids[int(slot)], top):
            second = float(scores[int(slot)])
            break
    return top, top_score, top_score - second


def _pair_margin(scores: np.ndarray, ids: list[str], top_id: str, text_id: str, top_score: float) -> float:
    rest = np.array([-2.0 if same_card(card_id, top_id) or same_card(card_id, text_id) else score
                     for card_id, score in zip(ids, scores)], dtype=np.float32)
    return top_score - float(rest.max())


def one_card(hits: list[dict], language: str | None, embeddings: np.ndarray,
             position: dict[str, int]) -> dict | None:
    if len(hits) == 1:
        return hits[0]
    if len(hits) < 2 or not language:
        return None
    for left in range(len(hits)):
        for right in range(left + 1, len(hits)):
            a, b = hits[left], hits[right]
            if (a.get('language') or '') == (b.get('language') or ''):
                return None
            if a['id'] not in position or b['id'] not in position:
                return None
            if float(embeddings[position[a['id']]] @ embeddings[position[b['id']]]) < TWIN_COSINE:
                return None
    chosen = [card for card in hits if card.get('language') == language]
    return chosen[0] if len(chosen) == 1 else None


def contradicts(scores: np.ndarray, ids: list[str], embeddings: np.ndarray, position: dict[str, int],
                by_id: dict[str, dict], top_id: str, top_score: float, text_id: str) -> bool:
    if text_id not in position or same_card(top_id, text_id):
        return False
    gap = top_score - float(scores[position[text_id]])
    if top_id in position:
        cosine = float(embeddings[position[top_id]] @ embeddings[position[text_id]])
        languages = {(by_id.get(top_id) or {}).get('language'), (by_id.get(text_id) or {}).get('language')}
        if cosine >= TWIN_COSINE and None not in languages and len(languages) == 2:
            return False
    return gap >= CONTRADICTION


def decide(vector: np.ndarray, embeddings: np.ndarray, card_ids: list[str], *,
           by_key: dict[str, list[dict]], by_id: dict[str, dict], bare_ids: set[str],
           name: str | None, number: str | None, language: str | None,
           quad_ok: bool, stage1b: bool = False, label: bool = False) -> Decision:
    """The stage 1 gate, and stage 1b's text and contradiction rules.

    The artwork check is separate: a stage of ``1b`` here means the text named
    one card and nothing strongly contradicts it. The caller still has to verify.
    """
    started = time.perf_counter()
    if vector is None or embeddings is None or len(card_ids) == 0:
        return _empty('no_embedding', started)
    if not quad_ok:
        return _empty('no_quad', started)
    hits = collapse_hits(lookup(by_key, name, number, language), bare_ids)
    # A slab label with no language still counts as one card when only the English row matches.
    # Stage 1b looks the label up again without that narrowing, as the simulation did.
    stage1_hits = hits
    if label and language is None and len(hits) != 1:
        english = [card for card in hits if card.get('language') == 'en']
        if len(english) == 1:
            stage1_hits = english
    text_id = stage1_hits[0]['id'] if len(stage1_hits) == 1 else None
    scores = embeddings @ vector
    top_id, top_score, margin = _top(scores, card_ids)
    position: dict[str, int] = {}
    for index, card_id in enumerate(card_ids):
        position.setdefault(card_id, index)
    if text_id and text_id in position and top_id in position and not same_card(top_id, text_id):
        cosine = float(embeddings[position[top_id]] @ embeddings[position[text_id]])
        vector_card, text_card = by_id.get(top_id), by_id.get(text_id)
        languages_differ = bool(vector_card and text_card and (vector_card.get('language') or '') != (text_card.get('language') or ''))
        if cosine >= TWIN_COSINE and languages_differ and not set_total_conflicts(number, vector_card or {}):
            margin = _pair_margin(scores, card_ids, top_id, text_id, top_score)
            if margin >= STAGE1_MARGIN:
                return Decision(True, '1', text_id, margin, None, 'twin', (time.perf_counter() - started) * 1000)
            low_margin = margin
        else:
            low_margin = None
    elif text_id and same_card(top_id, text_id):
        if margin >= STAGE1_MARGIN:
            answer = text_id if text_id not in bare_ids else f'en:{text_id}'
            if answer not in by_id:
                answer = text_id
            return Decision(True, '1', answer, margin, None, 'same', (time.perf_counter() - started) * 1000)
        low_margin = margin
    else:
        low_margin = None
    if not stage1b:
        if low_margin is not None:
            return _empty('low_margin', started, margin=low_margin)
        if text_id is None:
            return _empty('no_unique_text' if not hits else 'ambiguous_text', started, margin=margin)
        return _empty('vector_disagree', started, margin=margin)
    card = one_card(hits, language, embeddings, position)
    if card is None:
        return _empty('no_unique_text' if not hits else 'ambiguous_text', started, margin=margin)
    if contradicts(scores, card_ids, embeddings, position, by_id, top_id, top_score, card['id']):
        return _empty('visual_contradiction', started, margin=margin)
    return Decision(False, '1b_pending', card['id'], margin, None, 'needs_artwork',
                    (time.perf_counter() - started) * 1000)
