from __future__ import annotations

import pytest

from app.recognition import rank
from app.recognition.ocr import OcrHit
from app.recognition.rank import (accepted_collector_numbers, extract_collector_candidates,
                                  number_matches_identifiers)


@pytest.fixture(params=[True, False], ids=['flag_on', 'flag_off'])
def flag(request, monkeypatch):
    monkeypatch.setattr(rank, 'set_code_prefix_enabled', lambda: request.param)
    return request.param


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(rank, 'set_code_prefix_enabled', lambda: True)


@pytest.fixture
def off(monkeypatch):
    monkeypatch.setattr(rank, 'set_code_prefix_enabled', lambda: False)


def _texts(raw: str) -> list[str]:
    return [h.text for h in extract_collector_candidates([], hits=[OcrHit(raw, .95, 'collector')])]


def _verdict(raw: str, card: dict) -> bool | None:
    hits = extract_collector_candidates([], hits=[OcrHit(raw, .95, 'collector')])
    return number_matches_identifiers(hits, accepted_collector_numbers(card))


def _card(number: str, set_id: str, total: int | None = None) -> dict:
    return {'collector_number': number, 'set_id': set_id, 'set_total': total}


@pytest.mark.parametrize(('raw', 'number'), [('30C077/128', '077'), ('30C095/128', '095'),
                                             ('30CEN 077/128', '077'), ('30CEN077/128', '077'),
                                             ('SV077/198', '077')])
def test_glued_set_code_is_stripped_when_on(on, raw, number):
    assert _texts(raw) == [f'{number}/' + raw.split('/')[1]]
    assert _verdict(raw, _card(number, 'cel30', 128 if '30C' in raw else 198)) is True


def test_glued_set_code_is_unchanged_when_off(off):
    assert _texts('30C077/128') != ['077/128']
    assert _verdict('30C077/128', _card('077', 'cel30', 128)) is False


def test_glued_set_code_keeps_wrong_number_and_denominator_conflicting(on):
    card = _card('077', 'cel30', 128)
    assert _verdict('30C078/128', card) is False      # a different real number
    assert _verdict('30C077/129', card) is False      # same number, other total
    assert _verdict('128', card) is False
    assert _verdict('30C128/128', card) is False


def test_denominator_only_collision_is_not_agreement(on):
    # The old bug read 30C077/128 as 128. A card numbered 128 must not agree with it now.
    assert _verdict('30C077/128', _card('128', 'cel30', 128)) is False


@pytest.mark.parametrize('raw', ['30c077/128', '3OC077/128', '30C 077/128x', 'X30C077/128',
                                 '130C077/128', '30D077/128'])
def test_lowercase_noisy_or_unknown_prefixes_are_not_stripped(on, raw):
    assert '077/128' not in _texts(raw)


def test_sv_prefix_only_strips_a_three_digit_number_before_the_slash(on):
    assert _texts('SV2a173/165') == ['173/165']          # existing set-code rule, unchanged

def test_sv_rule_changes_nothing_for_non_three_digit_forms(monkeypatch):
    for raw in ['SV12/122', 'SV2173/165', 'SV2a173/165', 'SV1/122']:
        monkeypatch.setattr(rank, 'set_code_prefix_enabled', lambda: False)
        before = _texts(raw)
        monkeypatch.setattr(rank, 'set_code_prefix_enabled', lambda: True)
        assert _texts(raw) == before


def test_bare_fraction_still_matches(flag):
    assert _verdict('078/128', _card('078', 'cel30', 128)) is True
    assert _verdict('077/128', _card('078', 'cel30', 128)) is False


def test_promo_prefix_equal_to_set_id_matches_when_on(on):
    assert _verdict('MEP078', _card('078', 'mep')) is True
    assert _verdict('MEP078', _card('78', 'mep')) is True
    assert _verdict('MEP078', _card('078', 'en:mep')) is True
    assert _verdict('SWSH050', _card('050', 'swshp')) is True


def test_promo_prefix_is_not_accepted_when_off(off):
    assert _verdict('MEP078', _card('078', 'mep')) is False


def test_svp_is_unchanged_in_both_modes(flag):
    assert _verdict('SVP045', _card('045', 'svp')) is True


def test_promo_prefix_never_creates_agreement_from_unrelated_numbers(on):
    assert _verdict('MEP079', _card('078', 'mep')) is False          # other number
    assert _verdict('MEP078', _card('078', 'sv1')) is False          # other set
    assert _verdict('MEP078', _card('078', 'svp')) is False          # other promo set
    assert _verdict('SVP078', _card('078', 'mep')) is False
    assert _verdict('XYZ078', _card('078', 'mep')) is False          # arbitrary letters
    assert _verdict('M078', _card('078', 'mep')) is False            # truncated prefix stays a conflict
    assert 'MEP078' not in accepted_collector_numbers(_card('MEP-078', 'mep'))


def test_bare_promo_number_matches_either_way(flag):
    assert _verdict('078', _card('078', 'mep')) is True
