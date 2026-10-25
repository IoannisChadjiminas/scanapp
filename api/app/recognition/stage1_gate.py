"""Stage 1 and stage 1b, the rules measured in the stage 0 simulation.

Stage 1 answers when the phone's vector and its text name the same card, with
a margin of at least 0.02. Duplicate ids collapse. An English/Japanese twin
pair agrees and the text's card wins. Stage 1b, only after that abstains,
checks the artwork of the one card the text names, and refuses when another
card leads by 0.05 or more.

Neither function reads the network or the scan tables.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
import re
import sqlite3
import time

import numpy as np

from app.recognition.client_embedding import parse_client_embedding
from app.recognition.client_text import number_candidates
from app.recognition.label_identity import number_key
from app.recognition.stage1_text_repair import card_totals, fuzzy_name_ok, number_variants
from app.recognition.rank import name_match, number_match, number_matches_identifiers, parse_collector, normalize_text

TWIN_COSINE = 0.84
STAGE1_MARGIN = 0.02
CONTRADICTION = 0.05
MIN_INLIERS = 10
REPRINT_COSINE = 0.95


@dataclass(frozen=True)
class GateOptions:
    set_totals: bool = False
    normalize_duplicates: bool = False
    printing_groups: bool = False
    promo_numbers: bool = False
    diagnostics: bool = False
    number_repair: bool = False
    fuzzy_name: bool = False
    twin_guard: bool = False

    @classmethod
    def from_settings(cls, settings):
        return cls(**{key: bool(getattr(settings, 'stage1_' + key, False))
                      for key in cls.__dataclass_fields__})


@dataclass(frozen=True)
class Decision:
    answered: bool
    stage: str | None
    card_id: str | None
    margin: float | None
    inliers: int | None
    reason: str
    ms: float
    printing_ids: tuple[str, ...] = ()
    vector_top: str | None = None
    vector_top_score: float | None = None
    text_candidates: tuple[str, ...] = ()
    text_candidate_count: int = 0
    contradicting_card: str | None = None
    contradiction_gap: float | None = None
    # The raw phone read that was repaired into the number the gate used (logged, never trusted).
    number_candidate: str | None = None


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


_CLEAN_NUMBER = re.compile(r'^[A-Z]{0,5}\d{1,4}[A-Z]?(?:/[A-Z]{0,4}\d{1,4})?$')
_USABLE_NUMBER = re.compile(r'^(?:[A-Z0-9]{0,5}\d{1,4}[A-Z]?/[A-Z]{0,4}\d{1,4}|[A-Z]{2,5}\d{1,4})$')


def text_number_candidates(raw: str | None) -> tuple[str, ...]:
    """The phone's raw number reads, only when it sent no valid number of its own."""
    if not raw:
        return ()
    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError):
        return ()
    if not isinstance(body, dict) or body.get('number'):
        return ()
    return number_candidates(body.get('number_candidates'))


def _total_agrees(spelling: str, card: dict) -> bool:
    """A repaired number with a set total must match a total the catalogue holds for that card.

    The ordinary lookup lets a bare catalogue number fit any denominator, which is fine for the
    phone's own validated number but too loose for a repaired guess: 205/777 must not pass.
    A prefixed code with no total (TG05, SWSH020) has nothing to compare.
    """
    parts = parse_collector(spelling)
    if parts is None or not parts.denominator:
        return True
    totals = {total.lstrip('0') or '0' for total in card_totals(card)}
    return (parts.denominator.lstrip('0') or '0') in totals


def resolve_number(name: str | None, number: str | None, candidates: tuple[str, ...],
                   language: str | None, by_key: dict[str, list[dict]],
                   options: 'GateOptions') -> tuple[str | None, str | None]:
    """(number, candidate used). A valid ``number`` always wins and is never replaced.

    A raw candidate is used only when, after the catalogue-constrained repair, it is a
    number the catalogue holds (with its set total, or a prefixed promo/gallery code) for
    a card whose name also agrees with the phone's name. It cannot pick a card by itself:
    the gate still needs the vector, or stage 1b the artwork, to agree afterwards.
    """
    if number or not name or not candidates or not options.number_repair:
        return number, None
    for candidate in candidates:
        compact = re.sub(r'\s+', '', candidate.upper())
        spellings = ([compact] if _CLEAN_NUMBER.fullmatch(compact) else []) + number_variants(candidate, by_key)
        for spelling in spellings:
            if not _USABLE_NUMBER.fullmatch(spelling):
                continue
            hits = _strict_lookup(by_key, name, spelling, language, options)
            if any(_total_agrees(spelling, card) for card in hits):
                return spelling, candidate
    return number, None


