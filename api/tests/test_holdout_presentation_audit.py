import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('holdout_audit',
    Path(__file__).resolve().parents[1] / 'scripts/audit_photo_holdout.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


@pytest.mark.parametrize('identifier,expected', [
    ('en:base1-58',True), ('base1-58',True), ('en:base4-87',False),
    ('ja:base1-58',False), ('extra-pikachu',False),
])
def test_holdout_score_only_merges_legacy_english_provider_alias(identifier,expected):
    assert audit.correct({'card_id':identifier},{'expected_id':'en:base1-58'}) is expected


def test_internal_top_is_not_used_as_displayed_match_correctness():
    case = dict(name='photo',expected_id='en:base1-58',truth_in_artwork_pilot=True,
        provenance=dict(language='en',layout='standard_frame',page_url='https://example.com/card'),
        after=dict(top_id='en:base1-58',status='uncertain',best_match={'card_id':'en:base4-87'},
                   alternatives=[{'card_id':'base1-58'}],match_state='likely',
                   full_shortlist_printing_recall=True,artwork_shortlist_printing_recall=True,
                   identity_evidence={},ocr={},query_size=[500,700],frame_selection={}))
    row = audit.evaluate(case,'after')
    assert not row['best_match_correct']
    assert row['correct_in_best_or_alternatives']
    assert not row['automatic_wrong_match']
    case['after']['status'] = 'matched'
    assert audit.evaluate(case,'after')['automatic_wrong_match']


def test_no_match_is_not_counted_as_success_or_a_wrong_displayed_card():
    row = dict(best_match_correct=False,best_match_id=None,correct_in_best_or_alternatives=False,
               status='retake',automatic_wrong_match=False)
    metrics = audit.counts([row])
    assert metrics['no_best_match'] == 1
    assert metrics['best_match_correct'] == metrics['best_match_wrong'] == 0
