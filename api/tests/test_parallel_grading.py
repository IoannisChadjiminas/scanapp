from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
import sys

from PIL import Image
import pytest

from app.config import Settings
from app.recognition import pipeline
from app.recognition.grading_parallel import GradingJob, parallel_grading_scope
from app.recognition.ocr import CardOcr, OcrResult
from app.recognition.runtime import Runtime
import app.recognition.runtime as runtime_module
from app.schemas import GradingEvidence, ScanStatus


def test_job_owns_exact_input_and_starts_only_once():
    entered, finish = Event(), Event()
    observed = []
    def read(image):
        entered.set()
        assert finish.wait(2)
        observed.append((image.size, image.getpixel((0, 0))))
        return GradingEvidence(slab_detected=True, company='psa', grade=9)
    original = Image.new('RGB', (60, 90), 'red')
    with ThreadPoolExecutor(max_workers=1) as worker:
        job = GradingJob(SimpleNamespace(read_grading=read), worker)
        job.start(original)
        assert entered.wait(2)
        original.paste('blue', (0, 0, 60, 90))
        job.start(original)
        finish.set()
        assert job.result().grade == 9
    assert observed == [((60, 90), (255, 0, 0))]
    assert job.elapsed_ms > 0


def test_pipeline_overlaps_and_joins_before_saving(monkeypatch):
    entered, card_done = Event(), Event()
    expected = GradingEvidence(slab_detected=True, company='psa', grade=9)
    def grade(image):
        entered.set()
        assert card_done.wait(2)
        return expected
    serial = SimpleNamespace(read_grading=lambda image: pytest.fail('Must not reuse card OCR'))
    response = SimpleNamespace(status=ScanStatus.uncertain, id='scan', versions={})
    saves = []
    first = pipeline._ScanEvaluation(response, {'total_ms': 1.}, Image.new('RGB', (60, 90)),
        lambda: saves.append(response.grading), None, OcrResult(), [], ('en',), 0., False, {})
    def recognize(data, **kwargs):
        kwargs['_input_observer'](first.input_image)
        assert entered.wait(2), 'Grading must start before card OCR finishes'
        card_done.set()
        return first
    monkeypatch.setattr(pipeline, '_recognize_bytes_once', recognize)
    with ThreadPoolExecutor(max_workers=1) as worker:
        runtime = SimpleNamespace(ocr=serial, grading_ocr=SimpleNamespace(read_grading=grade),
                                  grading_executor=worker, require=lambda: (None, None, serial))
        result = pipeline.recognize_bytes(b'fake', settings=Settings(_env_file=None, parallel_grading=True),
            runtime=runtime, catalog=None, results=None, session_id='test', skip_detect=True)
    assert result.grading == expected and saves == [expected]
    assert result.timings_ms['grading_parallel'] == 1
    assert result.timings_ms['grading_wait_ms'] >= 0
    assert result.timings_ms['total_ms'] >= result.timings_ms['grading_ms']


def test_grading_failure_preserves_scan_and_warning(monkeypatch):
    def fail(image):
        raise ValueError('private detail')
    serial = SimpleNamespace(read_grading=fail)
    response = SimpleNamespace(status=ScanStatus.uncertain, id='scan', versions={})
    saves = []
    first = pipeline._ScanEvaluation(response, {'total_ms': 1.}, Image.new('RGB', (60, 90)),
        lambda: saves.append(True), None, OcrResult(), [], ('en',), 0., False, {})
    def recognize(data, **kwargs):
        kwargs['_input_observer'](first.input_image)
        return first
    monkeypatch.setattr(pipeline, '_recognize_bytes_once', recognize)
    with ThreadPoolExecutor(max_workers=1) as worker:
        runtime = SimpleNamespace(ocr=serial, grading_ocr=SimpleNamespace(read_grading=fail),
                                  grading_executor=worker, require=lambda: (None, None, serial))
        result = pipeline.recognize_bytes(b'fake', settings=Settings(_env_file=None, parallel_grading=True),
            runtime=runtime, catalog=None, results=None, session_id='test', skip_detect=True)
    assert result.status == ScanStatus.uncertain and saves == [True]
    assert result.grading.warnings == ['grading_ocr_failed']


def test_card_failure_drains_grading_without_masking_original():
    done = Event()
    def grade(image):
        done.set()
        raise ValueError('grading failure')
    @parallel_grading_scope
    def recognize(data, *, settings, runtime, _grading_job):
        _grading_job.start(Image.new('RGB', (60, 90)))
        raise RuntimeError('card failure')
    with ThreadPoolExecutor(max_workers=1) as worker:
        runtime = SimpleNamespace(ocr=object(), grading_ocr=SimpleNamespace(read_grading=grade),
                                  grading_executor=worker)
        with pytest.raises(RuntimeError, match='card failure'):
            recognize(b'fake', settings=Settings(_env_file=None, parallel_grading=True), runtime=runtime)
    assert done.is_set()


