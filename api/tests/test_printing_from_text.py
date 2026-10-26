"""OCR_PRINTING_FROM_TEXT: the printing the phone's own name and number name orders an ambiguous result.

Plan 2026-10-26 step 1. The 16 disagreements of the family-vector benchmark were printing choices where
the server never read the footer number, so the visual leader was shown first. The phone's text carries
the number; when it names exactly one card (set totals applied) and that card is a candidate, it goes first.
It only orders: the status stays printing_ambiguous.
"""
import sqlite3
from types import SimpleNamespace

from app.config import Settings
from app.recognition.pipeline import _text_named_card
from app.recognition.stage1_gate import GateOptions  # noqa: F401  (keeps the import path honest)


def _catalog(rows, totals=()):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE cards (id TEXT, name TEXT, view_title TEXT, collector_number TEXT, '
                 'printed_collector_number TEXT, language TEXT, set_id TEXT, image_path TEXT)')
    conn.executemany('INSERT INTO cards VALUES (?,?,?,?,?,?,?,?)', rows)
    conn.execute('CREATE TABLE set_totals (language TEXT, set_id TEXT, official_total INTEGER, fetched_at TEXT)')
    conn.executemany('INSERT INTO set_totals VALUES (?,?,?,?)', [(lang, set_id, total, 'x') for lang, set_id, total in totals])
    return conn


def _row(card_id, name, number, set_id):
    return (card_id, name, None, number, number, 'en', set_id, None)


def _text(name, number):
    return SimpleNamespace(name=name, number=number)


SETTINGS = Settings(_env_file=None)
ROWS = [
    _row('en:xy12-35', 'Pikachu', '35', 'xy12'),
    _row('en:30th-035', 'Pikachu', '35', '30th'),
    _row('base1-58', 'Pikachu', '58', 'base1'),
    _row('en:xy12-9', 'Charmander', '9', 'xy12'),
    _row('base1-46', 'Charmander', '46', 'base1'),
]
TOTALS = [('en', 'xy12', 108), ('en', '30th', 128), ('en', 'base1', 102)]


def test_the_footer_total_picks_the_printing_among_same_number_sets():
    runtime = SimpleNamespace()
    catalog = _catalog(ROWS, TOTALS)
    assert _text_named_card(runtime, catalog, _text('Pikachu', '35/108'), SETTINGS) == 'en:xy12-35'
    assert _text_named_card(runtime, catalog, _text('Charmander', '9/108'), SETTINGS) == 'en:xy12-9'


def test_without_the_set_total_the_same_number_stays_ambiguous():
    # Two Pikachu 35s with no total to tell them apart: the phone's text names no single card.
    runtime = SimpleNamespace()
    assert _text_named_card(runtime, _catalog(ROWS, ()), _text('Pikachu', '35'), SETTINGS) is None


def test_a_missing_name_or_number_names_nothing():
    runtime = SimpleNamespace()
    catalog = _catalog(ROWS, TOTALS)
    assert _text_named_card(runtime, catalog, None, SETTINGS) is None
    assert _text_named_card(runtime, catalog, _text(None, '9/108'), SETTINGS) is None
    assert _text_named_card(runtime, catalog, _text('Charmander', None), SETTINGS) is None


def test_the_catalogue_is_cached_on_the_runtime_once():
    runtime = SimpleNamespace()
    catalog = _catalog(ROWS, TOTALS)
    _text_named_card(runtime, catalog, _text('Pikachu', '35/108'), SETTINGS)
    cached = runtime.printing_text_catalogue
    _text_named_card(runtime, catalog, _text('Charmander', '9/108'), SETTINGS)
    assert runtime.printing_text_catalogue is cached


def test_the_flag_defaults_off_in_code_and_in_production_compose():
    assert Settings(_env_file=None).ocr_printing_from_text is False
    from pathlib import Path
    production = (Path(__file__).resolve().parents[2] / 'compose.dokploy.production.yaml').read_text()
    assert 'OCR_PRINTING_FROM_TEXT: ${OCR_PRINTING_FROM_TEXT:-false}' in production
