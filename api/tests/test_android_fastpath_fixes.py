"""Android fast-path fixes: number repair, constrained fuzzy name, stage 1b on the server's own frame.

Every fix is default off. None of them can pick a card by itself: they only offer the ordinary
lookup more spellings, and the vector or artwork still has to agree afterwards.
"""
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import numpy as np
import pytest

from app.config import Settings
from app.recognition import stage1_answer
from app.recognition.stage1_answer import evaluate_stage1
from app.recognition.stage1_gate import GateOptions, collapse_hits, load_catalogue, lookup
from app.recognition.stage1_text_repair import edit_distance, fuzzy_name_ok, number_variants

REPO = Path(__file__).resolve().parents[2]

CARDS = [
    # id, name, collector number, printed number, language, set id
    ('en:sv02-204', 'Marill', '204', '204/193', 'en', 'sv02'),
    ('en:sv03-205', 'Scizor', '205', '205/197', 'en', 'sv03'),
    ('en:sv03-203', 'Tinkaton', '203', '203/197', 'en', 'sv03'),
    ('en:sv01-210', 'Drowzee', '210', '210/198', 'en', 'sv01'),
    ('ja:SM9-065', 'Dragonite', '065', '065/095', 'ja', 'SM9'),
    ('ja:SM9-038', 'Gengar & Mimikyu GX', '038', '038/095', 'ja', 'SM9'),
    ('en:swsh9-013', 'Shaymin V', '013', '013/172', 'en', 'swsh9'),
    ('en:swsh10tg-TG05', 'Gardevoir', 'TG05', 'TG05/TG30', 'en', 'swsh10tg'),
    ('en:base1-63', 'Mew', '63', '63/102', 'en', 'base1'),
    ('en:base1-20', 'Mewtwo', '20', '20/102', 'en', 'base1'),
    ('en:xy1-20', 'Abra', '20', '20/146', 'en', 'xy1'),
    ('en:sv02-193', 'Marill', '193', '193/193', 'en', 'sv02'),
]
ON = GateOptions(number_repair=True, fuzzy_name=True)


@pytest.fixture(scope='module')
def catalogue():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE cards (id TEXT, name TEXT, view_title TEXT, collector_number TEXT, '
                 'printed_collector_number TEXT, language TEXT, set_id TEXT, image_path TEXT)')
    conn.executemany('INSERT INTO cards VALUES (?,?,NULL,?,?,?,?,?)', [(*row, f'{row[0]}.jpg') for row in CARDS])
    return load_catalogue(conn)


def ids(catalogue, name, number, options=ON):
    by_key, _by_id, bare = catalogue
    return sorted(card['id'] for card in collapse_hits(lookup(by_key, name, number, None, options), bare))


def test_every_fix_defaults_off_and_only_staging_compose_may_turn_it_on():
    fields = Settings.model_fields
    assert not any(fields[key].default for key in ('stage1_number_repair', 'stage1_fuzzy_name', 'stage1b_server_frame'))
    assert GateOptions.from_settings(Settings(_env_file=None)) == GateOptions()
    staging = (REPO / 'compose.dokploy.yaml').read_text()
    for key in ('STAGE1_NUMBER_REPAIR', 'STAGE1_FUZZY_NAME', 'STAGE1B_SERVER_FRAME'):
        assert f'{key}: ${{{key}:-' in staging
        for production in REPO.glob('compose*prod*.yaml'):
            assert key not in production.read_text()


@pytest.mark.parametrize(('phone', 'expected'), [
    ('o65/095', ['065/95']),          # o to 0 inside the number
    ('O65/O95', ['065/95']),
    ('205197', ['205/197']),          # the slash was not read
    ('2o4193-', ['204/193']),         # confusable digit, missing slash, trailing junk
    ('#TGO5', ['TG05']),              # prefix kept as letters, the O is a digit
])
def test_number_variants_repair_only_inside_the_number(catalogue, phone, expected):
    assert number_variants(phone, catalogue[0])[:1] == expected


def test_a_cut_short_total_and_a_slash_read_as_t_need_the_catalogue_to_hold_the_total(catalogue):
    by_key = catalogue[0]
    assert '204/193' in number_variants('204/19)', by_key)       # total cut short
    assert '013/172' in number_variants('013T2', by_key)         # slash read as T, "17" lost
    assert number_variants('999/193', by_key) == []              # not a number the catalogue has
    assert number_variants('204/777', by_key) == []              # the catalogue has no such total
    assert number_variants('205198', by_key) == []               # 205/198 is not a printed pair
    assert number_variants('1234567890123456789012', by_key) == []
    assert number_variants('ABC', by_key) == []


