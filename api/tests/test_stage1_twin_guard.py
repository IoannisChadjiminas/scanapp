"""Stage 1b abstains on printing twins; the artwork alone may not pick one of them.

The 2026-10-25 Capsule scan answered en:sv04-159 by artwork while the full pipeline
said en:PPS5-PAR-159. The guard is default off and only changes stage 1b on twins.
"""
import base64
import io
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from app import scan_summary
from app.config import Settings
from app.recognition.stage1_answer import evaluate_stage1
from app.recognition.stage1_gate import GateOptions, decide, load_catalogue, printing_twins
from app.stage0 import PhoneEvidence, stage0_line

CAPSULE_NAME = 'Ancient Booster Energy Capsule'
QUAD = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]


def _unit(*values: float) -> np.ndarray:
    # The phone sends 384 floats, so the fixtures use the same width.
    vector = np.zeros(384, np.float32)
    vector[:len(values)] = values
    vector /= np.linalg.norm(vector)
    return vector


def _card(card_id: str, name: str, number: str, language: str, set_id: str) -> tuple:
    return (card_id, name, None, number, number, language, set_id, None)


def _conn(rows: list[tuple]) -> sqlite3.Connection:
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute(
        'CREATE TABLE cards (id TEXT, name TEXT, view_title TEXT, collector_number TEXT, '
        'printed_collector_number TEXT, language TEXT, set_id TEXT, image_path TEXT)')
    conn.executemany('INSERT INTO cards VALUES (?,?,?,?,?,?,?,?)', rows)
    return conn


def _gate(rows, embeddings, query, *, name, number, language=None, stage1b=True, guard=False, printing=True):
    conn = _conn(rows)
    by_key, by_id, bare = load_catalogue(conn)
    options = GateOptions(printing_groups=printing, twin_guard=guard, diagnostics=True)
    return decide(
        query, np.stack(embeddings), [row[0] for row in rows],
        by_key=by_key, by_id=by_id, bare_ids=bare, name=name, number=number, language=language,
        quad_ok=True, stage1b=stage1b, options=options)


# The Capsule shape: the text names sv04-159 and its Play! Pokemon reprint PPS5-PAR-159, and the
# phone's vector leads with a different card (zh-tw SV8a-157) by about 0.03 over the text card,
# while staying below the twin family. The reprint is 0.99 like the base, not a stage 1 match.
CAPSULE_ROWS = [
    _card('en:sv04-159', CAPSULE_NAME, '159', 'en', 'sv04'),
    _card('en:PPS5-PAR-159', CAPSULE_NAME, '159', 'en', 'PPS5'),
    _card('zh-tw:SV8a-157', 'Other Card', '157', 'zh-tw', 'SV8a'),
]
CAPSULE_TEXT = _unit(0.742, 0.212, 0.636)
CAPSULE_VECTORS = [_unit(1, 0), _unit(np.cos(np.radians(8)), np.sin(np.radians(8))), _unit(0.2, 0, 0.9798)]


def test_guard_defaults_off_in_code_and_is_named_in_the_scan_summary():
    assert Settings.model_fields['stage1_twin_guard'].default is False
    assert 'stage1_twin_guard' in scan_summary.SWITCHES


def test_capsule_twins_are_stage_1b_pending_on_sv04_with_the_guard_off():
    decision = _gate(CAPSULE_ROWS, CAPSULE_VECTORS, CAPSULE_TEXT, name=CAPSULE_NAME, number='159', guard=False)
    assert decision.stage == '1b_pending' and decision.card_id == 'en:sv04-159'
    assert decision.printing_ids == ('en:sv04-159', 'en:PPS5-PAR-159')


def test_capsule_twins_abstain_with_the_guard_on():
    decision = _gate(CAPSULE_ROWS, CAPSULE_VECTORS, CAPSULE_TEXT, name=CAPSULE_NAME, number='159', guard=True)
    assert not decision.answered and decision.stage is None and decision.card_id is None
    assert decision.reason == 'printing_twins'


class _Verifier:
    """Stands in for the artwork verifier: every reference matches with 40 inliers."""

    def __init__(self, root: Path):
        self.root = root

    def verify(self, _photo, _pairs):
        return [SimpleNamespace(artwork_inliers=40)]


def _photo_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', (200, 280), (120, 80, 40)).save(buffer, format='PNG')
    return buffer.getvalue()


def _client_text() -> str:
    return json.dumps({'name': CAPSULE_NAME, 'number': '159'})


def _client_embedding(vector: np.ndarray) -> str:
    return json.dumps({'model': '2ddf6ec79e37/litert-fp16',
                       'vector': base64.b64encode(vector.astype('<f2').tobytes()).decode()})