def number_ok(phone: str | None, card: dict, options: GateOptions = GateOptions()) -> bool:
    if not phone:
        return False
    identifiers = [card.get('collector_number'), card.get('printed_collector_number')]
    if options.promo_numbers and '/' not in phone and number_key(phone) in card.get('promo_keys', ()):
        return True
    if options.set_totals:
        # A bare alias must never overrule a known, different denominator.
        printed = parse_collector(card.get('printed_collector_number'))
        structured = ([card['printed_collector_number']] if printed and printed.denominator else
                      [value for value in identifiers if (parts := parse_collector(value)) and parts.denominator])
        total = card.get('set_total')
        if not structured and type(total) is int and total > 0:
            structured = [f'{value}/{total}' for value in identifiers
                          if (parts := parse_collector(value)) and not parts.prefix and not parts.denominator]
        result = number_matches_identifiers([phone], structured or [v for v in identifiers if v])
        if result is not None:
            return result
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


def _strict_lookup(by_key: dict[str, list[dict]], name: str, number: str,
                   language: str | None, options: GateOptions) -> list[dict]:
    pool = by_key.get(number_key(number) or '', [])
    # Existing bare slab numbers still work. Only additional promo-code aliases
    # are promo-scoped; dropping base hits here could auto-select a Prize Pack.
    return [card for card in pool if number_ok(number, card, options) and name_ok(name, card)
            and (language is None or card.get('language') == language)]


def lookup(by_key: dict[str, list[dict]], name: str | None, number: str | None,
           language: str | None, options: GateOptions = GateOptions()) -> list[dict]:
    if not name or not number:
        return []
    hits = _strict_lookup(by_key, name, number, language, options)
    if hits:
        return hits
    # Both repairs run only after the exact text found nothing, so they cannot
    # change an answer the gate already gave. Neither can select a card by itself:
    # the repaired number still has to be one the catalogue holds for a card whose
    # name also agrees, and the vector or artwork must still agree after that.
    variants = number_variants(number, by_key) if options.number_repair else []
    seen: dict[str, dict] = {}
    for variant in variants:
        for card in _strict_lookup(by_key, name, variant, language, options):
            seen.setdefault(card['id'], card)
    if seen:
        return list(seen.values())
    if options.fuzzy_name:
        # Only on a number with its set total, which has already narrowed the candidates.
        for candidate in (number, *variants):
            if '/' not in candidate:
                continue
            for card in by_key.get(number_key(candidate) or '', []):
                if (number_ok(candidate, card, options) and (language is None or card.get('language') == language)
                        and (fuzzy_name_ok(name, card.get('name')) or fuzzy_name_ok(name, card.get('view_title')))):
                    seen.setdefault(card['id'], card)
    return list(seen.values())


def is_promo(card: dict) -> bool:
    set_id = str(card.get('set_id') or '').split(':')[-1].casefold()
    title = str(card.get('set_name') or '').casefold()
    return (set_id in {'mep', 'svp', 'swshp', 'smp', 'smpromos', 'bwp', 'np', 'dp', 'dpp', 'hgssp', 'xy', 'xyp', 'wp'}
            or bool(re.fullmatch(r'pps\d+', set_id)) or 'promo' in title or 'prize pack' in title)


def _promo_keys(card: dict) -> set[str]:
    keys = set(card['keys'])
    if not is_promo(card):
        return set()
    prefix = {'svp': 'SVP', 'swshp': 'SWSH', 'smp': 'SM', 'smpromos': 'SM',
              'bwp': 'BW', 'dpp': 'DP', 'hgssp': 'HGSS', 'xyp': 'XY', 'mep': 'MEP'}.get(
                  str(card.get('set_id') or '').split(':')[-1].casefold())
    if prefix:
        keys.update(prefix + key for key in card['keys'] if key.isdigit())
    return keys


def duplicate_identity(card: dict) -> tuple:
    return (normalize_text(str(card.get('name') or '')),
            str(card.get('set_id') or '').split(':')[-1].strip().casefold(),
            number_key(card.get('collector_number')),
            str(card.get('language') or '').strip().casefold())


def collapse_hits(hits: list[dict], bare_ids: set[str]) -> list[dict]:
    present = {card['id'] for card in hits}
    drop = {card['id'] for card in hits if card['id'] in bare_ids and f'en:{card["id"]}' in present}
    return [card for card in hits if card['id'] not in drop]


