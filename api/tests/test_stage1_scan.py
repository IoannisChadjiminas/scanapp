"""A failed stage 1 gate leaves the scan on today's pipeline. A pass does not enter it."""
import asyncio
import logging
from contextlib import contextmanager
from types import SimpleNamespace

from app.recognition.stage1_check import CheckJob, Stage1Checker
from app.recognition.stage1_gate import Decision
from app.schemas import Coverage, OcrEvidence, ScanResponse, ScanStatus


def _answer(**_kwargs):
    stage = _kwargs.get('decision').stage if _kwargs.get('decision') is not None else '1'
    return ScanResponse(
        id='stage1-id', status=ScanStatus.uncertain, suggestions=[],
        ocr=OcrEvidence(), coverage=Coverage(cards=0, indexed=0, missing_images=0),
        timings_ms={'total_ms': 1.0}, versions={'stage': stage})


@contextmanager
def _lane(runtime):
    yield runtime


def _client(monkeypatch, *, early=False, background=False, decision=None, stream=False):
    from concurrent.futures import ThreadPoolExecutor

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.admission import ScanLimiter
    from app.config import Settings
    from app.recognition.images import ImageError
    from app.routes import scans

    calls = {'pipeline': 0, 'gate': 0, 'pipeline_kwargs': []}

    def recognize_bytes(data, **kwargs):
        calls['pipeline'] += 1
        calls['pipeline_kwargs'].append(kwargs)
        if kwargs.get('results', object()) is None and kwargs.get('store_capture') is False:
            return SimpleNamespace(suggestions=[])
        if kwargs.get('_progress_observer') is not None:
            return SimpleNamespace(
                id='full-id', status=SimpleNamespace(value='uncertain'), suggestions=[],
                timings_ms=SimpleNamespace(model_dump=lambda **_k: {}),
                model_dump=lambda **_k: {'id': 'full-id', 'status': 'uncertain'})
        raise ImageError('pipeline')

    def evaluate_stage1(**_kwargs):
        calls['gate'] += 1
        return decision

    monkeypatch.setattr(scans, 'recognize_bytes', recognize_bytes)
    monkeypatch.setattr(scans, 'evaluate_stage1', evaluate_stage1)
    monkeypatch.setattr(scans, 'answer_stage1', _answer)
    monkeypatch.setattr(scans, 'scan_lane', _lane)
    monkeypatch.setattr(scans, 'get_or_create_session', lambda *_a, **_k: 'guest')
    monkeypatch.setattr('app.cardmarket_queue.schedule_scan_parallel_read', lambda *_a, **_k: None)
    app = FastAPI()
    app.include_router(scans.router)
    executor = ThreadPoolExecutor(max_workers=1)
    app.state.settings = Settings(
        _env_file=None, scan_stream_results=stream, stage1_early_exit=early,
        stage1_background_check=background, stage1_sample_rate=1.0, store_captures=False)
    app.state.executor = executor
    app.state.scan_limiter = ScanLimiter(0)
    app.state.runtime = SimpleNamespace()
    app.state.dbs = SimpleNamespace(catalog=None, results=None)
    app.state.stage1_checker = Stage1Checker()

    @app.middleware('http')
    async def bind(request, call_next):
        app.state.loop = asyncio.get_running_loop()
        return await call_next(request)

    return TestClient(app), executor, calls


def test_flag_off_does_not_consult_the_gate(monkeypatch):
    client, executor, calls = _client(monkeypatch, early=False)
    with client, executor:
        response = client.post('/scans', files={'image': ('card.jpg', b'jpeg', 'image/jpeg')})
    assert response.status_code == 400
    assert calls['pipeline'] == 1 and calls['gate'] == 0


def test_abstain_runs_the_full_pipeline(monkeypatch):
    decision = Decision(False, None, None, 0.01, None, 'low_margin', 1.0)
    client, executor, calls = _client(monkeypatch, early=True, decision=decision)
    with client, executor:
        response = client.post('/scans', files={'image': ('card.jpg', b'jpeg', 'image/jpeg')})
    assert response.status_code == 400
    assert calls['pipeline'] == 1 and calls['gate'] == 1
    assert client.app.state.stage1_checker.answers == 0


