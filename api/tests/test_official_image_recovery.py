"""Official reference acquisition must prove printing identity, not URL shape."""
import sys
from pathlib import Path

import pytest
from bootstrap.catalogue import parse_tpc_collector

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from discover_official_missing_images import english_urls
from verify_recovered_references import identity_agrees


def fraction(number='001', denominator='078'):
    return f'&nbsp;{number}&nbsp;/&nbsp;{denominator}&nbsp;'


def logo(code='SV1S', alt='SV1S'):
    return f'<img src="/assets/images/card/regulation_logo_1/{code}.gif" alt="{alt}" />'


def test_numeric_denominator_uses_official_set_logo():
    assert parse_tpc_collector(logo() + fraction()) == ('001', 'SV1S')


def test_numeric_denominator_never_becomes_set_code():
    assert parse_tpc_collector(fraction()) is None


def test_promo_explicit_set_code_stays_supported():
    assert parse_tpc_collector(fraction('142', 'SV-P')) == ('142', 'SV-P')


def test_logo_promo_disagreement_is_rejected():
    assert parse_tpc_collector(logo() + fraction('142', 'SV-P')) is None


def test_logo_alt_disagreement_is_rejected():
    assert parse_tpc_collector(logo(alt='SV1V') + fraction()) is None


def test_two_set_logos_are_ambiguous():
    assert parse_tpc_collector(logo() + logo('SV1V', 'SV1V') + fraction()) is None


def test_two_collectors_are_ambiguous():
    assert parse_tpc_collector(logo() + fraction() + fraction('002')) is None


@pytest.mark.parametrize('sid,number,code,token', [
    ('swsh12.5gg', 'GG44', 'SWSH12PT5GG', 'GG44'),
    ('swsh12tg', 'TG25', 'SWSH12TG', 'TG25'),
    ('swsh4.5sv', 'SV001', 'SWSH45SV', 'SV001'),
    ('sm3.5', '53', 'SM35', '53'),
    ('swshp', 'SWSH001', 'SWSHP', 'SWSH001'),
    ('smp', 'SM01', 'SMP', 'SM01'),
    ('svp', '001', 'SVP', '1'),
    ('mep', '031', 'MEP', '31'),
])
def test_official_asset_candidates(sid, number, code, token):
    assert english_urls({'set_id': sid, 'collector_number': number})[0].endswith(f'/{code}/{code}_EN_{token}.png')


@pytest.mark.parametrize('sid,number', [('SV2a', '205'), ('B2a', '001'), ('sv01', '../5'), ('sv01', '')])
def test_unknown_or_unsafe_asset_identity_not_guessed(sid, number):
    assert english_urls({'set_id': sid, 'collector_number': number}) == []


@pytest.mark.parametrize('names,numbers,expected', [
    ([('Mewtwo VSTAR', .99)], [('GG44/GG70', .99)], True),
    ([('Mewtwo VSTAR', .99)], [('GG43/GG70', .99)], False),
    ([('Mewtwo VSTAR', .99)], [('GG70/GG44', .99)], False),
    ([('Mewtwo VSTAR', .5)], [('GG44/GG70', .99)], False),
    ([('Mew VSTAR', .99)], [('GG44/GG70', .99)], False),
    ([('Mewtwo VSTAR', .99)], [('GG44', .99)], False),
])
def test_reference_ocr_does_not_accept_missing_or_conflicting_identity(names, numbers, expected):
    assert identity_agrees({'name': 'Mewtwo VSTAR', 'collector_number': 'GG44'}, names, numbers) is expected
