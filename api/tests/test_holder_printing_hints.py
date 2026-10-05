from dataclasses import replace

import pytest

from app.recognition.grading import LabelLine
from app.recognition.holder_printing import holder_printing_hint
from app.recognition.ocr import OcrHit


def rows():
    return [dict(card_id='first', name='Example ex', language='en', set_id='SET',
                 set_name='Sample Expansion', collector_number='007', printed_collector_number='007/034'),
            dict(card_id='second', name='Example ex', language='en', set_id='OTHER',
                 set_name='Other Expansion', collector_number='007', printed_collector_number='007/034')]


def lines():
    return [LabelLine(t, .99, (.1, .1, .9, .2)) for t in
            ['2023 POKEMON SET', 'EXAMPLE EX - HOLO', '#007', 'GEM MT', 'PSA', '12345678']]


def hint(rs=None, ls=None, **options):
    defaults=dict(printed_name='Example ex', printed_name_confidence=.99,
                  printed_numbers=[], language='en')
    return holder_printing_hint(rs or rows(), lines() if ls is None else ls,
                               **(defaults | options))


def test_literal_set_and_number_only_orders_one_existing_choice():
    rs=rows()
    assert hint(rs)=='first'
    assert hint(list(reversed(rs)))=='first'
    assert rs[0]['card_id']=='first' and len(rs)==2


def test_full_set_name_with_fraction_can_be_on_same_label_line():
    ls=lines()
    ls[0]=replace(ls[0],text='2023 POKEMON')
    ls[2]=replace(ls[2],text='Sample Expansion #007/034')
    assert hint(ls=ls)=='first'


@pytest.mark.parametrize('missing',[0,1,2,3])
def test_independent_date_name_number_condition_required(missing):
    assert hint(ls=[l for i,l in enumerate(lines()) if i!=missing]) is None


def test_brand_watermark_without_date_number_cannot_supply_hint():
    assert hint(ls=lines()[3:]) is None


def test_brand_or_certificate_required():
    assert hint(ls=lines()[:4]) is None


@pytest.mark.parametrize('missing',[0,1,2,3])
@pytest.mark.parametrize('change',[{'confidence':.60},{'confidence':None},{'box':None}])
def test_weak_or_unlocated_fields_cannot_supply_hint(missing,change):
    ls=lines();ls[missing]=replace(ls[missing],**change)
    assert hint(ls=ls) is None


def test_multiple_number_fields_abstain():
    assert hint(ls=[*lines(),LabelLine('#042',.99,(.1,.2,.9,.3))]) is None


def test_two_matching_set_identities_abstain():
    assert hint(ls=[*lines(),LabelLine('OTHER',.99,(.1,.2,.9,.3))]) is None


def test_printed_fraction_contradiction_cannot_be_overridden_by_label():
    assert hint(printed_numbers=[OcrHit('007/099',.99,'collector')]) is None
    assert hint(printed_numbers=[OcrHit('042/034',.99,'collector')]) is None
    assert hint(printed_numbers=[OcrHit('007/034',.99,'collector')])=='first'


def test_holder_hint_cannot_supply_foreign_language_translation():
    assert hint(language='ja') is None
    assert hint(printed_name='サンプル',language='en') is None
    assert hint(printed_name_confidence=.70) is None


def test_partial_set_code_does_not_match():
    ls=lines();ls[0]=replace(ls[0],text='2023 POKEMON ASSET')
    assert hint(ls=ls) is None


def test_set_without_number_does_not_disambiguate_same_art():
    ls=lines();ls[2]=replace(ls[2],text='007/034')
    assert hint(ls=ls) is None


@pytest.mark.parametrize('proof', ['geometry', 'printed_metadata', 'none'])
@pytest.mark.parametrize('status', ['printing_ambiguous', 'uncertain', 'retake'])
def test_pipeline_hint_keeps_public_saved_ranking_and_confidence_consistent(monkeypatch, proof, status):
    from types import SimpleNamespace
    from PIL import Image
    from app.config import Settings
    from app.recognition import pipeline
    from app.recognition.ocr import OcrResult
    from app.schemas import Candidate, Coverage, GradingEvidence, MatchOption, OcrEvidence, PrintingReview, ScanResponse, ScanStatus
    ranked=[{**r, 'visual_score':.90, 'combined_score':.90, 'image_url':'/image'} for r in reversed(rows())]
    shown=ranked[:1]
    response=ScanResponse(id='test',status=ScanStatus(status),suggestions=[Candidate(**shown[0])],
        ocr=OcrEvidence(name_text='Example ex'),coverage=Coverage(cards=2,indexed=2,missing_images=0),
        timings_ms={},versions={},detected_language='en',best_match=MatchOption(**shown[0]),
        printing_review=PrintingReview(reason='shared_printing_identifier',
            candidate_group_id='group',reference_coverage_complete=True,
            plausible_printings=ranked,guidance='Confirm printing'))
    evidence={'local_artwork_matches':[{}] if proof=='geometry' else [],
              'framing_review_supported':proof=='printed_metadata'}
    saved=[]
    first=pipeline._ScanEvaluation(response,{'total_ms':1.},Image.new('RGB',(500,700)),
        lambda:saved.append((ranked[0]['card_id'],shown[0]['card_id'],dict(evidence))),
        ranked[0],OcrResult(name_text='Example ex'),[],('en',),.99,False,evidence,ranked,shown)
    monkeypatch.setattr(pipeline,'_recognize_bytes_once',lambda *a,**k:first)
    reader=SimpleNamespace(read_grading=lambda im:GradingEvidence(slab_detected=True,company='psa',grade=9),
                           read_holder_identity=lambda im:lines())
    runtime=SimpleNamespace(require=lambda:(None,None,reader))
    result=pipeline.recognize_bytes(b'test',settings=Settings(),runtime=runtime,
        catalog=None,results=None,session_id='test',skip_detect=True)
    preferred='first' if proof!='none' and status=='printing_ambiguous' else 'second'
    assert result.best_match.card_id==result.suggestions[0].card_id==preferred
    assert saved[0][0]==saved[0][1]==preferred
    assert result.status.value==status
    assert result.grading.grade==9 and result.grading.company=='psa'
    if preferred=='first':
        assert result.confidence.candidate_card_id=='first'
        assert result.confidence.probability is None and result.confidence.requires_confirmation
        assert result.confidence.printing=='ambiguous' and result.match_state=='likely'
        assert result.alternatives[0].card_id=='second'
        assert saved[0][2]['match_presentation']['best_match']['card_id']=='first'
        assert saved[0][2]['confidence']['candidate_card_id']=='first'
