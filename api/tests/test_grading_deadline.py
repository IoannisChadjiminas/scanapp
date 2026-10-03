from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore, Event
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from app.config import Settings
from app.recognition import pipeline, label_vision
from app.recognition.grading_control import GradingCancelled, grading_cancellation_scope
from app.recognition.grading_parallel import GradingJob
from app.recognition.ocr import OcrResult
from app.schemas import GradingEvidence, ScanStatus


def evaluation():
    response = SimpleNamespace(status=ScanStatus.uncertain, id='scan', versions={})
    saved = []
    item = pipeline._ScanEvaluation(response, {'total_ms': 1.}, Image.new('RGB', (60,90)),
        lambda: saved.append(response.grading.model_dump()), None, OcrResult(), [], ('en',), 0., False, {})
    return item, saved


def runtime(reader, worker):
    card = SimpleNamespace(read_grading=lambda image: pytest.fail('Must not fall back to serial OCR'))
    return SimpleNamespace(ocr=card, grading_ocr=SimpleNamespace(read_grading=reader),
        grading_executor=worker, grading_slots=BoundedSemaphore(1), require=lambda:(None,None,card))


def recognize(rt):
    return pipeline.recognize_bytes(b'test', settings=Settings(_env_file=None,
        grading_at_card_deadline=True), runtime=rt, catalog=None, results=None,
        session_id='test', skip_detect=True)


def test_pending_grade_returns_plain_ungraded_without_waiting_or_late_update(monkeypatch):
    entered, finish = Event(), Event()
    item, saved = evaluation()
    def grade(image):
        entered.set()
        assert finish.wait(2)
        return GradingEvidence(company='psa', grade=9, is_graded=True, grading_status='graded')
    def card(data, **kwargs):
        kwargs['_input_observer'](item.input_image)
        assert entered.wait(2)
        return item
    monkeypatch.setattr(pipeline, '_recognize_bytes_once', card)
    with ThreadPoolExecutor(max_workers=1) as worker:
        try:
            result = recognize(runtime(grade, worker))
            assert not finish.is_set()
            assert result.grading == GradingEvidence(is_graded=False, grading_status='ungraded')
            assert result.grading.warnings == [] and result.grading.source == 'none'
            assert result.timings_ms['grading_ready_at_card_deadline'] == 0
            assert saved == [result.grading.model_dump()]
        finally:
            finish.set()
    assert result.grading.company is None and result.grading.grade is None
    assert saved == [result.grading.model_dump()]


@pytest.mark.parametrize('evidence', [
    GradingEvidence(company='psa', grade=9, is_graded=True, grading_status='graded'),
    GradingEvidence(company='tag', slab_detected=True),
    GradingEvidence(warnings=['no_supported_grading_label_detected']),
])
def test_finished_grade_is_used_only_when_company_identified(monkeypatch, evidence):
    item, saved = evaluation()
    with ThreadPoolExecutor(max_workers=1) as worker:
        rt = runtime(lambda image:evidence, worker)
        def card(data, **kwargs):
            kwargs['_input_observer'](item.input_image)
            # Test-only synchronization ensures the label is done at deadline.
            kwargs_reader = rt.grading_slots
            assert kwargs_reader.acquire(timeout=2)
            kwargs_reader.release()
            return item
        monkeypatch.setattr(pipeline, '_recognize_bytes_once', card)
        result = recognize(rt)
    expected = evidence if evidence.company else GradingEvidence(is_graded=False, grading_status='ungraded')
    assert result.grading == expected and saved == [expected.model_dump()]
    assert result.timings_ms['grading_ready_at_card_deadline'] == 1


def test_failed_optional_grade_returns_plain_ungraded(monkeypatch):
    item, saved = evaluation()
    def fail(image):
        raise ValueError('OCR failed')
    with ThreadPoolExecutor(max_workers=1) as worker:
        rt = runtime(fail, worker)
        def card(data, **kwargs):
            kwargs['_input_observer'](item.input_image)
            assert rt.grading_slots.acquire(timeout=2)
            rt.grading_slots.release()
            return item
        monkeypatch.setattr(pipeline, '_recognize_bytes_once', card)
        result = recognize(rt)
    assert result.grading == GradingEvidence(is_graded=False, grading_status='ungraded')
    assert saved == [result.grading.model_dump()]


def test_busy_grader_never_queues_a_second_photo():
    entered, finish = Event(), Event()
    calls = []
    slots = BoundedSemaphore(1)
    def grade(image):
        calls.append(image.size)
        entered.set()
        assert finish.wait(2)
        return GradingEvidence()
    with ThreadPoolExecutor(max_workers=1) as worker:
        first = GradingJob(SimpleNamespace(read_grading=grade), worker, slots)
        second = GradingJob(SimpleNamespace(read_grading=grade), worker, slots)
        try:
            first.start(Image.new('RGB',(60,90)))
            assert entered.wait(2)
            first.stop()
            second.start(Image.new('RGB',(80,100)))
            second.start(Image.new('RGB',(80,100)))
            assert second.future is None and second.started
            assert worker._work_queue.qsize() == 0
        finally:
            finish.set()
    assert calls == [(60,90)]
    assert slots.acquire(blocking=False)
    slots.release()


def test_logo_recovery_stops_at_next_scale_without_changing_normal_search(monkeypatch):
    stop = Event()
    mask = np.zeros((20,40),np.uint8); mask[3:17,3:37] = 255
    monkeypatch.setattr(label_vision,'_logo_masks',lambda:{'psa':mask})
    original = label_vision.cv2.matchTemplate
    calls = []
    def match(*args,**kwargs):
        calls.append(1)
        stop.set()
        return original(*args,**kwargs)
    monkeypatch.setattr(label_vision.cv2,'matchTemplate',match)
    with grading_cancellation_scope(stop):
        with pytest.raises(GradingCancelled):
            label_vision.logo_company(Image.new('RGB',(400,400),'white'))
    assert len(calls) <= 3
    # Context cleanup prevents the cancellation leaking into later requests.
    assert isinstance(label_vision._logo_matches(Image.new('RGB',(10,10))),list)


def test_cancelled_job_releases_slot_without_recovery_work():
    entered, finish = Event(), Event()
    slots = BoundedSemaphore(1)
    def grade(image):
        entered.set()
        assert finish.wait(2)
        label_vision.logo_company(image)
        pytest.fail('Cancelled recovery must not continue')
    with ThreadPoolExecutor(max_workers=1) as worker:
        job = GradingJob(SimpleNamespace(read_grading=grade),worker,slots)
        job.start(Image.new('RGB',(400,400)))
        assert entered.wait(2)
        job.stop(); finish.set()
        with pytest.raises(GradingCancelled):
            job.result()
    assert slots.acquire(blocking=False)
    slots.release()


def test_submission_failure_is_optional_and_releases_owned_pixels_and_slot():
    slots = BoundedSemaphore(1)
    worker = ThreadPoolExecutor(max_workers=1)
    worker.shutdown()
    job = GradingJob(SimpleNamespace(read_grading=lambda image:None),worker,slots)
    job.start(Image.new('RGB',(60,90)))
    assert job.future.done()
    with pytest.raises(RuntimeError):
        job.result()
    assert slots.acquire(blocking=False)
    slots.release()
