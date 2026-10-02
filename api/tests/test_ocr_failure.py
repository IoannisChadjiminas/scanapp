from __future__ import annotations

from PIL import Image

from app.recognition.ocr import CardOcr
from app.recognition.rank import rerank
from types import SimpleNamespace
import numpy as np
import pytest


def test_ocr_read_failure_returns_failed_result(monkeypatch) -> None:  # noqa: ANN001
    from PIL import Image

    from app.recognition.ocr import CardOcr as Real

    def boom(self, image):  # noqa: ANN001, ARG001
        raise RuntimeError("nope")

    monkeypatch.setattr(Real, "_run", boom)
    ocr = Real.__new__(Real)
    result = Real.read(ocr, Image.new("RGB", (64, 64)))
    assert result.failed is True
    ranked = rerank(
        [
            {
                "card_id": "a",
                "name": "Pikachu",
                "collector_number": "25",
                "visual_score": 0.8,
                "combined_score": 0.8,
            }
        ],
        result.name_text,
        [],
        result.failed,
    )
    assert ranked[0]["card_id"] == "a"


def test_readable_fraction_skips_extra_ocr(monkeypatch):
    calls=[]
    observations=iter([(['Charizard ex'],[.99]),(['199/165'],[.99])])
    def read(self,image):
        calls.append(image.size)
        return next(observations)
    monkeypatch.setattr(CardOcr,'_run',read)
    result=CardOcr.read(CardOcr.__new__(CardOcr),Image.new('RGB',(600,825)))
    assert not result.failed and len(calls) == 2


def test_missing_name_does_not_trigger_collector_retry(monkeypatch):
    observations=iter([(['TRAINER'],[.99]),(['no fraction'],[.99])])
    monkeypatch.setattr(CardOcr,'_run',lambda self,image:next(observations))
    result=CardOcr.read(CardOcr.__new__(CardOcr),Image.new('RGB',(600,825)))
    assert not result.failed


@pytest.mark.parametrize('scores', [[.99,.40], np.array([.99,.40])])
def test_empty_ocr_entry_does_not_shift_confidence_to_later_text(scores):
    ocr=CardOcr.__new__(CardOcr)
    ocr.engine=lambda pixels:SimpleNamespace(txts=['','Charizard ex'],scores=scores)
    texts,confidences=ocr._run(Image.new('RGB',(300,400)))
    assert texts == ['Charizard ex'] and confidences == [.40]


@pytest.mark.parametrize('first_number', ['215/203', 'SM215', '215 / 203'])
def test_small_frame_readable_identifier_never_overwritten(monkeypatch, first_number):
    observations = iter([(['Umbreon VMAX'], [.99]), ([first_number], [.40])])
    monkeypatch.setattr(CardOcr, '_run', lambda self, image: next(observations))
    result = CardOcr.read(CardOcr.__new__(CardOcr), Image.new('RGB', (249,330)))
    assert not result.failed and not result.collector_retry_used
    assert result.hits[-1].confidence == .40


@pytest.mark.parametrize('retry_fails', [False, True])
def test_small_frame_collector_retry_is_bounded_and_keeps_first_read(monkeypatch, retry_fails):
    calls = []
    def read(self, image):
        calls.append(image.size)
        if len(calls) == 1:
            return ['Umbreon VMAX'], [.994]
        if len(calls) == 2:
            return ['215'], [.60]
        if retry_fails:
            raise RuntimeError('optional retry failed')
        return ['2N', '215/203'], [.99, .90]
    monkeypatch.setattr(CardOcr, '_run', read)
    result = CardOcr.read(CardOcr.__new__(CardOcr), Image.new('RGB', (249,330)))
    assert not result.failed and result.collector_retry_used and len(calls) == 3
    assert calls[-1][0] == 747
    assert result.hits[1].text == '215' and result.hits[1].confidence == .60
    assert result.collector_text == ('215' if retry_fails else '215/203')
    assert '2N' not in [h.text for h in result.hits]
    assert result.collector_retry_contributed is not retry_fails


def test_collector_retry_cannot_import_weak_structured_read(monkeypatch):
    observations = iter([(['Blastoise ex'], [.90]), (['200'], [.99]), (['200/1'], [.68])])
    monkeypatch.setattr(CardOcr, '_run', lambda self, image: next(observations))
    result = CardOcr.read(CardOcr.__new__(CardOcr), Image.new('RGB', (249,330)))
    assert result.collector_retry_used and not result.collector_retry_contributed
    assert result.collector_text == '200'


def test_small_frame_weak_name_does_not_spend_retry_or_gain_confidence(monkeypatch):
    observations = iter([(['Umbreon VMAX'], [.60]), ([], [])])
    monkeypatch.setattr(CardOcr, '_run', lambda self, image: next(observations))
    result = CardOcr.read(CardOcr.__new__(CardOcr), Image.new('RGB', (249,330)))
    assert not result.failed and not result.collector_retry_used
    assert result.hits[0].confidence == .60
