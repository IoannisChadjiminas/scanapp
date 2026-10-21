"""Printed number plus a name read anywhere: a short catalogue list for an abstaining scan.

A slab or screenshot can put the wrong text in the title strip (a label's PRISTINE, a page
header) while the footer number is read perfectly and the card's name appears in some other
OCR line. Together they often leave one card. This only proposes candidates: the pipeline
still runs local artwork verification, and an unverified list is shown for confirmation,
never as a match.
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata

from app.recognition.ocr import OcrHit, grading_label_line
from app.recognition.rank import (accepted_collector_numbers, name_match, normalize_text,
                                  number_matches_identifiers, parse_collector)
from app.set_totals import set_total

VERSION = 'number-name-candidates-v1'
MAX_CANDIDATES = 3
MIN_NUMBER_CONFIDENCE = .90
MIN_NAME_CONFIDENCE = .80
# A mechanic suffix is not part of the species name read on a thumbnail or label.
SUFFIX = re.compile(r'(?:vmax|vstar|vunion|ex|gx|v|break|lvx)$')


def _cjk(text: str) -> bool:
    return any('぀' <= c <= 'ヿ' or '一' <= c <= '鿿' or '가' <= c <= '힣'
               for c in text)


def name_tokens(hits: list[OcrHit]) -> list[str]:
    """Confident lines that could carry a card name, HP and digits removed."""
    tokens = []
    for hit in hits:
        if hit.confidence is None or hit.confidence < MIN_NAME_CONFIDENCE or grading_label_line(hit.text):
            continue
        text = unicodedata.normalize('NFKC', hit.text)
        text = re.sub(r'(?i)\bHP\b|\d+', ' ', text).strip()
        token = normalize_text(text)
        if len(token) >= (2 if _cjk(token) else 4) and token not in tokens:
            tokens.append(token)
    return tokens


def _stem(name: str) -> str:
    value = normalize_text(name)
    stem = SUFFIX.sub('', value)
    return stem if len(stem) >= (2 if _cjk(stem) else 3) else value


def name_agrees(tokens: list[str], *names: str) -> bool:
    """A token is the catalogue name, contains its stem, or is a fuzzy Latin match."""
    for name in filter(None, names):
        full, stem = normalize_text(name), _stem(name)
        for token in tokens:
            if _cjk(token) != _cjk(full):
                continue
            if token == full or stem in token or (len(token) >= 3 and token in full):
                return True
            if not _cjk(token) and name_match(token, name):
                return True
    return False


def confident_fractions(numbers: list[OcrHit]) -> list[OcrHit]:
    return [h for h in numbers if h.region == 'collector' and h.confidence is not None
            and h.confidence >= MIN_NUMBER_CONFIDENCE and '/' in h.text
            and (p := parse_collector(h.text)) is not None and p.denominator]


def text_identity_candidates(index, catalog: sqlite3.Connection, *, hits: list[OcrHit],
                             numbers: list[OcrHit], languages: tuple[str, ...]) -> tuple[list[str], str]:
    """Card ids (at most three) agreeing with the one confident fraction and a read name.

    Returns ([], reason) when the evidence is missing, contradictory or too broad.
    """
    fractions = confident_fractions(numbers)
    if not fractions:
        return [], 'no_confident_fraction'
    keys = {(p.prefix, p.number, p.denominator) for h in fractions if (p := parse_collector(h.text))}
    if len(keys) != 1:
        return [], 'conflicting_fractions'
    prefix, number, _ = next(iter(keys))
    pool = [row for row in index.by_number.get((prefix, number), ())
            if not languages or row.get('language') in languages]
    if not pool:
        return [], 'number_not_in_catalogue'
    ids = [row['id'] for row in pool]
    placeholders = ','.join('?' for _ in ids)
    rows = {r['id']: dict(r) for r in catalog.execute(
        f'SELECT * FROM cards WHERE id IN ({placeholders})', ids)}
    numbered = []
    for card_id in ids:
        row = rows.get(card_id)
        if row is None:
            continue
        row['card_id'] = card_id
        row['set_total'] = set_total(catalog, row['language'], row['set_id'])
        # Printed fraction or set number plus a known set total. A bare catalogue
        # number accepts any denominator, which is not a printed-number agreement.
        expected = [n for n in accepted_collector_numbers(row)
                    if (p := parse_collector(n)) is not None and p.denominator]
        if expected and all(number_matches_identifiers([h], expected) is True for h in fractions):
            numbered.append(row)
    if not numbered:
        return [], 'number_not_in_catalogue'
    tokens = name_tokens(hits)
    if not tokens:
        return [], 'no_name_token'
    named = [row for row in numbered
             if name_agrees(tokens, row['name'], str(row.get('view_title') or ''))]
    if not named:
        return [], 'no_name_agreement'
    if len(named) > MAX_CANDIDATES:
        # The catalogue has no HP column to break the tie; too broad to propose.
        return [], 'too_many_candidates'
    return sorted(row['card_id'] for row in named), 'candidates'
