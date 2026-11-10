"""Two narrow misread rules from the retired sealed photos (both flags off by default).

OCR_DAMAGE_NUMBER_GUARD: a Japanese card prints its collector number with three digits (040), so
an unpadded bare "40" read from the footer strip of a Japanese card is attack damage or HP. The
reads are dropped only when they are the footer's only bare numbers: removing one of several noisy
reads would promote the rest (a slabbed Emolga BW-P 236 read "60" and "4"; dropping "60" left "4"
naming PokéPark's Pikachu 004).

LATIN_NAME_TWIN: Japanese Southern Islands Mew prints ミュウ. When the visual leader is Japanese but
the name strip reads the leader's English name in Latin letters, the photo shows the English print;
the one English card with that name in the same-named set is proposed and put first.
"""
from __future__ import annotations

import re
from typing import Any

from app.recognition.rank import normalize_text

LATIN_NAME = re.compile(r"[A-Za-z][A-Za-z .'\-]{2,}")


def damage_number_guard(numbers: list, leader_language: str | None) -> list:
    if (leader_language or '').lower() != 'ja':
        return list(numbers or [])
    numbers = list(numbers or [])
    bare = [h for h in numbers if h.region == 'collector' and h.text.isdigit()]
    damage = [h for h in bare if len(h.text) <= 2 and int(h.text) % 10 == 0]
    if len(damage) < len(bare):
        return numbers
    return [h for h in numbers if h not in damage]


def _get(row: Any, key: str) -> str:
    try:
        return str(row[key] or '')
    except (KeyError, IndexError, TypeError):
        return ''


def latin_name_twin(by_name: dict, leader: Any, ocr_name: str | None, fetch=None) -> str | None:
    """fetch(ids) -> {id: row} completes index rows that lack set_name."""
    if leader is None or _get(leader, 'language').lower() == 'en':
        return None
    name = (ocr_name or '').strip()
    if not LATIN_NAME.fullmatch(name):
        return None
    key = normalize_text(name)
    if key not in {normalize_text(_get(leader, 'name')), normalize_text(_get(leader, 'view_title'))} - {''}:
        return None
    set_name = normalize_text(_get(leader, 'set_name'))
    english = [r for r in by_name.get(key, ()) if _get(r, 'language') == 'en']
    if fetch is not None and english:
        full = fetch([_get(r, 'id') for r in english])
        english = [full.get(_get(r, 'id'), r) for r in english]
    rows = [r for r in english if set_name and normalize_text(_get(r, 'set_name')) == set_name]
    return _get(rows[0], 'id') if len(rows) == 1 else None
