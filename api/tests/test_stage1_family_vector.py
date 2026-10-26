"""STAGE1_FAMILY_VECTOR (narrow): the footer rules a same-name printing out of the vector race.

Plan docs/family-rule-narrow-plan-20261026.md. A same-name row is removed from the race only when the
phone's footer reads a full fraction whose total equals the text card's own known total and differs
from that row's known total. Without a total, or with a bare number, nothing is excluded, so the
stage 1b contradiction contract (test_stage1_gate) is unchanged.
"""
from pathlib import Path
import sqlite3

import numpy as np

from app.config import Settings
from app.recognition.stage1_gate import GateOptions, decide, footer_excluded_ids, load_catalogue, lookup, collapse_hits

from tests.test_stage1_twin_guard import _unit

ROWS = [
    # id, name, number, set_id, language
    ('en:xy12-35', 'Pikachu', '35', 'xy12', 'en'),
    ('base1-58', 'Pikachu', '58', 'base1', 'en'),
    ('en:2015xy-6', 'Pikachu', '6', '2015xy', 'en'),
    ('en:xy12-9', 'Charmander', '9', 'xy12', 'en'),
    ('base1-46', 'Charmander', '46', 'base1', 'en'),
    ('en:base1-62', 'Pikachu', '62', 'base1', 'en'),
    ('en:base4-91', 'Pikachu', '91', 'base4', 'en'),
]
TOTALS = [('en', 'xy12', 108), ('en', 'base1', 102), ('en', 'base4', 102)]
ON = GateOptions(family_vector=True, set_totals=True)
OFF = GateOptions(family_vector=False, set_totals=True)


def _catalog(totals=TOTALS, rows=ROWS):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE cards (id TEXT, name TEXT, view_title TEXT, collector_number TEXT, '
                 'printed_collector_number TEXT, language TEXT, set_id TEXT, image_path TEXT)')
    conn.executemany('INSERT INTO cards VALUES (?,?,?,?,?,?,?,?)',
                     [(i, n, None, num, num, lang, set_id, None) for i, n, num, set_id, lang in rows])
    conn.execute('CREATE TABLE set_totals (language TEXT, set_id TEXT, official_total INTEGER, fetched_at TEXT)')
    conn.executemany('INSERT INTO set_totals VALUES (?,?,?,?)', [(*t, 'x') for t in totals])
    return conn


def _run(scores, *, name, number, options, stage1b=False, rows=ROWS, totals=TOTALS):
    conn = _catalog(totals, rows)
    by_key, by_id, bare = load_catalogue(conn, options)
    ids = [row[0] for row in rows]
    embeddings = np.stack([_unit(score, np.sqrt(max(0.0, 1 - score * score))) for score in scores])
    return decide(_unit(1.0), embeddings, ids, by_key=by_key, by_id=by_id, bare_ids=bare,
                  name=name, number=number, language='en', quad_ok=True, stage1b=stage1b, options=options)


def test_footer_total_rules_out_the_base_set_reprint_and_the_text_card_answers():
    # Base Set Pikachu 58 (102) leads by 0.08 over the Evolutions card the footer names (35/108).
    # Scores follow ROWS order: en:xy12-35, base1-58, ...
    scores = [0.80, 0.88, 0.10, 0.10, 0.10, 0.10, 0.10]
    assert not _run(scores, name='Pikachu', number='35/108', options=OFF, stage1b=True).answered
    decision = _run(scores, name='Pikachu', number='35/108', options=ON, stage1b=True)
    assert decision.stage == '1' and decision.card_id == 'en:xy12-35'


def test_a_promo_without_a_known_total_is_not_excluded():
    # The leader is a Pikachu promo with no known set total: the footer cannot rule it out.
    rows = [ROWS[0], ROWS[2]]
    totals = [('en', 'xy12', 108)]
    decision = _run([0.80, 0.88], name='Pikachu', number='35/108', options=ON, stage1b=True,
                    rows=rows, totals=totals)
    assert not decision.answered and decision.reason == 'visual_contradiction'


def test_a_charmander_reprint_with_another_total_is_excluded():
    scores = [0.10, 0.10, 0.10, 0.10, 0.88, 0.10, 0.10]
    rows = [ROWS[3], ROWS[4]]
    decision = _run([0.80, 0.88], name='Charmander', number='9/108', options=ON, rows=rows)
    assert decision.stage == '1' and decision.card_id == 'en:xy12-9'
    assert not _run([0.80, 0.88], name='Charmander', number='9/108', options=OFF, rows=rows, stage1b=True).answered


def test_the_safety_contract_is_unchanged_when_totals_agree():
    # Read 62/102 against a same-name leader from another 102-card set: the totals agree, nothing is ruled out.
    scores = [0.10, 0.10, 0.10, 0.10, 0.10, 0.80, 0.88]
    decision = _run(scores, name='Pikachu', number='62/102', options=ON, stage1b=True)
    assert not decision.answered and decision.reason == 'visual_contradiction'


def test_a_bare_number_excludes_nothing():
    conn = _catalog()
    by_key, by_id, _ = load_catalogue(conn, ON)
    hits = collapse_hits(lookup(by_key, 'Pikachu', '35', 'en', ON), set())
    assert footer_excluded_ids(by_id, hits, '35', ON) == frozenset()


def test_the_text_card_total_must_agree_with_the_footer():
    conn = _catalog()
    by_key, by_id, _ = load_catalogue(conn, ON)
    hits = collapse_hits(lookup(by_key, 'Pikachu', '35/102', 'en', ON), set())
    assert footer_excluded_ids(by_id, hits, '35/102', ON) == frozenset()


def test_flags_off_in_code_and_on_in_staging_only():
    assert GateOptions().family_vector is False
    assert Settings(_env_file=None).stage1_family_vector is False
    repo = Path(__file__).resolve().parents[2]
    production = (repo / 'compose.dokploy.production.yaml').read_text()
    assert 'STAGE1_FAMILY_VECTOR: ${STAGE1_FAMILY_VECTOR:-false}' in production
