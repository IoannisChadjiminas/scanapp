"""The phone's raw number reads (PokeSingle #161): accepted, sanitized, and repaired against the catalogue.

A candidate never picks a card. It only becomes a number when the catalogue holds that number (with its
set total, or a prefixed code) for a card whose name also agrees with the phone's name, and the vector or
the artwork still has to agree afterwards.
"""
import json
import sqlite3

import pytest

from app.config import Settings
from app.recognition.client_text import MAX_BYTES, number_candidates, parse_client_text
from app.recognition.stage1_gate import (GateOptions, collapse_hits, load_catalogue, lookup, resolve_number,
                                        text_number_candidates)

CARDS = [
    ('en:sv02-204', 'Marill', '204', '204/193', 'en', 'sv02'),
    ('en:sv03-205', 'Scizor', '205', '205/197', 'en', 'sv03'),
    ('en:sv01-210', 'Drowzee', '210', '210/198', 'en', 'sv01'),
    ('ja:SM9-065', 'Dragonite', '065', '065/095', 'ja', 'SM9'),
    ('en:swsh9-013', 'Shaymin V', '013', '013/172', 'en', 'swsh9'),
    ('en:swsh10tg-TG05', 'Gardevoir', 'TG05', 'TG05/TG30', 'en', 'swsh10tg'),
    ('en:sv02-193', 'Pikachu', '193', '193/193', 'en', 'sv02'),
    ('en:base1-24', 'Charmeleon', '24', '24/102', 'en', 'base1'),
]
ON = GateOptions(number_repair=True)


@pytest.fixture(scope='module')
def catalogue():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE cards (id TEXT, name TEXT, view_title TEXT, collector_number TEXT, '
                 'printed_collector_number TEXT, language TEXT, set_id TEXT, image_path TEXT)')
    conn.executemany('INSERT INTO cards VALUES (?,?,NULL,?,?,?,?,?)', [(*row, f'{row[0]}.jpg') for row in CARDS])
    return load_catalogue(conn)


def entry(text, conf=0.5, region='footer'):
    return {'text': text, 'conf': conf, 'region': region}


def body(**extra):
    return {'v': 1, 'engine': 'mlkit-latin', 'name': 'Scizor', 'number': None, **extra}


# --- validation --------------------------------------------------------------------------------

def test_candidates_are_accepted_in_order_and_do_not_drop_the_hint():
    raw = json.dumps(body(number_candidates=[entry('205197', 0.9), entry('205/19)', None, 'corner_left')]))
    hint, reason = parse_client_text(raw)
    assert reason == 'ok' and hint.number_candidates == ('205197', '205/19)') and hint.number is None


def test_a_hint_with_only_candidates_is_not_empty_and_one_without_anything_is():
    hint, reason = parse_client_text(json.dumps({'v': 1, 'engine': 'mlkit-latin', 'number_candidates': [entry('205197')]}))
    assert reason == 'ok' and hint.name is None and hint.number_candidates == ('205197',)
    assert parse_client_text(json.dumps({'v': 1, 'engine': 'mlkit-latin', 'number_candidates': []}))[1] == 'empty'


def test_bad_entries_are_dropped_not_the_whole_hint():
    value = [entry('205197'), {'text': 'x' * 17, 'conf': 0.5, 'region': 'footer'},
             {'text': '1/2', 'conf': 2, 'region': 'footer'}, {'text': '1/2', 'conf': 0.5, 'region': 'sky'},
             {'text': '1/2', 'conf': 0.5, 'region': 'footer', 'extra': 1}]
    assert number_candidates(value) == ('205197',)
    more = [{'text': 5, 'conf': 0.5, 'region': 'footer'}, {'text': '1\n2', 'conf': 0.5, 'region': 'footer'},
            'garbage', entry('205197'), entry('013T2', None, 'corner_right')]
    assert number_candidates(more) == ('205197', '013T2')
    assert number_candidates([entry('  '), entry('205197'), entry('205197')]) == ('205197',)
    assert number_candidates('205197') == () and number_candidates(None) == ()
    assert number_candidates([entry(str(n) + '/10') for n in range(20)]) == tuple(f'{n}/10' for n in range(5))