def test_shared_engine_is_rejected_before_any_work():
    reader = object()
    @parallel_grading_scope
    def recognize(*args, **kwargs):
        pytest.fail('Must not run with shared OCR engines')
    with ThreadPoolExecutor(max_workers=1) as worker:
        runtime = SimpleNamespace(ocr=reader, grading_ocr=reader, grading_executor=worker)
        with pytest.raises(RuntimeError, match='isolated'):
            recognize(b'fake', settings=Settings(_env_file=None, parallel_grading=True), runtime=runtime)


@pytest.mark.parametrize('options', [{'parallel_grading': False},
    {'parallel_grading': True, 'use_ocr': False}, {'parallel_grading': True, 'use_grading': False}])
def test_disabled_scope_keeps_serial_path(options):
    @parallel_grading_scope
    def recognize(data, *, settings, runtime, **kwargs):
        assert '_grading_job' not in kwargs
        return 'serial'
    runtime = SimpleNamespace(ocr=object(), grading_ocr=object(), grading_executor=object())
    assert recognize(b'fake', settings=Settings(_env_file=None, **options), runtime=runtime) == 'serial'


@pytest.mark.parametrize('parallel,deadline', [(False,False), (True,False), (False,True)])
def test_runtime_owns_separate_engine_and_cleans_up_reload(monkeypatch, tmp_path, parallel, deadline):
    readers = []
    def make_reader(**kwargs):
        reader = SimpleNamespace(arguments=kwargs, shared_from=None)
        reader.share_inference_sessions_from = lambda other: setattr(reader, 'shared_from', other)
        readers.append(reader)
        return reader
    monkeypatch.setattr(runtime_module, 'CardOcr', make_reader)
    monkeypatch.setattr(runtime_module, 'DinoEmbedder', lambda *args: object())
    runtime = Runtime(Settings(_env_file=None, data_dir=tmp_path, parallel_grading=parallel,
                               grading_at_card_deadline=deadline))
    enabled = parallel or deadline
    runtime.load(SimpleNamespace())
    assert runtime.ready
    assert len(readers) == (2 if enabled else 1)
    old_worker = runtime.grading_executor
    if enabled:
        assert runtime.ocr is not runtime.grading_ocr
        assert runtime.ocr.arguments == runtime.grading_ocr.arguments
        assert runtime.grading_ocr.shared_from is runtime.ocr
        assert old_worker._max_workers == 1
    else:
        assert runtime.grading_ocr is None and old_worker is None
    runtime.load(SimpleNamespace())
    if enabled:
        assert old_worker._shutdown
        assert runtime.grading_executor is not old_worker
    runtime.close()
    assert runtime.grading_executor is None and runtime.grading_ocr is None


def test_only_read_only_cpu_sessions_are_shared(monkeypatch):
    class FakeSession:
        def get_providers(self):
            return ['CPUExecutionProvider']
    monkeypatch.setitem(sys.modules, 'onnxruntime', SimpleNamespace(InferenceSession=FakeSession))
    def reader():
        obj = CardOcr.__new__(CardOcr)
        obj._model_signature = ('det', 'rec', 'cls', 1, 1)
        obj.engine = SimpleNamespace(use_cls=True, **{
            name: SimpleNamespace(session=SimpleNamespace(session=FakeSession()), mutable_state=[])
            for name in ('text_det', 'text_cls', 'text_rec')})
        return obj
    card, grading = reader(), reader()
    grading.share_inference_sessions_from(card)
    for name in ('text_det', 'text_cls', 'text_rec'):
        lhs, rhs = getattr(card.engine, name), getattr(grading.engine, name)
        assert lhs is not rhs and lhs.session is not rhs.session
        assert lhs.mutable_state is not rhs.mutable_state
        assert lhs.session.session is rhs.session.session
    grading.engine.use_cls = False
    assert card.engine.use_cls is True
    with pytest.raises(ValueError, match='separate engines'):
        card.share_inference_sessions_from(card)
    grading._model_signature = ('different-model', 'rec', 'cls', 1, 1)
    with pytest.raises(ValueError, match='different OCR'):
        grading.share_inference_sessions_from(card)


def test_invalid_session_rejects_whole_share_before_modification(monkeypatch):
    class FakeSession:
        def get_providers(self):
            return ['CPUExecutionProvider']
    monkeypatch.setitem(sys.modules, 'onnxruntime', SimpleNamespace(InferenceSession=FakeSession))
    def reader():
        obj = CardOcr.__new__(CardOcr)
        obj._model_signature = ('det', 'rec', 'cls', 1, 1)
        obj.engine = SimpleNamespace(**{name: SimpleNamespace(session=SimpleNamespace(session=FakeSession()))
                                      for name in ('text_det', 'text_cls', 'text_rec')})
        return obj
    card, grading = reader(), reader()
    original = grading.engine.text_det.session.session
    card.engine.text_rec.session.session = object()
    with pytest.raises(ValueError, match='CPU ONNX'):
        grading.share_inference_sessions_from(card)
    assert grading.engine.text_det.session.session is original
