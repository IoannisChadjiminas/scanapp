import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.admission import ScanLimiter
from app.config import Settings
from app.db import SerializedConnection, connect, init_results
from app.schemas import Coverage, OcrEvidence, ScanResponse, ScanStatus


@pytest.mark.parametrize('stream,status,expected_outcome', [
    (False, 'matched', 'usable'), (True, 'uncertain', 'usable'),
    (False, 'retake', 'retake'), (True, 'no_match', 'no_match'),
    (False, 'error', 'failed'), (True, 'error', 'failed'),
])
@pytest.mark.parametrize('global_enforced', [True, False])
def test_scan_permit_is_claimed_once_and_outcome_settled(monkeypatch, tmp_path, stream, status, expected_outcome, global_enforced):
    from app.routes import scans
    session, attempt = str(uuid.uuid4()), str(uuid.uuid4())
    settings = Settings(_env_file=None, data_dir=tmp_path, product_api_scan_gate_ready=True)
    results = connect(settings.results_sqlite, factory=SerializedConnection)
    init_results(results)
    results.execute('INSERT INTO sessions(id,created_at,last_seen) VALUES (?, ?, ?)', (session, 'now', 'now'))
    results.commit()
    calls = {'claims': 0, 'recognitions': 0, 'settlements': []}

    class Product:
        def __init__(self, _settings): pass
        def scan_quota_enforced(self): return global_enforced
        def claim_scan(self, _secret, _execution, actual_session, actual_attempt):
            assert actual_session == session and actual_attempt == attempt
            calls['claims'] += 1
            return '42'
        def settle_scan(self, _attempt, _execution, _session, outcome, scan_id):
            calls['settlements'].append((outcome, scan_id))

    @contextmanager
    def lane(runtime):
        yield runtime

    def recognize(_data, **kwargs):
        calls['recognitions'] += 1
        if status == 'error':
            from app.recognition.images import ImageError
            raise ImageError('bad image')
        scan_id = str(uuid.uuid4())
        conn = kwargs['results']
        with conn._cache_lock:
            conn.execute('INSERT INTO scans(id,session_id,created_at,status,preprocessing) VALUES (?,?,?,?,?)',
                         (scan_id, session, 'now', status, 'pad'))
            kwargs['_on_persist'](conn, scan_id, status)
            conn.commit()
        return ScanResponse(id=scan_id, status=ScanStatus(status), suggestions=[], ocr=OcrEvidence(),
                            coverage=Coverage(cards=0, indexed=0, missing_images=0), timings_ms={}, versions={})

    monkeypatch.setattr(scans, 'SubscriptionClient', Product)
    monkeypatch.setattr(scans, 'get_or_create_session', lambda *_args: session)
    monkeypatch.setattr(scans, 'scan_lane', lane)
    monkeypatch.setattr(scans, 'recognize_bytes', recognize)
    monkeypatch.setattr('app.cardmarket_queue.schedule_scan_parallel_read', lambda *_a, **_k: None)
    app = FastAPI()
    app.include_router(scans.router)
    app.state.settings = settings
    app.state.dbs = SimpleNamespace(catalog=None, results=results)
    app.state.runtime = SimpleNamespace()
    app.state.scan_limiter = ScanLimiter(0)
    executor = ThreadPoolExecutor(max_workers=1)
    app.state.executor = executor

    @app.middleware('http')
    async def bind(_request, call_next):
        app.state.loop = asyncio.get_running_loop()
        return await call_next(_request)

    headers = {'x-pokesingle-scan-attempt': attempt, 'x-pokesingle-scan-permit': 'p' * 43}
    image = {'image': ('card.jpg', b'jpeg', 'image/jpeg')}
    with TestClient(app) as client, executor:
        if global_enforced:
            missing = client.post('/scans', files=image)
            assert missing.status_code == 403
        response = client.post('/scans', headers=headers, data={'stream_results': str(stream).lower()}, files=image)
        assert response.status_code == (400 if status == 'error' and not stream else 200)
        event = json.loads(response.text.splitlines()[-1]) if stream else response.json()
        body = (event['result'] if stream else event) if status != 'error' else None
        if status == 'error' and stream:
            assert event['type'] == 'error'
        repeated = client.post('/scans', headers=headers, files=image)
        assert repeated.status_code == 409
    assert calls['claims'] == calls['recognitions'] == 1
    assert calls['settlements'] == [(expected_outcome, body['id'] if body else None)]
    row = results.execute('SELECT outcome,state FROM scan_permit_settlement').fetchone()
    assert (row['outcome'], row['state']) == (expected_outcome, 'acknowledged')
    results.close()
