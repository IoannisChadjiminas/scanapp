"""Generic bounded issuer recovery and literal-number safety contracts."""
from dataclasses import replace

import pytest

from app.recognition.grading import (
    LabelLine, brand_company, parse_label as literal_label, _within_one_edit, recover_fuzzy_company,
)


def parse_label(lines):
    return recover_fuzzy_company(literal_label(lines), [lines])


def structured(brand='BECKETTO', confidence=.99):
    return [LabelLine('2024 POKEMON', .99, (.2, .10, .6, .15)),
            LabelLine('MINT', .99, (.7, .25, .9, .30)),
            LabelLine('9', .99, (.73, .18, .85, .24)),
            LabelLine('12345678', .99, (.65, .35, .95, .40)),
            LabelLine(brand, confidence, (.05, .30, .18, .38))]


@pytest.mark.parametrize('word', ['BECKETTO', 'BECKETTS', 'BECKET', 'BECKFTT', 'BEECKETT'])
def test_one_edit_long_issuer_is_flagged_and_digits_stay_literal(word):
    lines = structured(word)
    result = parse_label(lines)
    assert result.company == 'beckett'
    assert result.company_source == 'label_ocr_fuzzy'
    assert result.requires_confirmation is True
    assert result.grade == 9
    assert result.certification_number == '12345678'
    assert result.label_text == [line.text for line in lines]
    assert 'grading_company_fuzzy_match_requires_confirmation' in result.warnings
    assert brand_company(word) is None


@pytest.mark.parametrize('word', ['BECKETT TEAM', 'BECKETTSHOP', 'BEKET', 'PS4', 'PSAA', 'SCGC',
                                'CGO', 'TAGG', 'AGE', 'AG5', 'ACE SPEC', 'TAG TEAM', 'BECKET7'])
def test_short_brands_extra_words_and_multiple_edits_are_not_corrected(word):
    assert parse_label(structured(word)).company is None


@pytest.mark.parametrize('index', [0, 1, 3])
def test_each_independent_label_marker_is_required(index):
    lines = structured()
    del lines[index]
    assert parse_label(lines).company is None


@pytest.mark.parametrize('confidence', [.89, None, float('nan'), float('inf')])
def test_low_or_invalid_brand_confidence_is_not_recovered(confidence):
    assert parse_label(structured(confidence=confidence)).company is None


@pytest.mark.parametrize('box', [None, (0, .8, .2, .9), (-.1, .3, .2, .4),
                               (.1, .3, .1, .4), (0, .3, .2, float('nan'))])
def test_brand_must_be_located_within_label_not_below_on_card(box):
    lines = structured()
    lines[-1] = replace(lines[-1], box=box)
    assert parse_label(lines).company is None


def test_near_word_and_a_digit_without_label_context_are_not_a_slab():
    result = parse_label([structured()[-1], structured()[2]])
    assert result.company is None and result.grade is None and result.slab_detected is None


def test_literal_conflicting_issuer_is_not_overridden_by_fuzzy_recovery():
    lines = [*structured(), LabelLine('PSA', .99, (.3, .01, .4, .05))]
    prior = literal_label(lines)
    assert parse_label(lines) == prior
    assert prior.company == 'psa'


def test_literal_same_issuer_keeps_literal_source():
    result = parse_label([*structured(), LabelLine('BECKETT', .99, (.3, .01, .4, .05))])
    assert result.company_source == 'label_ocr'
    assert 'grading_company_fuzzy_match_requires_confirmation' not in result.warnings


def test_certificate_conflict_prevents_recovery_and_grade_selection():
    result = parse_label([*structured(), LabelLine('87654321', .99, (.1, .5, .3, .55))])
    assert result.company is None and result.grade is None
    assert 'certification_number_ambiguous' in result.warnings


@pytest.mark.parametrize('digit', ['O', 'g', 'B', 'lO'])
def test_unreadable_grade_is_not_fuzzy_corrected(digit):
    lines = structured()
    lines[2] = replace(lines[2], text=digit)
    assert parse_label(lines).grade is None


def test_fuzzy_company_does_not_invent_missing_certificate_or_grade():
    lines = structured()
    lines[3] = replace(lines[3], text='1234567B')
    assert parse_label(lines).company is None
    lines = structured()
    del lines[2]
    result = parse_label(lines)
    assert result.company == 'beckett' and result.grade is None


