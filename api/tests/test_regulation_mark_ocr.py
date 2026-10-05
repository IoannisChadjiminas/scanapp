import pytest

from app.recognition.metadata import MetadataCandidateIndex
from app.recognition.ocr import OcrHit
from app.recognition.printing import assess_printings
from app.recognition.rank import extract_collector_candidates, parse_collector, rerank


@pytest.mark.parametrize('text,number', [
    ('D201/202','201/202'), ('D 201/202','201/202'), ('d201 / 202','201/202'),
    ('E025/198','025/198'), ('F173/165AR','173/165'), ('G251/198','251/198'),
    ('H005/078','005/078'), ('I002/068','002/068'), ('J123/198','123/198'),
])
def test_regulation_mark_is_separate_from_numeric_fraction(text, number):
    result = extract_collector_candidates([number], hits=[OcrHit(text,.95546,'collector')])
    assert len(result) == 1
    assert result[0] == OcrHit(number,.95546,'collector')
    # Do not change the generic catalogue identifier parser.
    assert parse_collector('D201/202').prefix == 'D'


@pytest.mark.parametrize('text', ['TG05/030','GG25/070','SM183','SWSH051','SVP002',
                                 'D201','E005','A201/202','K201/202','GD201/202'])
def test_cleanup_does_not_strip_real_or_unknown_collector_namespaces(text):
    result = extract_collector_candidates([], hits=[OcrHit(text,.99,'collector')])
    assert [h.text for h in result] == [text]


@pytest.mark.parametrize('confidence,region', [(.40,'collector'), (None,'collector'), (.99,'unknown')])
def test_normalization_does_not_upgrade_evidence(confidence, region):
    result = extract_collector_candidates([], hits=[OcrHit('D201/202',confidence,region)])
    assert result == [OcrHit('201/202',confidence,region)]


def rows():
    # Slightly favor the wrong printing visually, as in the diagnosed photo.
    return [dict(card_id='209',id='209',name="Professor's Research (Professor Magnolia)",
        set_id='swsh1',set_name='Sword & Shield',collector_number='209',
        printed_collector_number='209/202',language='en',visual_score=.80045),
        dict(card_id='201',id='201',name="Professor's Research (Professor Magnolia)",
        set_id='swsh1',set_name='Sword & Shield',collector_number='201',
        printed_collector_number='201/202',language='en',visual_score=.79767)]


@pytest.mark.parametrize('text,expected', [('D201/202','201'), ('D209/202','209')])
def test_collector_evidence_selects_observed_printing_not_fixed_card(text, expected):
    numbers = extract_collector_candidates([], hits=[OcrHit(text,.95546,'collector')])
    ranked = rerank(rows(), "Professor's Research", numbers, False,
        detected_languages=('en',), name_confidence=.99984, require_confident_ocr=True)
    assert ranked[0]['card_id'] == expected
    assert not ranked[0]['structured_collector_conflict']
    index = MetadataCandidateIndex(rows(), indexed_ids={'201','209'})
    assert index.candidates(ocr_name="Professor's Research",name_confidence=.99984,
        numbers=numbers,languages=('en',)) == [expected]
    printing = assess_printings(ranked, family=rows(), hits=numbers,
        reference_incomplete=False, min_visual=.78, min_gap=.04, retake=False)
    assert not printing.ambiguous


def test_wrong_denominator_still_conflicts_and_cannot_resolve_printing():
    numbers = extract_collector_candidates([], hits=[OcrHit('D201/203',.99,'collector')])
    ranked = rerank(rows(), "Professor's Research", numbers, False,
        name_confidence=.99, require_confident_ocr=True)
    assert all(r['structured_collector_conflict'] for r in ranked)
    assert MetadataCandidateIndex(rows(),indexed_ids={'201','209'}).candidates(
        ocr_name="Professor's Research",name_confidence=.99,numbers=numbers,languages=('en',)) == []
    assert assess_printings(ranked,family=rows(),hits=numbers,reference_incomplete=False,
        min_visual=.78,min_gap=.04,retake=False).ambiguous