def test_five_candidates_with_a_long_name_fit_the_limit():
    big = body(name='N' * 64, number_candidates=[entry('0123456789/12345', 0.123456, 'corner_right')] * 5 +
               [entry(f'{n}234567/{n}2345') for n in range(5)])
    raw = json.dumps(big)
    assert len(raw.encode()) <= MAX_BYTES and MAX_BYTES >= 1280
    assert parse_client_text(raw)[1] == 'ok'


def test_config_switch_and_defaults():
    settings = Settings(_env_file=None)
    assert settings.app_client_number_candidates is True and settings.stage1_number_repair is True
    # Stage 1 itself stays off by code default, so the repair changes nothing until it is turned on.
    assert settings.stage1_early_exit is False


# --- repair against the catalogue ----------------------------------------------------------------

@pytest.mark.parametrize(('name', 'candidates', 'expected_number', 'expected_card'), [
    ('Scizor', ['205197'], '205/197', 'en:sv03-205'),                   # slash not read
    ('Shaymin V', ['013T2'], '013/172', 'en:swsh9-013'),                # slash read as T, "17" lost
    ('Marill', ['204/19)'], '204/193', 'en:sv02-204'),                  # total cut short
    ('Marill', ['2o4193-'], '204/193', 'en:sv02-204'),                  # confusable digit, no slash, trailing junk
    ('Dragonite', ['o65/095'], '065/095', 'ja:SM9-065'),                # o is a zero
    ('Gardevoir', ['#TGO5'], 'TG05', 'en:swsh10tg-TG05'),               # prefix code
    ('Scizor', ['999/999', '205197'], '205/197', 'en:sv03-205'),        # the first usable one wins, in order
])
def test_real_a55_misreads_are_repaired_when_the_catalogue_holds_them(catalogue, name, candidates, expected_number, expected_card):
    by_key, _by_id, bare = catalogue
    number, used = resolve_number(name, None, tuple(candidates), None, by_key, ON)
    assert number.replace('/095', '/95') == expected_number.replace('/095', '/95') or number == expected_number
    assert used in candidates
    assert [c['id'] for c in collapse_hits(lookup(by_key, name, number, None, ON), bare)] == [expected_card]


def test_a_valid_phone_number_always_wins_and_candidates_are_ignored(catalogue):
    by_key = catalogue[0]
    assert resolve_number('Scizor', '205/197', ('204193',), None, by_key, ON) == ('205/197', None)


def test_an_invalid_candidate_selects_nothing(catalogue):
    by_key = catalogue[0]
    for candidate in ('999/999', '205198', '20', 'ABC', '1234567890123456', '205/777'):
        assert resolve_number('Scizor', None, (candidate,), None, by_key, ON) == (None, None)


def test_a_candidate_never_picks_a_card_without_a_matching_name(catalogue):
    by_key = catalogue[0]
    assert resolve_number('Pikachu', None, ('205197',), None, by_key, ON) == (None, None)  # 205/197 is Scizor
    assert resolve_number(None, None, ('205197',), None, by_key, ON) == (None, None)
    assert resolve_number('Seizor-less', None, ('205197',), None, by_key, ON) == (None, None)


def test_a_bare_numerator_is_not_a_number(catalogue):
    by_key = catalogue[0]
    # Lone digits are attack damage or a year, never a collector number, even next to the right name.
    assert resolve_number('Scizor', None, ('205',), None, by_key, ON) == (None, None)


def test_the_repair_is_off_without_its_flag(catalogue):
    by_key = catalogue[0]
    assert resolve_number('Scizor', None, ('205197',), None, by_key, GateOptions()) == (None, None)


def test_candidates_come_from_the_sent_text_only_when_no_valid_number_was_sent():
    raw = json.dumps(body(number_candidates=[entry('205197')]))
    assert text_number_candidates(raw) == ('205197',)
    assert text_number_candidates(json.dumps(body(number='205/197', number_candidates=[entry('205197')]))) == ()
    assert text_number_candidates('not json') == () and text_number_candidates(None) == ()
