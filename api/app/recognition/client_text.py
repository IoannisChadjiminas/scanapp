"""The phone's own OCR of the card: a hint for skipping work, never evidence.

The phone reads the card's name and collector number on the device and sends
them as `client_text`, a small JSON object:

    {"v": 1, "engine": "apple-vision", "name": "Blastoise", "name_conf": 0.98,
     "number": "14/100", "number_conf": 0.95, "ms": 140}

The server never lets this text choose, rank or confirm a card. It only lets
the server skip its optional OCR re-reads when the phone confirms what the
server already found from pixels: a clear visual and artwork leader, with a
single printing for that collector number. Anything else runs the full path.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
import re
import unicodedata
from typing import Any

from app.physical_cards import is_tcg_pocket_card
from app.recognition.ocr import OcrHit, OcrResult
from app.recognition.printing import printing_key
from app.recognition.rank import (RELIABLE_COLLECTOR_CONF, accepted_collector_numbers,
                                  extract_collector_candidates, name_match,
                                  number_matches_identifiers, parse_collector)

VERSION = 'client-text-v1'
OCR_MODES = ('off', 'footer', 'all')
# The phone may add up to five raw number reads (see `number_candidates`); with a long
# name and a slab label they need room beyond the 768 bytes of the first version.
MAX_BYTES = 1280
CANDIDATE_REGIONS = ('footer', 'corner_left', 'corner_right', 'label')
MAX_CANDIDATES = 5
# With CLIENT_TEXT_TOP20 the phone's name and number may name a card anywhere in this many visual candidates.
TOP_N_NAMED = 20
_LABEL_KEYS = {
    'label_name', 'label_name_conf', 'label_number', 'label_number_conf',
    'label_set', 'label_language', 'label_grader', 'label_grade',
}
_KEYS = {'v', 'engine', 'name', 'name_conf', 'number', 'number_conf', 'ms', 'number_candidates',
         *_LABEL_KEYS}
_ENGINE = re.compile(r'^[a-z0-9][a-z0-9._-]{0,31}$')
# 14/100, 045/198, TG12/TG30, GG01/GG70, SWSH050, SVP 045, SM35, 25a.
_NUMBER = re.compile(r'^(?:[A-Z]{1,5}[- ]?)?\d{1,4}[A-Z]?(?:\s*/\s*(?:[A-Z]{1,4})?\d{1,4})?$',
                     re.IGNORECASE)


@dataclass(frozen=True)
class ClientText:
    engine: str
    name: str | None = None
    name_conf: float | None = None
    number: str | None = None
    number_conf: float | None = None
    ms: int | None = None
    number_candidates: tuple[str, ...] = ()


def _confidence(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('bad_confidence')
    value = float(value)
    if not math.isfinite(value) or not 0. <= value <= 1.:
        raise ValueError('bad_confidence')
    return value


def _name(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('bad_name')
    text = unicodedata.normalize('NFC', value).strip()
    if (not 1 <= len(text) <= 64 or not any(c.isalpha() for c in text)
            or any(unicodedata.category(c).startswith('C') for c in text)):
        raise ValueError('bad_name')
    return text


def _number(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('bad_number')
    text = value.strip()
    if len(text) > 16 or not _NUMBER.fullmatch(text):
        raise ValueError('bad_number')
    compact = re.sub(r'[- ]', '', text).upper()
    # Gallery numbers print the namespace twice (TG01/TG30); the parser takes TG01/30.
    compact = re.sub(r'^([A-Z]{1,4})(\d{1,4})/\1(\d{1,4})$', r'\1\2/\3', compact)
    if parse_collector(compact) is None:
        raise ValueError('bad_number')
    return compact


def number_candidates(value: Any) -> tuple[str, ...]:
    """Raw number-like reads from the phone, sanitized. Bad entries are dropped, never the hint.

    Each entry is ``{"text": <=16 chars, "conf": 0..1 or null, "region": one of CANDIDATE_REGIONS}``,
    at most five, in the order the phone sent them (best first). The text is kept as read: the
    catalogue, not the format, decides whether a repaired number is real.
    """
    if not isinstance(value, list):
        return ()
    found: list[str] = []
    for item in value[:MAX_CANDIDATES]:
        if not isinstance(item, dict) or set(item) != {'text', 'conf', 'region'}:
            continue
        text, region = item['text'], item['region']
        if not isinstance(text, str) or region not in CANDIDATE_REGIONS:
            continue
        try:
            _confidence(item['conf'])
        except ValueError:
            continue
        text = unicodedata.normalize('NFC', text).strip()
        if (not 1 <= len(text) <= 16 or any(unicodedata.category(c).startswith('C') for c in text)
                or text in found):
            continue
        found.append(text)
    return tuple(found)


def parse_client_text(raw: str | None) -> tuple[ClientText | None, str]:
    """Strictly validated hint and why it was taken or dropped. Never raises."""
    if raw is None or not raw.strip():
        return None, 'absent'
    if len(raw.encode('utf-8', 'surrogatepass')) > MAX_BYTES:
        return None, 'too_long'
    try:
        body = json.loads(raw)
    except ValueError:
        return None, 'not_json'
    if not isinstance(body, dict):
        return None, 'not_object'
    if set(body) - _KEYS:
        return None, 'unknown_keys'
    version = body.get('v')
    # Version 2 adds slab label fields. They are logged elsewhere and are not
    # part of this hint, so a version 2 body with no label field is still refused.
    if version not in (1, 2) or isinstance(version, bool) or (
            version == 2 and not (_LABEL_KEYS & set(body))):
        return None, 'bad_version'
    engine = body.get('engine')
    if not isinstance(engine, str) or not _ENGINE.fullmatch(engine):
        return None, 'bad_engine'
    ms = body.get('ms')
    if ms is not None and (isinstance(ms, bool) or not isinstance(ms, int) or not 0 <= ms <= 60_000):
        return None, 'bad_ms'
    try:
        hint = ClientText(engine=engine, name=_name(body.get('name')),
                          name_conf=_confidence(body.get('name_conf')),
                          number=_number(body.get('number')),
                          number_conf=_confidence(body.get('number_conf')), ms=ms,
                          number_candidates=number_candidates(body.get('number_candidates')))
    except ValueError as error:
        return None, str(error)
    if hint.name is None and hint.number is None and not hint.number_candidates:
        return None, 'empty'
    return hint, 'ok'


def printings_with_number(catalog, lead: dict[str, Any], number: str) -> set[tuple] | None:
    """Printings of the leader's name and language that a phone number fits.

    A bare catalogue number fits any denominator, so this can only over-count.
    None when the family is too large to inspect.
    """
    rows = catalog.execute(
        'SELECT id, name, set_id, set_name, collector_number, printed_collector_number, language '
        'FROM cards WHERE name = ? AND language = ? ORDER BY id LIMIT 513',
        (str(lead['name']), str(lead.get('language') or ''))).fetchall()
    if len(rows) > 512:
        return None
    found = set()
    for row in rows:
        card = dict(row)
        if is_tcg_pocket_card(card.get('language'), card.get('set_id')):
            continue
        if number_matches_identifiers([number], accepted_collector_numbers(card)) is True:
            found.add(printing_key(card))
    return found


def fast_path_decision(hint: ClientText | None, candidates: list[dict], lead: dict | None,
                       artwork_hits, catalog, *, image_size, min_confidence: float) -> tuple[bool, str]:
    """May the optional OCR re-reads be skipped for this frame? Decided before OCR.

    `candidates` is the full-card visual shortlist (card_id, name, visual_score,
    language); `lead` the catalogue row of its first entry with set_total. The
    visual and artwork thresholds are those of the existing title-only rule.

    The margin is measured to the best other card in the leader's language. The
    same artwork printed in another language is often a near tie; the server's
    own title read separates those, so then that read must agree confidently
    ('eligible_title_required'). An alias of the leader is not a rival.
    """
    if hint is None:
        return False, 'no_hint'
    if not hint.name or not hint.number:
        return False, 'incomplete'
    if (hint.name_conf or 0.) < min_confidence or (hint.number_conf or 0.) < min_confidence:
        return False, 'low_confidence'
    width, height = image_size
    if not .62 <= width / height <= .80:
        return False, 'frame_shape'
    if not candidates or lead is None:
        return False, 'no_runner_up'
    first = candidates[0]
    language = str(lead.get('language') or '')
    rivals = [c for c in candidates[1:] if not _alias(c['card_id'], first['card_id'])]
    same = next((c for c in rivals if c.get('language', language) == language), None)
    other = next((c for c in rivals if c.get('language', language) != language), None)
    if first['visual_score'] < .85 or (same is not None
                                       and first['visual_score'] - same['visual_score'] < .08):
        return False, 'visual_margin'
    art = next((h for h in artwork_hits if h.card_id == first['card_id']), None)
    if art is None or art.score < .80:
        return False, 'artwork'
    if not name_match(hint.name, first['name']):
        return False, 'name_disagrees'
    if number_matches_identifiers([hint.number], accepted_collector_numbers(lead)) is not True:
        return False, 'number_disagrees'
    if printings_with_number(catalog, lead, hint.number) != {printing_key(lead)}:
        return False, 'printings'
    if other is not None and first['visual_score'] - other['visual_score'] < .08:
        return True, 'eligible_title_required'
    return True, 'eligible'


def named_in_top(hint: ClientText, top: list[dict], lead_for, catalog, *, mode: str):
    """The one card in the visual top list that the phone's name and number name. Decided before OCR.

    Used only with CLIENT_TEXT_TOP20. The visual leader is not required: any card in the top list
    whose name matches and whose collector number fits, counted with its set total. Exactly one card
    may qualify (aliases of one card count once), and the catalogue must hold one printing of that
    name with that number. A same-name reprint in the list makes two qualifying cards, so it is refused.
    Returns (allowed, card_id, reason).
    """
    named: dict[str, tuple[dict, dict]] = {}
    for candidate in top:
        lead = lead_for(candidate['card_id'])
        if lead is None or not name_match(hint.name, candidate['name']):
            continue
        if number_matches_identifiers([hint.number], accepted_collector_numbers(lead)) is not True:
            continue
        key = candidate['card_id'].split(':', 1)[-1]
        named.setdefault(key, (candidate, lead))
    if not named:
        return False, None, 'not_in_top'
    if len(named) > 1:
        return False, None, 'several_in_top'
    (candidate, lead), = named.values()
    if printings_with_number(catalog, lead, hint.number) != {printing_key(lead)}:
        return False, None, 'printings'
    return True, candidate['card_id'], 'eligible_top'


def ocr_skip_decision(hint: ClientText | None, candidates: list[dict], lead_for, catalog, *,
                      mode: str, image_size, min_confidence: float, min_visual: float,
                      min_gap: float, top_n: int = 1) -> tuple[bool, str | None, str]:
    """May the phone's read stand in for server OCR on this frame? Decided before OCR.

    The phone must confirm the visual leader by name and number, and the catalogue must
    have one printing of that name with that number. The phone never settles a near tie:
    with 'footer' the server still reads the title, which separates different names and
    scripts, so only a same-name reprint within `min_gap` stops it; with 'all' any other
    card within `min_gap` does.

    The leader is the visual first, even when the same artwork in another language ranks
    above the phone's card (マリル above Marill): the footer read is what lets the ranker
    rule that print out, so standing in there turned matched scans uncertain on the
    replay. Returns whether the phone may stand in, the card it confirmed, and the reason.
    """
    if hint is None:
        return False, None, 'no_hint'
    if not hint.name or not hint.number:
        return False, None, 'incomplete'
    if (hint.name_conf or 0.) < min_confidence or (hint.number_conf or 0.) < min_confidence:
        return False, None, 'low_confidence'
    width, height = image_size
    if not .62 <= width / height <= .80:
        return False, None, 'frame_shape'
    if not candidates:
        return False, None, 'no_candidates'
    if top_n > 1:
        return named_in_top(hint, candidates[:top_n], lead_for, catalog, mode=mode)
    first = candidates[0]
    lead = lead_for(first['card_id'])
    if lead is None:
        return False, None, 'no_candidates'
    if first['visual_score'] < min_visual:
        return False, None, 'visual_floor'
    if not name_match(hint.name, first['name']):
        return False, None, 'name_disagrees'
    if number_matches_identifiers([hint.number], accepted_collector_numbers(lead)) is not True:
        return False, None, 'number_disagrees'
    if printings_with_number(catalog, lead, hint.number) != {printing_key(lead)}:
        return False, None, 'printings'
    ties = [c for c in candidates[1:] if not _alias(c['card_id'], first['card_id'])
            and first['visual_score'] - c['visual_score'] < min_gap]
    if mode == 'footer':
        if any(name_match(hint.name, c['name']) for c in ties):
            return False, None, 'reprint_tie'
    elif ties:
        return False, None, 'visual_tie'
    return True, first['card_id'], 'eligible'


def phone_read(hint: ClientText) -> OcrResult:
    """The phone's text as the card read, for CLIENT_TEXT_OCR=all."""
    return OcrResult(name_text=hint.name, collector_text=hint.number, lines=[hint.name, hint.number],
                     hits=[OcrHit(hint.name, hint.name_conf, 'name'),
                           OcrHit(hint.number, hint.number_conf, 'collector')],
                     failed=False, client_text_used='all')


