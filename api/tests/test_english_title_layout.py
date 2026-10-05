"""Identity must not come from printed mechanic badges or clipped rules."""
import pytest
from app.recognition.ocr import pick_confident_name, pick_name_line


@pytest.mark.parametrize('badge', ['STRIKE', 'FUSION', 'RAPID', 'SINGLE', 'FUSION STRIKE', 'Rapid Strike', 'Single Strike'])
def test_mechanic_badge_does_not_replace_title_before_stage(badge):
    assert pick_confident_name(['180', 'Example V', 'HP', 'BASIC', badge],
                               [.99, .95, .99, .99, .99]) == 'Example V'


@pytest.mark.parametrize('rule', ['Evolves', 'Evolvest', 'Evolves tr', 'Evolves from'])
def test_split_evolution_rule_is_not_a_title(rule):
    assert pick_name_line(['360', 'Example ex', 'STAGE2', 'HP', rule, 'Previousmon']) == 'Example ex'
    assert pick_name_line([rule, 'Previousmon']) is None


def test_merged_stage_instruction_does_not_replace_title():
    assert pick_confident_name(['STAGEI Evolves tr', 'Example', '70 HP'], [.96, .99, .98]) == 'Example'


def test_clipped_split_badge_without_visible_title_stays_neutral():
    assert pick_name_line(['180', 'HP', 'FUSION', 'ASTRIKE']) is None
    assert pick_name_line(['Example V', 'BASIC', 'FUSION', 'ASTRIKE']) == 'Example V'


def test_complete_evolution_rule_does_not_consume_next_title():
    assert pick_name_line(['Evolves from Previousmon', 'Example']) == 'Example'


def test_title_and_background_anchor_preserved():
    assert pick_name_line(['BACKGROUND SHOP', 'STAGE2', 'Example ex']) == 'Example ex'
    assert pick_name_line(['Eevee', '90 HP']) == 'Eevee'
    assert pick_name_line(['Single Strike Style Mustard']) == 'Single Strike Style Mustard'
    assert pick_name_line(['Rapid Strike Urshifu VMAX']) == 'Rapid Strike Urshifu VMAX'