@pytest.mark.parametrize('guard, answered, reason', [(False, True, 'artwork'), (True, False, 'printing_twins')])
def test_capsule_scan_end_to_end_answers_today_and_abstains_with_the_guard(tmp_path, guard, answered, reason):
    (tmp_path / 'sv04-159.png').write_bytes(_photo_bytes())
    rows = [row if row[0] != 'en:sv04-159' else (*row[:7], 'sv04-159.png') for row in CAPSULE_ROWS]
    runtime = SimpleNamespace(
        snapshot=SimpleNamespace(embeddings=np.stack(CAPSULE_VECTORS), card_ids=[row[0] for row in rows]),
        artwork_verifier=_Verifier(tmp_path))
    settings = SimpleNamespace(stage1b_text_verify=True, stage1_printing_groups=True, stage1_twin_guard=guard,
                               stage1_set_totals=False, stage1_normalize_duplicates=False,
                               stage1_promo_numbers=False, stage1_diagnostics=True, stage1_number_repair=True,
                               stage1_fuzzy_name=False)
    decision = evaluate_stage1(
        settings=settings, runtime=runtime, catalog=_conn(rows), client_text=_client_text(),
        client_embedding=_client_embedding(CAPSULE_TEXT), card_quad=QUAD, image_bytes=_photo_bytes())
    assert decision.answered is answered
    assert decision.reason == reason
    if answered:
        assert decision.stage == '1b' and decision.card_id == 'en:sv04-159'
    else:
        assert decision.stage is None and decision.card_id is None


def test_the_abstain_reason_reaches_the_stage0_line():
    decision = _gate(CAPSULE_ROWS, CAPSULE_VECTORS, CAPSULE_TEXT, name=CAPSULE_NAME, number='159', guard=True)
    line = stage0_line(SimpleNamespace(id='scan', suggestions=[]), trace='t', source=None, evidence=PhoneEvidence(),
                       stage1='abstained', stage1_reason=decision.reason, stage1_margin=decision.margin,
                       stage1_ms=decision.ms, gate=decision)
    assert 'stage1=abstained' in line and 'stage1_reason=printing_twins' in line
    assert 'text_candidate_count=2' in line


def test_a_stage_1_printing_answer_confirmed_by_the_vector_still_answers():
    # The vector lands on the base printing itself, so the printing group is proven and still marked.
    decision = _gate(CAPSULE_ROWS, CAPSULE_VECTORS, CAPSULE_VECTORS[0], name=CAPSULE_NAME, number='159',
                     stage1b=False, guard=True)
    assert decision.answered and decision.stage == '1' and decision.reason == 'printing_group'
    assert decision.card_id == 'en:sv04-159' and decision.printing_ids == ('en:sv04-159', 'en:PPS5-PAR-159')


SINGLES = [
    ('Comfey', '77', 'en:swsh9-77', 'swsh9'),
    ('Charmander', '9', 'en:xy12-9', 'xy12'),
    ('Charmeleon', '24', 'en:base1-24', 'base1'),
]


@pytest.mark.parametrize('name, number, card_id, set_id', SINGLES)
def test_single_candidates_answer_the_same_with_the_guard_on_or_off(name, number, card_id, set_id):
    rows = [_card(card_id, name, number, 'en', set_id), _card('en:base1-4', 'Charmander', '4', 'en', 'base1')]
    vectors = [_unit(1, 0), _unit(0, 1)]
    outcomes = []
    for guard in (False, True):
        decision = _gate(rows, vectors, vectors[0], name=name, number=number, guard=guard)
        assert decision.answered and decision.card_id == card_id
        outcomes.append((decision.stage, decision.card_id, decision.reason))
    assert outcomes[0] == outcomes[1] == ('1', card_id, 'same')


def test_a_single_text_card_that_needs_artwork_still_goes_to_stage_1b_with_the_guard_on():
    # The vector leads with another card by 0.03, so the text card goes to artwork, as before.
    rows = [_card('en:base1-24', 'Charmeleon', '24', 'en', 'base1'), _card('en:base1-4', 'Pidgey', '4', 'en', 'base1')]
    vectors = [_unit(1, 0), _unit(0.2, 0, 0.9798)]
    for guard in (False, True):
        decision = _gate(rows, vectors, CAPSULE_TEXT, name='Charmeleon', number='24', guard=guard)
        assert decision.stage == '1b_pending' and decision.card_id == 'en:base1-24'


def test_same_card_id_collapsed_by_duplicate_normalization_still_answers():
    rows = [
        _card('base1-25', 'Pikachu', '25', 'en', 'base1'),
        _card('en:base1-25', 'Pikachu', '25', 'en', 'base1'),
        _card('en:base1-4', 'Charmander', '4', 'en', 'base1'),
    ]
    vector = _unit(1, 0)
    vectors = [vector, vector, _unit(0, 1)]
    for guard in (False, True):
        decision = _gate(rows, vectors, vector, name='Pikachu', number='25', stage1b=False, guard=guard)
        assert decision.answered and decision.card_id == 'en:base1-25' and decision.reason == 'same'


def test_printing_twins_needs_two_rows_with_one_name_language_and_number():
    left = {'name': 'Pikachu', 'language': 'en', 'collector_number': '25'}
    assert not printing_twins([left])
    assert printing_twins([left, {**left, 'id': 'en:base1-25'}])
    assert not printing_twins([left, {**left, 'collector_number': '26'}])
    assert not printing_twins([left, {**left, 'language': 'ja'}])
    assert not printing_twins([left, {**left, 'name': 'Raichu'}])