def test_repair_selects_nothing_without_the_name_and_changes_no_exact_hit(catalogue):
    assert ids(catalogue, 'Marill', '2o4193-') == ['en:sv02-204']
    assert ids(catalogue, 'Scizor', '205197') == ['en:sv03-205']
    assert ids(catalogue, 'Dragonite', 'o65/095') == ['ja:SM9-065']
    assert ids(catalogue, 'Gardevoir', '#TGO5') == ['en:swsh10tg-TG05']
    assert ids(catalogue, 'Shaymin V', '013T2') == ['en:swsh9-013']
    # A repaired number with a different card's name finds nothing: the number never picks a card.
    assert ids(catalogue, 'Pikachu', '205197') == []
    assert ids(catalogue, 'Tinkaton', '205197') == []
    # An exact hit is returned as it is, even though a repair would have found something else.
    assert ids(catalogue, 'Scizor', '205/197') == ['en:sv03-205']
    assert ids(catalogue, 'Scizor', '205197', GateOptions()) == []
    assert ids(catalogue, 'Marill', '2o4193-', GateOptions(fuzzy_name=True)) == []


@pytest.mark.parametrize(('phone', 'number', 'expected'), [
    ('Seizor', '205/197', ['en:sv03-205']),
    ('DrowzZee', '210/198', ['en:sv01-210']),
    ('Mavill', '204/193', ['en:sv02-204']),
    ('GENGAR & MIMIK YU GX', '038/095', ['ja:SM9-038']),
    ('Gengar &Mimikyu GX', '038/95', ['ja:SM9-038']),
])
def test_fuzzy_name_after_the_number_and_total_narrow_the_candidates(catalogue, phone, number, expected):
    assert ids(catalogue, phone, number) == expected


def test_a_fuzzy_name_alone_never_selects_a_card(catalogue):
    assert ids(catalogue, 'Seizor', '') == []
    assert ids(catalogue, 'Seizor', None) == []
    assert ids(catalogue, 'Seizor', '206/197') == []          # wrong number: no card has this name
    assert ids(catalogue, 'Seizor', '205/197', GateOptions()) == ['en:sv03-205']  # the shipped 0.72 rule already did this
    assert ids(catalogue, 'Seizor', '203/197') == []          # the card at 203 is Tinkaton
    assert ids(catalogue, 'Mew', '20/102') == []              # Mewtwo is not Mew


def test_fuzzy_name_distances():
    assert fuzzy_name_ok('Seizor', 'Scizor') and fuzzy_name_ok('Flabebe', 'Flabébé') and fuzzy_name_ok('PIKACHU& ZEKROM GX', 'Pikachu & Zekrom GX')
    assert fuzzy_name_ok('Charizrd ex', 'Charizard ex')
    assert not fuzzy_name_ok('Raichu', 'Pikachu') and not fuzzy_name_ok('Mew', 'Mewtwo')
    assert not fuzzy_name_ok('ピカチュウ', 'ピカチュウV')  # CJK names are never fuzzy
    assert edit_distance('kitten', 'sitting', 5) == 3 and edit_distance('abcdef', 'uvwxyz', 2) == 3


# --- stage 1b on the server's own frame -------------------------------------------------------

def _settings(**extra):
    return SimpleNamespace(stage1b_text_verify=True, stage1b_server_frame=True, stage1_set_totals=False,
                           stage1_normalize_duplicates=False, stage1_printing_groups=False, stage1_promo_numbers=False,
                           stage1_diagnostics=False, stage1_number_repair=False, stage1_fuzzy_name=False, **extra)


def _runtime(card_ids, vectors):
    return SimpleNamespace(snapshot=SimpleNamespace(embeddings=np.stack(vectors), card_ids=card_ids),
                           artwork_verifier=object())


def _unit(*values):
    vector = np.zeros(384, np.float32)
    vector[:len(values)] = values
    return vector / np.linalg.norm(vector)


@pytest.fixture
def frame(monkeypatch):
    calls = {'frame': 0, 'artwork': 0, 'quad': 'unset'}
    state = {'vector': _unit(1, 0, 0), 'rect': np.zeros((4, 2), np.float32), 'inliers': 40}

    def fake_frame(_runtime, _bytes):
        calls['frame'] += 1
        return None if state['vector'] is None else (state['rect'], state['vector'])

    def fake_artwork(_runtime, _bytes, quad, _card_id, _path, server_rect=None):
        calls['artwork'] += 1
        calls['quad'] = quad
        calls['rect'] = server_rect
        return state['inliers']

    monkeypatch.setattr(stage1_answer, '_server_frame_vector', fake_frame)
    monkeypatch.setattr(stage1_answer, '_artwork', fake_artwork)
    return calls, state


