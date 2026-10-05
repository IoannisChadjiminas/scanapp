import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('catalogue_completion_inventory',
    Path(__file__).resolve().parents[1]/'scripts/catalogue_completion_inventory.py')
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


@pytest.mark.parametrize('value,expected', [
    ('015','15'), ('95a','95a'), ('95b','95b'), ('SV041','SV041'),
    ('17/30','17/30'), ('E17','E17'), ('Z17','Z17'), ('',''), ('MET','MET'),
])
def test_collector_preserves_printing_tokens(value, expected):
    assert inventory.normalized_collector(value) == expected


def test_prefix_and_same_image_do_not_erase_variant_difference():
    left = dict(language='en', set_id='base1', name='Alakazam', collector_number='1',
                remote_image_url='https://example/image', variants_json='{"firstEdition": true}')
    right = dict(left, variants_json='{"firstEdition": false}')
    assert inventory.identity_differences(left, right) == ['variants_json']


def test_json_order_is_not_a_variant_difference():
    assert inventory.identity_differences({'variants_json':'{"holo": true, "normal": false}'},
                                         {'variants_json':'{"normal": false, "holo": true}'}) == []


def test_scope_requires_explicit_approval_and_language_agreement():
    card = dict(id='en:go-015', language='en',set_id='go',name='Squirtle',collector_number='015')
    product = dict(expansion='Japanese-GO', name='Squirtle (s10b 015)From 0,02 €',card_id=card['id'])
    assert inventory.local_candidate_check(card,product,{}) == ['expansion_scope_unapproved']
    scope = {'Japanese-GO':dict(verification='approved_exact_scope',language='ja',set_id='S10b')}
    assert inventory.local_candidate_check(card,product,scope) == ['language_or_set_conflict']


def test_suffix_and_owner_collisions_block_candidate():
    card = dict(id='en:aq-95a',language='en',set_id='aq',name='Trainer',collector_number='95a')
    product = dict(expansion='Aquapolis',name='Trainer (AQ 95b)',card_id='en:aq-95b')
    registry = {'Aquapolis':dict(verification='approved_exact_scope',language='en',set_id='aq')}
    assert inventory.local_candidate_check(card,product,registry) == ['collector_conflict','owner_conflict']


def test_unnumbered_is_not_invented():
    assert inventory.numbered_title('Metal Energy (s8a)') is None
