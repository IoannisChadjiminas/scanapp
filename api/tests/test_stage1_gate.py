"""Stage 1 agrees only when the vector and the text name one card, by a clear margin."""
import base64
import json
import sqlite3

import numpy as np

from app.config import Settings
from app.recognition.client_embedding import parse_client_embedding
from app.recognition.stage1_gate import decide, load_catalogue


def _unit(*values: float) -> np.ndarray:
    vector = np.zeros(8, np.float32)
    vector[:len(values)] = values
    vector /= np.linalg.norm(vector)
    return vector


def _catalogue(rows: list[tuple]) -> tuple:
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute(
        'CREATE TABLE cards (id TEXT, name TEXT, view_title TEXT, collector_number TEXT, '
        'printed_collector_number TEXT, language TEXT, set_id TEXT, image_path TEXT)')
    conn.executemany('INSERT INTO cards VALUES (?,?,?,?,?,?,?,?)', rows)
    return load_catalogue(conn)


def _card(card_id: str, name: str, number: str, language: str, set_id: str) -> tuple:
    return (card_id, name, None, number, number, language, set_id, None)


def _gate(rows, embeddings, query, *, name, number, language=None, quad=True, stage1b=False, label=False):
    by_key, by_id, bare = _catalogue(rows)
    return decide(
        query, np.stack(embeddings), [row[0] for row in rows],
        by_key=by_key, by_id=by_id, bare_ids=bare,
        name=name, number=number, language=language, quad_ok=quad, stage1b=stage1b, label=label)


def test_flags_default_off_and_confirmation_stays_on():
    fields = Settings.model_fields
    assert fields['stage1_early_exit'].default is False
    assert fields['stage1_background_check'].default is False
    assert fields['stage1_check_phone_inputs'].default is False
    assert fields['stage1b_text_verify'].default is False
    assert fields['stage1_require_confirmation'].default is True
    assert fields['stage1_sample_rate'].default == 1.0


def test_same_card_answers_at_the_margin_and_abstains_just_under():
    pikachu = _unit(1, 0, 0)
    clear = _unit(0.98, 0.199, 0)
    close = _unit(0.99, 0.141067, 0)
    rows = [
        _card('en:base1-25', 'Pikachu', '25/102', 'en', 'base1'),
        _card('en:base1-4', 'Charmander', '4/102', 'en', 'base1'),
    ]
    answered = _gate(rows, [pikachu, clear], pikachu, name='Pikachu', number='25/102')
    assert answered.answered and answered.stage == '1' and answered.card_id == 'en:base1-25'
    assert answered.reason == 'same' and answered.margin >= 0.02
    short = _gate(rows, [pikachu, close], pikachu, name='Pikachu', number='25/102')
    assert not short.answered and short.reason == 'low_margin' and short.margin < 0.02


def test_duplicate_ids_collapse_and_the_english_id_wins():
    vector = _unit(1, 0, 0)
    other = _unit(0, 1, 0)
    rows = [
        _card('base1-25', 'Pikachu', '25/102', 'en', 'base1'),
        _card('en:base1-25', 'Pikachu', '25/102', 'en', 'base1'),
        _card('en:base1-4', 'Charmander', '4/102', 'en', 'base1'),
    ]
    decision = _gate(rows, [vector, vector, other], vector, name='Pikachu', number='25/102')
    assert decision.answered and decision.card_id == 'en:base1-25' and decision.reason == 'same'


def test_language_twin_lets_the_text_card_win():
    english = _unit(1, 0, 0)
    japanese = _unit(0.9, 0.43589, 0)
    other = _unit(0, 0, 1)
    rows = [
        _card('en:base1-25', 'Pikachu', '25/102', 'en', 'base1'),
        _card('ja:base1-58', 'Pikachu', '58/165', 'ja', 'base1'),
        _card('en:base1-4', 'Charmander', '4/102', 'en', 'base1'),
    ]
    decision = _gate(rows, [english, japanese, other], japanese, name='Pikachu', number='25/102')
    assert decision.answered and decision.reason == 'twin' and decision.card_id == 'en:base1-25'


def test_set_total_conflict_blocks_a_twin():
    english = _unit(1, 0, 0)
    japanese = _unit(0.9, 0.43589, 0)
    rows = [
        _card('en:base1-25', 'Pikachu', '25/102', 'en', 'base1'),
        _card('ja:base1-25', 'Pikachu', '25/165', 'ja', 'base1'),
    ]
    decision = _gate(rows, [english, japanese], japanese, name='Pikachu', number='25/102')
    assert not decision.answered and decision.reason == 'vector_disagree'


