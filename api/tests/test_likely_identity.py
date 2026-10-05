import pytest

from app.recognition.identity import likely_identity_agrees
from app.recognition.ocr import OcrHit
from app.recognition.confidence import confidence_payload


def row(**overrides):
    return dict(card_id='umbreon', name='Umbreon VMAX', visual_score=.770661,
        artwork_score=.709755, retrieved_via=['full_card','artwork'], language='en',
        collector_number='215', printed_collector_number='215/203', **overrides)


@pytest.mark.parametrize('change,name,confidence,number,language,expected', [
    ({}, 'UmbreonVMAX', .994, None, ('en',), True),
    ({}, 'Pikachu', .99, None, ('en',), False),
    ({}, 'UmbreonVMAX', .60, None, ('en',), False),
    ({}, 'UmbreonVMAX', .99, '214/203', ('en',), False),
    ({}, 'UmbreonVMAX', .99, 'SM215', ('en',), False),
    ({}, 'UmbreonVMAX', .99, None, ('ja',), False),
    ({'retrieved_via':['ocr_metadata']}, 'UmbreonVMAX', .99, None, ('en',), False),
    ({'visual_score':.4}, 'UmbreonVMAX', .99, None, ('en',), False),
    ({'artwork_score':.4}, 'UmbreonVMAX', .99, None, ('en',), False),
])
def test_likely_identity_requires_corroboration_without_printing_proof(change, name, confidence, number, language, expected):
    candidate = row()
    candidate.update(change)
    assert likely_identity_agrees(candidate, ocr_name=name, name_confidence=confidence,
        numbers=[OcrHit(number,.99,'collector')] if number else [], languages=language,
        min_visual=.70) is expected


def test_evidence_never_reports_cosine_as_probability():
    confidence = confidence_payload([row()], status='printing_ambiguous',
        name_confidence=.994, numbers=[], framing_unverified=True, quality_retake=False,
        min_visual=.78, structured_identity=False, likely_identity=True)
    assert confidence.probability is None and confidence.calibration_status == 'uncalibrated'
    assert confidence.visual_similarity == pytest.approx(.770661)
    assert confidence.visual_margin is None
    assert confidence.identity == 'likely' and confidence.printing == 'ambiguous'
    assert confidence.finish == 'unconfirmed' and confidence.requires_confirmation
    assert not confidence.retake_recommended
