from __future__ import annotations

import pytest

from app.recognition import rank
from app.recognition.ocr import OcrHit
from app.recognition.rank import (accepted_collector_numbers, number_matches_identifiers,
                                  promo_bare_number_agrees, rerank)


@pytest.fixture(params=[True, False], ids=['near_on', 'near_off'])
def near(request, monkeypatch):
    monkeypatch.setattr(rank, 'promo_prefix_near_enabled', lambda: request.param)
    monkeypatch.setattr(rank, 'set_code_prefix_enabled', lambda: False)
    return request.param


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(rank, 'promo_prefix_near_enabled', lambda: True)
    monkeypatch.setattr(rank, 'set_code_prefix_enabled', lambda: False)


@pytest.fixture
def off(monkeypatch):
    monkeypatch.setattr(rank, 'promo_prefix_near_enabled', lambda: False)
    monkeypatch.setattr(rank, 'set_code_prefix_enabled', lambda: False)


def _verdict(raw: str, card: dict) -> bool | None:
    hits = [OcrHit(raw, .95, 'collector')]
    return number_matches_identifiers(hits, accepted_collector_numbers(card))


def _card(number: str, set_id: str, name: str = 'Toxel', card_id: str | None = None,
          total: int | None = None) -> dict:
    return {'card_id': card_id or f'en:{set_id}-{number}', 'name': name, 'collector_number': number,
            'set_id': set_id, 'set_total': total, 'visual_score': .8, 'language': 'en'}


MEP_078 = _card('078', 'mep', card_id='en:mep-078')


def test_mp078_agrees_with_mep78_when_on(on):
    assert _verdict('MP078', _card('78', 'mep')) is True
    assert _verdict('MP078', MEP_078) is True
    assert _verdict('ME078', MEP_078) is True
    assert _verdict('EP078', MEP_078) is True            # one letter missing from MEP
    assert _verdict('MPE078', MEP_078) is True           # one swapped pair


def test_mp078_conflicts_when_off(off):
    assert _verdict('MP078', MEP_078) is False


def test_mp078_is_conflict_on_a_non_promo_card(on):
    assert _verdict('MP078', _card('078', 'sv1', card_id='en:sv1-078')) is False


def test_mp078_is_conflict_on_a_different_number(on):
    assert _verdict('MP079', MEP_078) is False
    assert _verdict('MP78', MEP_078) is False            # the number must be 3 digits


def test_prefix_two_letters_off_still_conflicts(on):
    assert _verdict('MB078', MEP_078) is False
    assert _verdict('M078', MEP_078) is False
    assert _verdict('XYZ078', MEP_078) is False


def test_svp_and_other_non_table_sets_never_take_the_near_rule(on):
    # SVP is printed with the SV letters of the main set, so one letter off would
    # collide with SV045 shiny-vault collectors. It stays outside the near table.
    assert _verdict('SV045', _card('045', 'svp', card_id='en:svp-045')) is False


def test_near_rule_is_not_a_set_fallback_for_non_table_promos(on):
    assert _verdict('MP078', _card('078', 'wp')) is False


def test_bare_078_matches_when_name_and_number_name_one_promo_card(on):
    assert _verdict('078', MEP_078) is True
    assert promo_bare_number_agrees('Toxel', MEP_078, [MEP_078]) is True


def test_bare_078_with_a_different_name_conflicts(on):
    assert promo_bare_number_agrees('Pikachu', MEP_078, [MEP_078]) is False
    visual = [dict(MEP_078, visual_score=.85)]
    ranked = rerank(visual, 'Pikachu', [OcrHit('078', .95, 'collector')], False,
                    name_confidence=.95, require_confident_ocr=True)
    assert ranked[0]['collector_conflict'] is True


def test_bare_078_with_no_name_conflicts(on):
    assert promo_bare_number_agrees(None, MEP_078, [MEP_078]) is False


def test_ambiguous_name_with_two_promo_cards_conflicts_for_a_bare_number(on):
    other = _card('078', 'swshp', card_id='en:swshp-078')
    assert promo_bare_number_agrees('Toxel', MEP_078, [MEP_078, other]) is False
    ranked = rerank([dict(MEP_078, visual_score=.85), dict(other, visual_score=.84)], 'Toxel',
                    [OcrHit('078', .95, 'collector')], False, name_confidence=.95,
                    require_confident_ocr=True)
    # Neither promo card is proven by the bare 078: both keep a collector conflict.
    assert [row['collector_conflict'] for row in ranked] == [True, True]


def test_bare_rule_leaves_flag_off_unchanged(off):
    # Flag off: bare numbers keep the existing behaviour (no name gate).
    assert _verdict('078', MEP_078) is True
    assert _verdict('078', _card('078', 'mep', name='Pikachu')) is True


def test_near_rule_does_not_change_the_canonical_number_when_off(near):
    if rank.promo_prefix_near_enabled():
        assert 'MEP078' in accepted_collector_numbers(MEP_078)
    else:
        assert 'MEP078' not in accepted_collector_numbers(MEP_078)