def test_vector_disagrees_and_missing_fields_abstain():
    pikachu = _unit(1, 0, 0)
    charmander = _unit(0, 1, 0)
    rows = [
        _card('en:base1-25', 'Pikachu', '25/102', 'en', 'base1'),
        _card('en:base1-4', 'Charmander', '4/102', 'en', 'base1'),
    ]
    disagree = _gate(rows, [pikachu, charmander], pikachu, name='Charmander', number='4/102')
    assert not disagree.answered and disagree.reason == 'vector_disagree'
    missing = _gate(rows, [pikachu, charmander], pikachu, name=None, number=None)
    assert missing.reason == 'no_unique_text'
    no_quad = _gate(rows, [pikachu, charmander], pikachu, name='Pikachu', number='25/102', quad=False)
    assert no_quad.reason == 'no_quad'
    no_vector = decide(
        None, np.stack([pikachu, charmander]), ['en:base1-25', 'en:base1-4'],
        by_key={}, by_id={}, bare_ids=set(), name='Pikachu', number='25/102',
        language=None, quad_ok=True)
    assert no_vector.reason == 'no_embedding'


def test_label_without_a_language_keeps_the_single_english_card():
    english = _unit(1, 0, 0)
    japanese = _unit(0, 1, 0)
    rows = [
        _card('en:base1-25', 'Pikachu', '25/102', 'en', 'base1'),
        _card('ja:base1-25', 'Pikachu', '25/102', 'ja', 'base1'),
    ]
    kept = _gate(rows, [english, japanese], english, name='Pikachu', number='25/102', label=True)
    assert kept.answered and kept.card_id == 'en:base1-25'
    both = _gate(rows, [english, japanese], english, name='Pikachu', number='25/102', label=False)
    assert not both.answered and both.reason == 'ambiguous_text'


def test_stage1b_refuses_a_same_language_card_ahead_by_005():
    leader = _unit(1, 0, 0)
    text = _unit(0.90, 0.43589, 0)
    rows = [
        _card('en:base4-91', 'Pikachu', '91/102', 'en', 'base4'),
        _card('en:base1-62', 'Pikachu', '62/102', 'en', 'base1'),
    ]
    blocked = _gate(rows, [leader, text], leader, name='Pikachu', number='62/102', stage1b=True)
    assert not blocked.answered and blocked.reason == 'visual_contradiction' and blocked.stage is None


def test_stage1b_pending_when_the_leader_is_a_language_twin():
    japanese = _unit(1, 0, 0)
    english = _unit(0.9, 0.43589, 0)
    neighbour = _unit(0.999, 0.04471, 0)
    rows = [
        _card('en:base1-25', 'Pikachu', '25/102', 'en', 'base1'),
        _card('ja:base1-58', 'Pikachu', '58/165', 'ja', 'base1'),
        _card('en:base1-4', 'Charmander', '4/102', 'en', 'base1'),
    ]
    decision = _gate(
        rows, [english, japanese, neighbour], japanese,
        name='Pikachu', number='25/102', stage1b=True)
    assert not decision.answered and decision.stage == '1b_pending' and decision.card_id == 'en:base1-25'


def test_wrong_model_is_rejected_before_the_gate():
    payload = json.dumps({
        'model': 'aaaaaaaaaaaa/coreml-pal8',
        'vector': base64.b64encode(np.zeros(384, dtype='<f2').tobytes()).decode(),
    })
    vector, reason = parse_client_embedding(payload)
    assert vector is None and reason == 'bad_model'


def test_a_unit_vector_of_the_known_model_parses():
    values = np.zeros(384, np.float32)
    values[0] = 1
    payload = json.dumps({
        'model': '2ddf6ec79e37/coreml-pal8',
        'vector': base64.b64encode(values.astype('<f2').tobytes()).decode(),
    })
    vector, reason = parse_client_embedding(payload)
    assert reason == 'ok' and vector is not None and abs(float(np.linalg.norm(vector)) - 1) < 1e-3


def test_android_litert_model_id_is_accepted_but_other_runtime_ids_are_not():
    values = np.zeros(384, np.float32)
    values[0] = 1
    vector = base64.b64encode(values.astype('<f2').tobytes()).decode()
    android = json.dumps({'model': '2ddf6ec79e37/litert-fp16', 'vector': vector})
    unknown = json.dumps({'model': '2ddf6ec79e37/onnx-fp16', 'vector': vector})

    parsed, reason = parse_client_embedding(android)
    assert reason == 'ok' and parsed is not None
    parsed, reason = parse_client_embedding(unknown)
    assert parsed is None and reason == 'bad_model'
