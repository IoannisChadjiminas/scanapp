"""A confidently read name on a Japanese vintage card: offer those cards to choose from.

Japanese PMCG and neo cards print no collector number, so the number+name lookup
(text_identity) never runs for them, and a reprint with the same artwork can win the
picture match (the 1996 Charizard photos ranked behind 20th/25th anniversary prints).
When a scan already needs confirmation, this adds the 1-3 unnumbered cards whose
catalogue name is exactly a confident name read. It never changes the card shown
first or the status: the collector picks, so it cannot make a wrong answer.
"""
from __future__ import annotations

import sqlite3
import unicodedata

from app.recognition.ocr import OcrHit
from app.recognition.rank import number_not_printed
from app.recognition.text_identity import confident_fractions

VERSION = 'vintage-name-choices-v1'
MAX_CHOICES = 3
MIN_NAME_CONFIDENCE = .99
GUIDANCE = ('The name read on this card matches a vintage card without a collector number. '
            'Compare your card and choose the right one, or keep the card shown.')


def _name(text: str) -> str:
    return ''.join(unicodedata.normalize('NFKC', text).split())


def vintage_name_choices(catalog: sqlite3.Connection, *, hits: list[OcrHit], numbers: list[OcrHit],
                         languages: tuple[str, ...], exclude: set[str] = frozenset()) -> tuple[list[str], str]:
    """Card ids (at most three) in unnumbered Japanese sets named exactly by a confident read.

    Returns ([], reason) when the scan is not Japanese, reads a printed fraction (the card
    is numbered), has no confident name-strip read, or the name names too many cards.
    """
    if 'ja' not in languages:
        return [], 'not_japanese'
    if confident_fractions(numbers):
        return [], 'printed_fraction'
    names = sorted({_name(h.text) for h in hits if h.region == 'name' and h.confidence is not None
                    and h.confidence >= MIN_NAME_CONFIDENCE and _name(h.text)})
    if not names:
        return [], 'no_confident_name'
    rows = catalog.execute(
        f"SELECT id, name, set_id, language, printed_collector_number FROM cards "
        f"WHERE language = 'ja' AND name IN ({','.join('?' for _ in names)}) ORDER BY id",
        names).fetchall()
    ids = [row['id'] for row in rows if number_not_printed({**dict(row), 'card_id': row['id']})]
    if not ids:
        return [], 'no_unnumbered_card'
    if len(ids) > MAX_CHOICES:
        return [], 'too_many_cards'
    ids = [card_id for card_id in ids if card_id not in exclude]
    return ids, 'choices' if ids else 'already_offered'