@pytest.mark.parametrize(('word', 'company'), [
    ('CERTIFIEDGUARANTYCOMPANY', 'cgc'),
    ('AUTOMATED GRADING SYSTENS', 'ags'),
    ('PROFESSIONAL SPORTS AUTHENTICAT0R', None),
    ('TECHNICAL AUTHENTICATION & GRADIN', 'tag'),
])
def test_long_names_and_spacing_are_generic_not_photo_specific(word, company):
    assert parse_label(structured(word)).company == company


@pytest.mark.parametrize(('a', 'b', 'expected'), [
    ('BECKETT', 'BECKETT', True), ('BEKET', 'BECKETT', False),
    ('BECKETT', 'BECKET', True), ('BECKETT', 'BEECKETT', True),
    ('BECKETT', 'BECKXTT', True), ('BECKETT', 'BECKETTTT', False),
])
def test_bounded_edit_operation(a, b, expected):
    assert _within_one_edit(a, b) is expected


def test_fuzzy_parser_is_not_used_during_literal_interpretation():
    assert literal_label(structured()).company is None


def test_company_only_recovery_preserves_every_other_output():
    lines = structured()
    prior = literal_label(lines).model_copy(update={
        'subgrades': {'centering': 8.5, 'edges': 9.0}, 'tag_score': 950,
        'qualifiers': ['OC'],
    })
    result = recover_fuzzy_company(prior, [lines])
    before, after = prior.model_dump(), result.model_dump()
    for field in before.keys() - {'company', 'company_source', 'warnings', 'label_text', 'requires_confirmation'}:
        assert after[field] == before[field], field
    assert result.company == 'beckett'


@pytest.mark.parametrize('warning', ['conflicting_overall_grades', 'conflicting_grading_companies',
    'conflicting_condition_labels', 'certification_number_ambiguous',
    'certification_number_unreadable_or_ambiguous', 'condition_grade_contradiction', 'grading_ocr_failed'])
def test_company_recovery_never_overrides_prior_conflicts(warning):
    prior = literal_label(structured()).model_copy(update={'warnings': [warning]})
    assert recover_fuzzy_company(prior, [structured()]) == prior


def test_different_holder_certificate_is_not_transferred():
    lines = structured()
    lines[3] = replace(lines[3], text='98765432')
    prior = literal_label(structured())
    assert recover_fuzzy_company(prior, [lines]) == prior


def test_conflicting_observed_grade_is_not_transferred():
    lines = structured()
    lines[2] = replace(lines[2], text='8')
    prior = literal_label(structured())
    assert recover_fuzzy_company(prior, [lines]) == prior


def test_two_distinct_fuzzy_issuers_abstain():
    lines = structured()
    prior = literal_label(lines)
    assert recover_fuzzy_company(prior, [lines, structured('ROBOGRADIN')]) == prior


def test_read_grading_keeps_legacy_passes_and_fills_only_company(monkeypatch):
    from PIL import Image
    from app.recognition.ocr import CardOcr
    reader = CardOcr.__new__(CardOcr)
    reads = []
    reader._grading_lines = lambda image: reads.append(image.size) or structured()
    monkeypatch.setattr('app.recognition.label_vision.label_panels', lambda image: [])
    monkeypatch.setattr('app.recognition.label_vision.text_label_panel', lambda *a, **kw: None)
    result = reader.read_grading(Image.new('RGB', (600, 1000)))
    assert len(reads) == 2  # Initial and established logo-only retry, not fuzzy early return.
    prior = literal_label(structured())
    assert result.company == 'beckett' and result.company_source == 'label_ocr_fuzzy'
    assert result.grade == prior.grade and result.subgrades == prior.subgrades
    assert result.certification_number == prior.certification_number


def test_unused_subgrade_conflict_cannot_erase_consistent_company_only_evidence():
    lines = structured()
    ambiguous = [*lines, LabelLine('8.5', .99, (.75, .31, .85, .34))]
    assert 'conflicting_overall_grades' in literal_label(ambiguous).warnings
    prior = literal_label(lines)
    result = recover_fuzzy_company(prior, [lines, ambiguous])
    assert result.company == 'beckett'
    assert result.grade == prior.grade and result.subgrades == prior.subgrades
    assert result.certification_number == prior.certification_number
    assert recover_fuzzy_company(prior, [ambiguous]) == prior