def set_total_conflicts(text_number: str | None, card: dict, options: GateOptions = GateOptions()) -> bool:
    text = parse_collector(text_number)
    if text is None or not text.denominator:
        return False
    identifiers = [parse_collector(card.get(key)) for key in ('collector_number', 'printed_collector_number')]
    if (options.set_totals and type(card.get('set_total')) is int
            and not any(parts and parts.denominator for parts in identifiers)
            and any(parts and parts.prefix == text.prefix and parts.number == text.number for parts in identifiers)):
        return str(card['set_total']) != text.denominator
    for ident in (card.get('collector_number'), card.get('printed_collector_number')):
        parts = parse_collector(ident)
        if parts is None or not parts.denominator:
            continue
        if parts.prefix == text.prefix and parts.number == text.number and parts.denominator != text.denominator:
            return True
    return False


def load_catalogue(conn: sqlite3.Connection, options: GateOptions = GateOptions()) -> tuple[dict[str, list[dict]], dict[str, dict], set[str]]:
    cards = []
    totals = {}
    if options.set_totals:
        try:
            totals = {(str(row[0]).casefold(), str(row[1]).split(':')[-1].casefold()): int(row[2])
                      for row in conn.execute('SELECT language, set_id, official_total FROM set_totals')}
        except sqlite3.OperationalError:
            pass  # Small/older catalogues need not have the optional table.
    columns = {row[1] for row in conn.execute('PRAGMA table_info(cards)')}
    extras = ''.join(', ' + key for key in ('set_name', 'reprint_of', 'reprint_of_id') if key in columns)
    for row in conn.execute(
            'SELECT id, name, view_title, collector_number, printed_collector_number, language, set_id, image_path' + extras + ' '
            'FROM cards'):
        item = dict(row)
        item['keys'] = {key for key in (
            number_key(item['collector_number']), number_key(item['printed_collector_number'])) if key}
        if options.set_totals:
            item['set_total'] = totals.get((str(item.get('language') or 'en').casefold(),
                                           str(item.get('set_id') or '').split(':')[-1].casefold()))
        if options.promo_numbers:
            item['promo_keys'] = _promo_keys(item)
            item['keys'].update(item['promo_keys'])
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
        if same or (options.normalize_duplicates and duplicate_identity(card) == duplicate_identity(bare)
                    and all(duplicate_identity(card))):
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


def printing_group(hits: list[dict], embeddings: np.ndarray, position: dict[str, int]) -> tuple[dict | None, tuple[str, ...]]:
    """An identity plus explicit printing review; never select a promo/stamp.

    Every candidate must belong. A similar subset cannot hide an unrelated
    text candidate, and a chain of weak similarities cannot form a family.
    """
    if len(hits) < 2:
        return None, ()
    bases = [card for card in hits if not is_promo(card)
             and not (card.get('reprint_of') or card.get('reprint_of_id'))]
    if len(bases) != 1:
        return None, ()
    base = bases[0]
    for card in hits:
        if (normalize_text(card.get('name') or '') != normalize_text(base.get('name') or '')
                or card.get('language') != base.get('language')
                or number_key(card.get('collector_number')) != number_key(base.get('collector_number'))):
            return None, ()
        if card is base:
            continue
        explicit = card.get('reprint_of') or card.get('reprint_of_id')
        if explicit and same_card(str(explicit), base['id']):
            continue
        if card['id'] not in position or base['id'] not in position:
            return None, ()
        if float(embeddings[position[base['id']]] @ embeddings[position[card['id']]]) < REPRINT_COSINE:
            return None, ()
    return base, (base['id'], *sorted(card['id'] for card in hits if card is not base))


def printing_twins(hits: list[dict]) -> bool:
    """Two or more rows left after duplicate ids collapse, with one name, language and number.

    Those rows are printings of one card (a base set and its reprint, a promo and its base).
    """
    if len(hits) < 2:
        return False
    keys = {(normalize_text(str(card.get('name') or '')), card.get('language') or '',
             number_key(card.get('collector_number'))) for card in hits}
    return len(keys) == 1


