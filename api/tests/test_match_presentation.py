import copy

import pytest

from app.recognition.presentation import match_presentation
from app.schemas import PrintingReview


def card(cid='lead', **overrides):
    row = dict(card_id=cid, name='Pikachu', set_name='Base', collector_number='58',
        language='en', image_url='/lead.jpg', cardmarket_url='https://example.com/card',
        visual_score=.77, combined_score=.82, artwork_score=.72)
    row.update(overrides)
    return row


def review(*rows):
    return PrintingReview(reason='printing_not_proven', candidate_group_id='family',
        plausible_printings=rows, guidance='Choose the printing.')


@pytest.mark.parametrize('status,state', [('matched','matched'), ('uncertain','likely'),
                                        ('printing_ambiguous','likely')])
def test_explicit_best_match_is_same_lead_without_changing_ranking(status, state):
    ranked = [card(), card('other', set_name='Classic', collector_number='014')]
    before = copy.deepcopy(ranked)
    presentation = match_presentation(ranked, status=status, printing_review=None)
    assert presentation.best_match.card_id == 'lead'
    assert presentation.best_match.image_url == '/lead.jpg'
    assert presentation.match_state == state
    assert [c.card_id for c in presentation.alternatives] == ['other']
    assert ranked == before


@pytest.mark.parametrize('status', ['retake', 'no_match', 'failed'])
def test_abstention_never_fabricates_best_match(status):
    result = match_presentation([card()], status=status, printing_review=None)
    assert result.best_match is None and result.alternatives == []
    assert result.match_state == 'unavailable'


def test_no_catalogue_candidates_remains_explicitly_unavailable():
    assert match_presentation([], status='uncertain', printing_review=None).best_match is None


def test_legacy_printing_choices_can_supply_unscored_tentative_main_card():
    result = match_presentation([], status='printing_ambiguous', printing_review=review(card()))
    assert result.best_match.card_id == 'lead' and result.best_match.visual_score is None
    assert result.best_match.source == 'printing_review'
    assert result.match_state == 'tentative'


def test_all_printing_choices_retained_outside_top_k_without_fake_scores():
    lead = card()
    siblings = [card(f'sibling{i}', set_name=f'Set{i}', collector_number='014') for i in range(8)]
    allowed_fields = {'card_id','name','set_name','collector_number','language','image_url','cardmarket_url'}
    siblings = [{k:v for k,v in c.items() if k in allowed_fields} for c in siblings]
    result = match_presentation([lead], status='printing_ambiguous',
        printing_review=review(lead, *siblings))
    assert len(result.alternatives) == 8
    assert all(c.visual_score is None and c.combined_score is None for c in result.alternatives)
    assert all(c.source == 'printing_review' and c.selection_action == 'confirm' for c in result.alternatives)


def test_aliases_and_finishes_do_not_become_duplicate_cards():
    lead = card(cardmarket_variants=[{'url':'https://example.com/holo','label':'Holo'}])
    alias = card('alias')
    result = match_presentation([lead, alias], status='uncertain', printing_review=review(alias))
    assert result.alternatives == []
    assert result.best_match.cardmarket_variants[0].label == 'Holo'


def test_alternatives_filtered_bounded_and_feedback_contract_preserved():
    candidates = [card(), card('wrong-name', set_name='Bad1', strong_name_conflict=True),
        card('wrong-number', set_name='Bad2', structured_collector_conflict=True),
        card('wrong-language', set_name='Bad3', language_conflict=True),
        card('weak', set_name='Bad4', artwork_score=.4, visual_score=.4)]
    candidates += [card(f'other{i}', set_name=f'Other{i}') for i in range(10)]
    result = match_presentation(candidates, status='printing_ambiguous', printing_review=review(card()))
    assert [c.card_id for c in result.alternatives] == [f'other{i}' for i in range(5)]
    assert all(c.selection_action == 'correct' for c in result.alternatives)


def test_conflicting_lead_is_tentative_not_confirmed_identity():
    result = match_presentation([card(structured_collector_conflict=True)],
        status='uncertain', printing_review=None)
    assert result.match_state == 'tentative'
