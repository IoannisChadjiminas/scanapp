import pytest

from app.recognition.ocr import OcrHit
from app.recognition.rank import artwork_evidence_compatible


def compatible(*, name=None, confidence=0., hits=(), language='en', languages=()):
    return artwork_evidence_compatible(dict(name='Pikachu', language=language,
        collector_number='58/102', printed_collector_number=''), ocr_name=name,
        name_confidence=confidence, numbers=list(hits), languages=languages)


def test_geometry_cannot_override_known_language_or_strong_name_conflict():
    assert not compatible(language='ja',languages=('en',))
    assert not compatible(name='Raichu',confidence=.99)
    assert compatible(name='Pikachu',confidence=.99,languages=('en',))


@pytest.mark.parametrize('hit', [OcrHit('87/130',.99,'collector'),OcrHit('SV999',.99,'collector')])
def test_structured_collector_conflict_blocks_artwork_rescue(hit):
    assert not compatible(hits=[hit])


@pytest.mark.parametrize('hit', [OcrHit('87/130',.5,'collector'),OcrHit('87/130',None,'collector'),
    OcrHit('87/130',.99,'unknown'),OcrHit('6',.99,'collector')])
def test_weak_unknown_or_unstructured_evidence_is_neutral_for_artwork(hit):
    assert compatible(hits=[hit])


def test_missing_or_short_noise_name_does_not_veto_geometry():
    assert compatible() and compatible(name='UY',confidence=.99)
    assert compatible(name='Copyright Nintendo Creatures GAME FREAK',confidence=0.)
    assert compatible(hits=[OcrHit('58/102',.99,'collector')])