def with_phone_number(observed: OcrResult, hint: ClientText) -> OcrResult:
    """A server title-only read completed with the phone's collector number."""
    return replace(observed, collector_text=hint.number, lines=[*observed.lines, hint.number],
                   hits=[*observed.hits, OcrHit(hint.number, hint.number_conf, 'collector')],
                   footer_skipped=False, client_text_used='number')


def _alias(a: str, b: str) -> bool:
    """One catalogue card listed with and without its language prefix (sv01-210, en:sv01-210)."""
    return a.split(':', 1)[-1] == b.split(':', 1)[-1]


def server_read_agrees(hint: ClientText, ocr, *, require_title: bool = False) -> bool:
    """The server's own first read does not contradict the phone.

    A missing or weak server read is no contradiction: the visual leader and
    the phone already agree. A confident different title, or a readable
    collector number that is not the phone's, is. With `require_title` the
    server must itself have read the phone's title confidently.
    """
    if ocr.failed:
        return False
    if require_title and not any(
            h.region == 'name' and h.text == ocr.name_text and (h.confidence or 0.) >= .85
            and name_match(h.text, hint.name or '') for h in ocr.hits):
        return False
    for hit in ocr.hits:
        if hit.region == 'name' and hit.text == ocr.name_text and (hit.confidence or 0.) >= .5:
            if not name_match(hit.text, hint.name or ''):
                return False
    numbers = [h for h in extract_collector_candidates([], hits=ocr.hits)
               if ('/' in h.text or any(c.isalpha() for c in h.text))
               and (h.confidence is None or h.confidence >= RELIABLE_COLLECTOR_CONF)]
    if numbers and number_matches_identifiers(numbers, [hint.number or '']) is not True:
        return False
    return True


