"""Catalogue-constrained repairs of the phone's text, for the stage 1 gate only.

Neither repair can choose a card. Each one only offers extra spellings of the
same text to the gate's ordinary lookup, which still needs the phone's name and
the catalogue's number and set total to agree, and stage 1 still needs the
vector (or stage 1b the artwork) to agree afterwards.

* ``number_variants``: o/O to 0 and l/I/| to 1 inside the number only; a ``T``
  or ``)`` read as the slash, a missing slash, or a total cut short, accepted
  only when the result is a number and total the catalogue holds for that
  numerator. A variant the catalogue does not hold is never produced.
* ``fuzzy_name_ok``: a small edit distance on names folded for case, accents,
  spaces and ``&``. Used only after the number and its total have narrowed the
  candidates.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import re
import unicodedata

from app.recognition.label_identity import number_key
from app.recognition.rank import parse_collector

PREFIXES = ('SWSH', 'HGSS', 'SVP', 'S-P', 'SV-P', 'SV', 'TG', 'GG', 'RC', 'SM', 'XY', 'BW', 'DP', 'H')
_CONFUSED = {'O': '0', 'I': '1', 'L': '1', '|': '1'}
# What a slash is read as: the glyph itself, a T, or a closing bracket.
_SLASH_LIKE = '/T)'
MAX_VARIANTS = 8


def card_totals(card: dict) -> set[str]:
    """Printed denominators the catalogue holds for a card, as bare digit strings."""
    totals = set()
    for key in ('printed_collector_number', 'collector_number'):
        parts = parse_collector(card.get(key))
        if parts and parts.denominator:
            totals.add(parts.denominator)
    if not totals and type(card.get('set_total')) is int and card['set_total'] > 0:
        totals.add(str(card['set_total']))
    return totals


def _body(text: str) -> tuple[str, str] | None:
    """Prefix and the rest of the number, with confusable letters made digits."""
    prefix = ''
    for candidate in PREFIXES:
        if text.startswith(candidate):
            prefix = candidate
            break
    rest = text[len(prefix):].lstrip('-')
    if prefix:
        rest = rest.replace('/' + prefix, '/', 1)  # gallery numbers print the namespace twice: TG01/TG30
    mapped = ''.join(_CONFUSED.get(char, char) for char in rest)
    if not re.fullmatch(r'[0-9/T)]+', mapped):
        return None
    return prefix, mapped


def _splits(body: str) -> list[tuple[str, str, str]]:
    """(numerator, separator, fragment) readings of the digits around a slash-like glyph."""
    found = re.fullmatch(r'(\d{1,4})([/T)])(\d{1,4})', body)
    if found:
        return [(found[1], found[2], found[3])]
    if re.fullmatch(r'\d{5,8}', body):
        # A slash that was not read at all: every split, the catalogue decides.
        return [(body[:size], '', body[size:]) for size in range(1, 5) if 2 <= len(body) - size <= 4]
    return []


def _total_fits(total: str, fragment: str, separator: str) -> bool:
    fragment = fragment.lstrip('0') or '0'
    if total == fragment:
        return True
    if separator == '':
        return False  # nothing marked where the slash was; only an exact total fits
    if separator == '/' and len(fragment) >= 2 and total.startswith(fragment) and len(total) - len(fragment) == 1:
        return True  # "204/19" cut short of 193
    return (separator in 'T)' and total.endswith(fragment)
            and 1 <= len(total) - len(fragment) <= 2)  # "013T2" for 013/172


def number_variants(number: str | None, by_key: dict[str, list[dict]]) -> list[str]:
    """Other spellings of ``number`` the catalogue holds. Empty when there is nothing to offer."""
    if not number or not isinstance(number, str):
        return []
    text = re.sub(r'\s+', '', number.upper()).lstrip('#')
    text = re.sub(r'[^0-9A-Z]+$', '', text)
    if not text or len(text) > 20:
        return []
    split = _body(text)
    if split is None:
        return []
    prefix, body = split
    variants: list[str] = []

    def add(value: str) -> None:
        if value != number and value not in variants:
            variants.append(value)

    if re.fullmatch(r'\d{1,4}', body):
        if prefix or body != text:  # "TGO5" -> "TG05", "O65" -> "065"
            add(prefix + body)
        return variants[:MAX_VARIANTS]
    for numerator, separator, fragment in _splits(body):
        pool = by_key.get(number_key(prefix + numerator) or '', [])
        for card in pool:
            for total in sorted(card_totals(card)):
                if _total_fits(total, fragment, separator):
                    add(f'{prefix}{numerator}/{total}')
    return variants[:MAX_VARIANTS]


def _fold(value: str | None) -> str:
    text = unicodedata.normalize('NFKD', value or '')
    text = ''.join(char for char in text if not unicodedata.combining(char)).casefold().replace('&', '')
    return ''.join(char for char in text if char.isalnum())


def edit_distance(left: str, right: str, limit: int) -> int:
    """Levenshtein distance, stopping early once it exceeds ``limit``."""
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a != b)))
        if min(current) > limit:
            return limit + 1
        previous = current
    return previous[-1]


def fuzzy_name_ok(phone: str | None, card_name: str | None) -> bool:
    """Close enough to the catalogue name: two edits on long names, one on short ones, or 0.8 similar."""
    left, right = _fold(phone), _fold(card_name)
    if not left or not right or any(ord(char) > 0x2E80 for char in left + right):
        return False
    shortest = min(len(left), len(right))
    if shortest < 4:
        return left == right
    allowed = 2 if shortest >= 6 else 1
    if edit_distance(left, right, allowed) <= allowed:
        return True
    return shortest >= 6 and SequenceMatcher(None, left, right).ratio() >= 0.8
