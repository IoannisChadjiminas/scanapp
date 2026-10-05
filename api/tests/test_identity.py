import pytest

from app.recognition.identity import structured_identity_agrees
from app.recognition.ocr import OcrHit


def agrees(hits, **overrides):
    args = dict(ocr_name='Charizard ex',name_confidence=.99,numbers=hits,languages=('en',))
    args.update(overrides)
    return structured_identity_agrees(dict(name='Charizard ex',collector_number='199',language='en'),**args)


def test_two_structured_fields_support_review():
    assert agrees([OcrHit('199/165',.99,'collector')])


@pytest.mark.parametrize('hits', [[],[OcrHit('199/165',None,'collector')],
    [OcrHit('199/165',.99,'unknown')],[OcrHit('199',.99,'collector')],
    [OcrHit('199/165',.99,'collector'),OcrHit('200/165',.99,'collector')]])
def test_missing_unlocated_bare_or_contradictory_numbers_do_not_rescue(hits):
    assert not agrees(hits)


@pytest.mark.parametrize('overrides',[{'ocr_name':None},{'name_confidence':.6},
                                    {'ocr_name':'Pikachu'},{'languages':('ja',)}])
def test_missing_weak_or_contradictory_name_language_do_not_rescue(overrides):
    assert not agrees([OcrHit('199/165',.99,'collector')],**overrides)