def agreement(hint: ClientText, *, top: dict | None, ocr_name: str | None,
              ocr_numbers: list) -> dict[str, bool | None]:
    """How the phone's read compares with the server's answer and its OCR, for rollout logs."""
    def number_agrees(identifiers):
        if not hint.number or not identifiers:
            return None
        return number_matches_identifiers([hint.number], identifiers) is True
    return dict(
        top_name=(name_match(hint.name, str(top['name'])) if hint.name and top else None),
        top_number=number_agrees(accepted_collector_numbers(top) if top else []),
        ocr_name=(name_match(hint.name, ocr_name) if hint.name and ocr_name else None),
        ocr_number=(number_matches_identifiers(ocr_numbers, [hint.number]) is True
                    if hint.number and ocr_numbers else None),
    )


def _flag(value: bool | None) -> str:
    return 'none' if value is None else str(value).lower()


def client_text_line(scan_id: str, hint: ClientText | None, reason: str, *, status: str,
                     top: dict | None, ocr_name: str | None, ocr_numbers: list,
                     fast_path: str, ocr_skip: str = 'off') -> str:
    """One greppable line per hinted scan. The phone's title text itself is not logged."""
    parts = ['client_text', f'scan_id={scan_id}', f'parse={reason}']
    if hint is not None:
        agrees = agreement(hint, top=top, ocr_name=ocr_name, ocr_numbers=ocr_numbers)
        parts += [f'engine={hint.engine}',
                  f'name={"yes" if hint.name else "no"}',
                  f'name_conf={"none" if hint.name_conf is None else f"{hint.name_conf:.2f}"}',
                  f'number={hint.number or "none"}',
                  f'number_conf={"none" if hint.number_conf is None else f"{hint.number_conf:.2f}"}',
                  f'phone_ms={"none" if hint.ms is None else hint.ms}',
                  *(f'{key}_agrees={_flag(value)}' for key, value in agrees.items())]
    parts += [f'fast_path={fast_path}', f'ocr_skip={ocr_skip}', f'status={status}', f'top={(top or {}).get("card_id") or "none"}']
    return ' '.join(parts)