def test_an_answer_skips_the_pipeline_and_queues_the_background_check(monkeypatch):
    decision = Decision(True, '1', 'en:base1-25', 0.04, None, 'same', 2.0)
    client, executor, calls = _client(monkeypatch, early=True, background=True, decision=decision)
    with client, executor:
        response = client.post('/scans', files={'image': ('card.jpg', b'jpeg', 'image/jpeg')})
    assert response.status_code == 200
    assert response.json()['id'] == 'stage1-id'
    assert response.json()['status'] == 'uncertain'
    assert calls['pipeline'] == 0 and calls['gate'] == 1
    checker = client.app.state.stage1_checker
    assert checker.answers == 1
    job = checker._queue.get_nowait()
    assert job.card_id == 'en:base1-25' and job.scan_id == 'stage1-id'
    job.recognize(b'photo-bytes')
    assert calls['pipeline_kwargs'][-1]['results'] is None


def test_answer_counter_includes_scans_without_background_checks(monkeypatch):
    decision = Decision(True, '1b', 'en:base1-25', 0.04, 33, 'artwork', 55.0)
    client, executor, calls = _client(monkeypatch, early=True, background=False, decision=decision)
    with client, executor:
        response = client.post('/scans', files={'image': ('card.jpg', b'jpeg', 'image/jpeg')})
    assert response.status_code == 200
    assert calls['pipeline'] == 0 and calls['gate'] == 1
    checker = client.app.state.stage1_checker
    assert checker.answers == 1
    assert checker._queue.qsize() == 0


def test_streamed_stage1_answer_is_the_final_result(monkeypatch):
    import json

    decision = Decision(True, '1b', 'en:base1-25', 0.04, 33, 'artwork', 55.0)
    client, executor, calls = _client(
        monkeypatch, early=True, background=True, decision=decision, stream=True)
    with client, executor:
        response = client.post('/scans', data={'stream_results': 'true'},
                               files={'image': ('card.jpg', b'jpeg', 'image/jpeg')})
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]['type'] == 'final'
    assert events[-1]['result']['id'] == 'stage1-id'
    assert events[-1]['result']['versions']['stage'] == '1b'
    assert calls == {'pipeline': 0, 'gate': 1, 'pipeline_kwargs': []}
    checker = client.app.state.stage1_checker
    assert checker.answers == 1
    job = checker._queue.get_nowait()
    assert job.card_id == 'en:base1-25'
    job.recognize(b'photo-bytes')
    assert calls['pipeline_kwargs'][-1]['results'] is None


def test_background_check_logs_a_disagreement_and_keeps_the_photo(tmp_path, caplog):
    class Full:
        suggestions = [SimpleNamespace(card_id='en:base1-4')]

    job = CheckJob('scan-1', 'en:base1-25', b'photo-bytes', lambda _data: Full(), store_dir=tmp_path)
    checker = Stage1Checker()
    with caplog.at_level(logging.INFO, logger='scan.diagnostics'):
        assert checker.run_job(job) is False
    assert checker.checks == 1 and checker.disagreements == 1
    line = next(record.getMessage() for record in caplog.records if record.getMessage().startswith('stage1_check'))
    assert line == 'stage1_check scan_id=scan-1 stage1_card=en:base1-25 full_card=en:base1-4 agree=false'
    assert (tmp_path / 'scan-1-stage1-disagree.jpg').read_bytes() == b'photo-bytes'


def test_background_check_skips_when_a_scan_is_busy(caplog):
    checker = Stage1Checker()
    job = CheckJob('scan-2', 'en:base1-25', b'', lambda _data: None)
    with caplog.at_level(logging.INFO, logger='scan.diagnostics'):
        checker.submit(job, sample_rate=1.0, busy=True)
    assert checker._queue.qsize() == 0
    assert 'skipped busy=true' in caplog.records[-1].getMessage()