def _catalog():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE cards (id TEXT, name TEXT, view_title TEXT, collector_number TEXT, '
                 'printed_collector_number TEXT, language TEXT, set_id TEXT, image_path TEXT)')
    conn.executemany('INSERT INTO cards VALUES (?,?,NULL,?,?,?,?,?)', [(*row, f'{row[0]}.jpg') for row in CARDS])
    return conn


def _evaluate(settings, runtime, text, embedding=None, quad=None):
    return evaluate_stage1(settings=settings, runtime=runtime, catalog=_catalog(), client_text=text,
                           client_embedding=embedding, card_quad=quad, image_bytes=b'photo')


TEXT = json.dumps({'v': 1, 'engine': 'mlkit-latin', 'name': 'Scizor', 'number': '205/197'})
CARD_IDS = ['en:sv03-205', 'en:sv03-203', 'en:sv01-210']


def test_server_frame_answers_stage_1b_after_the_artwork_check(frame):
    calls, _state = frame
    decision = _evaluate(_settings(), _runtime(CARD_IDS, [_unit(1, 0, 0), _unit(0, 1, 0), _unit(0, 0, 1)]), TEXT)
    assert decision.answered and decision.stage == '1b' and decision.card_id == 'en:sv03-205'
    assert decision.reason == 'server_frame_artwork' and decision.inliers == 40
    assert calls['frame'] == 1 and calls['artwork'] == 1 and calls['rect'] is not None


def test_server_frame_never_answers_stage_1_and_still_needs_the_artwork(frame):
    calls, state = frame
    state['inliers'] = None
    decision = _evaluate(_settings(), _runtime(CARD_IDS, [_unit(1, 0, 0), _unit(0, 1, 0), _unit(0, 0, 1)]), TEXT)
    assert not decision.answered and decision.reason == 'artwork_miss' and decision.card_id is None


def test_server_frame_keeps_the_visual_contradiction_rule(frame):
    calls, state = frame
    state['vector'] = _unit(0, 1, 0)  # the server's frame looks like Tinkaton, not Scizor
    decision = _evaluate(_settings(), _runtime(CARD_IDS, [_unit(1, 0, 0), _unit(0, 1, 0), _unit(0, 0, 1)]), TEXT)
    assert not decision.answered and decision.reason == 'visual_contradiction' and calls['artwork'] == 0


def test_server_frame_does_no_work_unless_the_text_names_exactly_one_card(frame):
    calls, _state = frame
    runtime = _runtime(CARD_IDS, [_unit(1, 0, 0), _unit(0, 1, 0), _unit(0, 0, 1)])
    for text, reason in [
            (json.dumps({'v': 1, 'engine': 'mlkit-latin', 'name': 'Pikachu', 'number': '205/197'}), 'no_unique_text'),
            (json.dumps({'v': 1, 'engine': 'mlkit-latin', 'name': 'Scizor'}), 'no_unique_text'),
            (json.dumps({'v': 1, 'engine': 'mlkit-latin', 'number': '205/197'}), 'no_unique_text'),
            (None, 'no_embedding')]:
        decision = _evaluate(_settings(), runtime, text)
        assert not decision.answered and decision.reason == reason
    assert calls['frame'] == 0 and calls['artwork'] == 0


def test_server_frame_abstains_when_no_frame_is_found(frame):
    calls, state = frame
    state['vector'] = None
    decision = _evaluate(_settings(), _runtime(CARD_IDS, [_unit(1, 0, 0), _unit(0, 1, 0), _unit(0, 0, 1)]), TEXT)
    assert not decision.answered and decision.reason == 'no_server_frame' and calls['artwork'] == 0


def test_server_frame_is_off_without_its_flag_or_stage_1b_and_never_overrides_a_phone_vector(frame):
    calls, _state = frame
    runtime = _runtime(CARD_IDS, [_unit(1, 0, 0), _unit(0, 1, 0), _unit(0, 0, 1)])
    off = _settings()
    off.stage1b_server_frame = False
    assert _evaluate(off, runtime, TEXT).reason == 'no_embedding'
    no_1b = _settings()
    no_1b.stage1b_text_verify = False
    assert _evaluate(no_1b, runtime, TEXT).reason == 'no_embedding'
    # A phone vector that is present but refused is not the "no vector" case: no server fallback.
    refused = _evaluate(_settings(), runtime, TEXT, embedding='{"model": "x", "vector": "y"}')
    assert not refused.answered and refused.reason != 'server_frame_artwork'
    assert calls['frame'] == 0 and calls['artwork'] == 0