def decide(vector: np.ndarray, embeddings: np.ndarray, card_ids: list[str], *,
           by_key: dict[str, list[dict]], by_id: dict[str, dict], bare_ids: set[str],
           name: str | None, number: str | None, language: str | None,
           quad_ok: bool, stage1b: bool = False, label: bool = False,
           options: GateOptions = GateOptions()) -> Decision:
    """The stage 1 gate, and stage 1b's text and contradiction rules.

    The artwork check is separate: a stage of ``1b`` here means the text named
    one card and nothing strongly contradicts it. The caller still has to verify.
    """
    started = time.perf_counter()
    if vector is None or embeddings is None or len(card_ids) == 0:
        return _empty('no_embedding', started)
    if not quad_ok:
        return _empty('no_quad', started)
    hits = collapse_hits(lookup(by_key, name, number, language, options), bare_ids)
    text_candidates = tuple(sorted(card['id'] for card in hits))
    scores = embeddings @ vector
    top_id, top_score, margin = _top(scores, card_ids)
    position: dict[str, int] = {}
    for index, card_id in enumerate(card_ids):
        position.setdefault(card_id, index)
    base, printing_ids = printing_group(hits, embeddings, position) if options.printing_groups else (None, ())
    twins = printing_twins(hits)
    if base is not None:
        hits = [base]

    def family(card_id: str) -> bool:
        return any(same_card(card_id, member) for member in printing_ids)

    if printing_ids and family(top_id):
        other = [float(score) for card_id, score in zip(card_ids, scores) if not family(card_id)]
        margin = top_score - max(other) if other else 0.0

    def finish(result: Decision, *, contradiction_gap: float | None = None) -> Decision:
        result = replace(result, printing_ids=printing_ids)
        if options.diagnostics:
            result = replace(result, vector_top=top_id, vector_top_score=top_score,
                             text_candidates=text_candidates[:5], text_candidate_count=len(text_candidates),
                             contradicting_card=top_id if contradiction_gap is not None else None,
                             contradiction_gap=contradiction_gap)
        return result

    if options.printing_groups and len(hits) == 1 and not printing_ids:
        only = hits[0]
        if (str(only.get('set_id') or '').split(':')[-1].upper().startswith('PPS')
                or 'prize pack' in str(only.get('set_name') or '').casefold()
                or only.get('reprint_of') or only.get('reprint_of_id')):
            return finish(_empty('printing_base_missing', started, margin=margin))
    # A slab label with no language still counts as one card when only the English row matches.
    # Stage 1b looks the label up again without that narrowing, as the simulation did.
    stage1_hits = hits
    if label and language is None and len(hits) != 1:
        english = [card for card in hits if card.get('language') == 'en']
        if len(english) == 1:
            stage1_hits = english
    text_id = stage1_hits[0]['id'] if len(stage1_hits) == 1 else None
    if (text_id and text_id in position and top_id in position
            and not same_card(top_id, text_id) and not (printing_ids and family(top_id))):
        cosine = float(embeddings[position[top_id]] @ embeddings[position[text_id]])
        vector_card, text_card = by_id.get(top_id), by_id.get(text_id)
        languages_differ = bool(vector_card and text_card and (vector_card.get('language') or '') != (text_card.get('language') or ''))
        if cosine >= TWIN_COSINE and languages_differ and not set_total_conflicts(number, vector_card or {}, options):
            margin = _pair_margin(scores, card_ids, top_id, text_id, top_score)
            if margin >= STAGE1_MARGIN:
                return finish(Decision(True, '1', text_id, margin, None, 'twin', (time.perf_counter() - started) * 1000))
            low_margin = margin
        else:
            low_margin = None
    elif text_id and (same_card(top_id, text_id) or (printing_ids and family(top_id))):
        if margin >= STAGE1_MARGIN:
            answer = text_id if text_id not in bare_ids else f'en:{text_id}'
            if answer not in by_id:
                answer = text_id
            return finish(Decision(True, '1', answer, margin, None, 'printing_group' if printing_ids else 'same', (time.perf_counter() - started) * 1000))
        low_margin = margin
    else:
        low_margin = None
    if not stage1b:
        if low_margin is not None:
            return finish(_empty('low_margin', started, margin=low_margin))
        if text_id is None:
            return finish(_empty('no_unique_text' if not hits else 'ambiguous_text', started, margin=margin))
        return finish(_empty('vector_disagree', started, margin=margin))
    if options.twin_guard and twins:
        # Stage 1 above answers a printing group only when the vector itself lands in that group.
        # Here the artwork alone would pick one printing; the background check disagreed on that pick.
        return finish(_empty('printing_twins', started, margin=margin))
    card = one_card(hits, language, embeddings, position)
    if card is None:
        return finish(_empty('no_unique_text' if not hits else 'ambiguous_text', started, margin=margin))
    if printing_ids:
        matched_scores = [float(score) for card_id, score in zip(card_ids, scores) if family(card_id)]
        gap = top_score - max(matched_scores) if matched_scores else None
        blocked = gap is not None and not family(top_id) and gap >= CONTRADICTION
    else:
        gap = top_score - float(scores[position[card['id']]]) if card['id'] in position else None
        blocked = contradicts(scores, card_ids, embeddings, position, by_id, top_id, top_score, card['id'])
    if blocked:
        return finish(_empty('visual_contradiction', started, margin=margin), contradiction_gap=gap)
    return finish(Decision(False, '1b_pending', card['id'], margin, None, 'needs_artwork',
                           (time.perf_counter() - started) * 1000))
