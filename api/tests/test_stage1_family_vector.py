"""STAGE1_FAMILY_VECTOR: a vector leader that is another printing of the text's own card.

Plan 2026-10-26 step 2. The Pikachu and Charmander uploads of 2026-10-25/26 were refused as
``visual_contradiction`` because the Base Set reprint led the artwork; the text named the
Evolutions card by number. With the flag on, the printing comes from the text and the same-name
reprint is not a contradiction. Off by default: behaviour must be unchanged.
"""
from pathlib import Path

import numpy as np

from app.config import Settings
from app.recognition import stage1_gate
from app.recognition.stage1_answer import card_shaped_quad
from app.recognition.stage1_gate import GateOptions, decide, load_catalogue, same_name_ids

from tests.test_stage1_twin_guard import _card, _conn, _unit


PIKACHU_EVO = _card('en:xy12-35', 'Pikachu', '35', 'en', 'en:xy12-35')
PIKACHU_BASE = _card('base1-58', 'Pikachu', '58', 'en', 'base1-58')
CHARMANDER = _card('en:xy12-9', 'Charmander', '9', 'en', 'en:xy12-9')
RAYQUAZA = _card('en:xy12-99', 'Rayquaza', '99', 'en', 'en:xy12-99')
ROWS = [PIKACHU_EVO, PIKACHU_BASE, CHARMANDER, RAYQUAZA]


def _run(scores, *, name='Pikachu', number='35/108', family=False, stage1b=False):
    """Vector leaders chosen by giving each catalogue row the score in ``scores`` (dot product)."""
    conn = _conn(ROWS)
    by_key, by_id, bare = load_catalogue(conn)
    query = _unit(1.0)
    embeddings = np.stack([_unit(score, np.sqrt(max(0.0, 1 - score * score))) for score in scores])
    options = GateOptions(family_vector=family, diagnostics=True)
    return decide(query, embeddings, [row[0] for row in ROWS], by_key=by_key, by_id=by_id, bare_ids=bare,
                  name=name, number=number, language='en', quad_ok=True, stage1b=stage1b, options=options)


def test_same_name_ids_collects_every_printing_of_the_name():
    _, by_id, _ = load_catalogue(_conn(ROWS))
    assert same_name_ids(by_id, 'en:xy12-35') == {'en:xy12-35', 'base1-58'}
    assert same_name_ids(by_id, 'missing') == frozenset()


def test_flag_off_keeps_the_contradiction():
    # Base Set Pikachu leads by 0.08 over the Evolutions card the text names.
    decision = _run([0.80, 0.88, 0.10, 0.10], family=False, stage1b=True)
    assert not decision.answered
    assert decision.reason == 'visual_contradiction'


def test_flag_on_takes_the_text_printing_when_the_name_family_leads():
    decision = _run([0.80, 0.88, 0.10, 0.10], family=True)
    assert decision.answered
    assert decision.card_id == 'en:xy12-35'
    assert decision.stage == '1'


def test_flag_on_still_refuses_when_another_name_leads():
    # Charmander, a different card, leads the whole field: the family is not the answer.
    decision = _run([0.80, 0.88, 0.95, 0.10], family=True, stage1b=True)
    assert not decision.answered
    assert decision.reason == 'visual_contradiction'


def test_flag_on_stage1b_candidate_when_family_is_level_with_another_name():
    # Family 0.80 against the best other card 0.79: no stage 1 margin, but no contradiction either,
    # so the artwork check decides (stage 1b pending).
    decision = _run([0.80, 0.70, 0.79, 0.10], family=True, stage1b=True)
    assert decision.stage == '1b_pending'
    assert decision.card_id == 'en:xy12-35'


def test_family_margin_is_against_other_names_only():
    # Family best 0.80 against the best other card 0.79: the margin is 0.01, under 0.02.
    decision = _run([0.80, 0.70, 0.79, 0.10], family=True)
    assert not decision.answered
    assert decision.reason == 'low_margin'


def test_flag_off_by_default_in_code_on_in_staging_off_in_production():
    # Off in code: the stage 1b contradiction contract (test_stage1_gate) refuses a same-name card
    # with another number. Staging runs the rule; the owner decides the code default.
    assert GateOptions().family_vector is False
    assert Settings(_env_file=None).stage1_family_vector is False
    staging = (Path(__file__).resolve().parents[2] / 'compose.dokploy.yaml').read_text()
    assert 'STAGE1_FAMILY_VECTOR: ${STAGE1_FAMILY_VECTOR:-true}' in staging
    production = (Path(__file__).resolve().parents[2] / 'compose.dokploy.production.yaml').read_text()
    assert 'STAGE1_FAMILY_VECTOR: ${STAGE1_FAMILY_VECTOR:-false}' in production
    assert Settings(_env_file=None).stage1b_frame_fallback is False


def test_card_shaped_quad_accepts_a_raw_card_and_rejects_the_artwork_window():
    size = (1363, 1904)
    card = [[0.01, 0.012], [0.99, 0.012], [0.99, 0.988], [0.01, 0.988]]
    artwork = [[0.08, 0.12], [0.92, 0.12], [0.92, 0.52], [0.08, 0.52]]
    assert card_shaped_quad(card, size)
    assert not card_shaped_quad(artwork, size)
    assert not card_shaped_quad(None, size)
