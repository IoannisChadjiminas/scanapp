import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event
from types import SimpleNamespace

import pytest
from starlette.responses import Response

from app.admission import ScanLimiter
from app.recognition.images import ImageError
from app.recognition.progress import scan_stream


def result():
    return SimpleNamespace(id='final-id', status=SimpleNamespace(value='uncertain'),
        timings_ms={'total_ms': 9}, model_dump=lambda **kwargs:
        dict(id='final-id', status='uncertain', best_match={'card_id': 'different-final-card'}))


@pytest.mark.parametrize('repeat', range(10))
def test_one_preview_then_final_and_session_cookie_with_slot_released(repeat):
    async def run():
        limiter = ScanLimiter(0); assert await limiter.acquire()
        response = Response(); response.set_cookie('guest', 'private-session')
        calls = []
        def recognize(observer):
            calls.append(1)
            observer(dict(candidates=[dict(card_id='initial-card', name='Pikachu')],
                          provisional=True, printing_confirmed=False))
            observer(dict(candidates=[dict(card_id='ignored-retry')]))
            return result()
        with ThreadPoolExecutor(max_workers=1) as executor:
            stream = scan_stream(loop=asyncio.get_running_loop(), executor=executor,
                recognize=recognize, limiter=limiter, response=response, trace='test')
            events = [json.loads(chunk) async for chunk in stream.body_iterator]
        assert [e['type'] for e in events] == ['accepted', 'provisional', 'final']
        assert events[0] == dict(type='accepted', trace='test')
        assert events[1]['candidates'][0]['card_id'] == 'initial-card'
        assert events[2]['result']['best_match']['card_id'] == 'different-final-card'
        assert calls == [1] and not limiter._busy
        assert stream.headers['cache-control'] == 'no-store'
        assert stream.headers['x-accel-buffering'] == 'no'
        assert 'content-length' not in stream.headers
        assert 'guest=' in stream.headers['set-cookie']
    asyncio.run(run())


@pytest.mark.parametrize('error,code', [(ImageError('private-error'), 'invalid_image'),
                                        (ValueError('private-error'), 'failed')])
def test_error_is_terminal_sanitized_and_releases_slot(error, code):
    async def run():
        limiter = ScanLimiter(0); assert await limiter.acquire()
        def recognize(observer):
            raise error
        with ThreadPoolExecutor(max_workers=1) as executor:
            stream = scan_stream(loop=asyncio.get_running_loop(), executor=executor,
                recognize=recognize, limiter=limiter, response=Response(), trace='test')
            events = [json.loads(chunk) async for chunk in stream.body_iterator]
        assert events == [dict(type='accepted', trace='test'), dict(type='error', code=code)] and not limiter._busy
    asyncio.run(run())


def test_disconnected_consumer_does_not_release_slot_or_rerun_recognition():
    async def run():
        limiter = ScanLimiter(0); assert await limiter.acquire()
        finish = Event(); calls = []
        def recognize(observer):
            calls.append(1); observer(dict(candidates=[]))
            assert finish.wait(2)
            return result()
        with ThreadPoolExecutor(max_workers=1) as executor:
            stream = scan_stream(loop=asyncio.get_running_loop(), executor=executor,
                recognize=recognize, limiter=limiter, response=Response(), trace='test')
            iterator = stream.body_iterator
            assert json.loads(await anext(iterator))['type'] == 'accepted'
            assert json.loads(await anext(iterator))['type'] == 'provisional'
            await iterator.aclose()
            assert limiter._busy and not await limiter.acquire()
            finish.set()
            for _ in range(100):
                if not limiter._busy:
                    break
                await asyncio.sleep(.01)
        assert calls == [1] and not limiter._busy
    asyncio.run(run())


def stream_app(monkeypatch, *, enabled):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.routes import scans

    def recognize_bytes(data, **kwargs):
        observer = kwargs.get('_progress_observer')
        if observer is None:
            raise ImageError('plain path')
        observer(dict(candidates=[dict(card_id='initial-card', name='Pikachu')],
                      provisional=True, printing_confirmed=False))
        return result()
    monkeypatch.setattr(scans, 'recognize_bytes', recognize_bytes)
    monkeypatch.setattr(scans, 'get_or_create_session', lambda *args: 'guest')
    monkeypatch.setattr('app.cardmarket_queue.schedule_scan_parallel_read', lambda *a, **k: None)
    app = FastAPI()
    app.include_router(scans.router)
    executor = ThreadPoolExecutor(max_workers=1)
    app.state.settings = Settings(_env_file=None, scan_stream_results=enabled)
    app.state.executor = executor
    app.state.scan_limiter = ScanLimiter(0)
    app.state.runtime = app.state.dbs = SimpleNamespace(catalog=None, results=None)

    @app.middleware('http')
    async def bind(request, call_next):
        app.state.loop = asyncio.get_running_loop()
        return await call_next(request)
    return TestClient(app), executor


def test_stream_switch_off_keeps_the_plain_json_path(monkeypatch):
    client, executor = stream_app(monkeypatch, enabled=False)
    with client, executor:
        response = client.post('/scans', data={'stream_results': 'true'},
                               files={'image': ('card.jpg', b'jpeg', 'image/jpeg')})
    assert response.status_code == 400 and response.json()['detail'] == 'plain path'


def test_stream_switch_on_sends_provisional_then_final(monkeypatch, caplog):
    client, executor = stream_app(monkeypatch, enabled=True)
    with client, executor, caplog.at_level('INFO', logger='scan.diagnostics'):
        response = client.post('/scans', data={'stream_results': 'true'},
                               files={'image': ('card.jpg', b'jpeg', 'image/jpeg')})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert response.headers['content-type'].startswith('application/x-ndjson')
    assert [e['type'] for e in events] == ['accepted', 'provisional', 'final']
    line = next(r.getMessage() for r in caplog.records if 'scan_stream_done' in r.getMessage())
    assert 'scan_id=final-id' in line and 'provisional_top=initial-card' in line
    assert 'final_ms=' in line and 'provisional_ms=' in line


@pytest.mark.parametrize('trust,expected', [(False, False), (True, True)])
def test_phone_warp_is_trusted_only_when_switched_on(monkeypatch, trust, expected):
    from app.routes import scans
    client, executor = stream_app(monkeypatch, enabled=False)
    seen = {}
    def recognize_bytes(data, **kwargs):
        seen['skip_detect'] = kwargs['skip_detect']
        raise ImageError('plain path')
    monkeypatch.setattr(scans, 'recognize_bytes', recognize_bytes)
    client.app.state.settings = client.app.state.settings.model_copy(update=dict(trust_client_warp=trust))
    with client, executor:
        client.post('/scans', data={'skip_detect': 'true'},
                    files={'image': ('card.jpg', b'jpeg', 'image/jpeg')})
    assert seen['skip_detect'] is expected


def test_streaming_is_on_by_default_and_can_be_switched_off():
    from app.config import Settings
    assert Settings(_env_file=None).scan_stream_results is True
    assert Settings(_env_file=None, scan_stream_results=False).scan_stream_results is False


def test_source_fields_reach_the_scan_summary_and_old_phones_still_work(monkeypatch, caplog):
    client, executor = stream_app(monkeypatch, enabled=True)
    files = {'image': ('card.jpg', b'jpeg', 'image/jpeg')}
    with client, executor, caplog.at_level('INFO', logger='scan.diagnostics'):
        new = client.post('/scans', data={
            'stream_results': 'true', 'platform': 'ios', 'capture': 'auto', 'camera': 'native',
            'app_build': '1.0.0+61', 'card_quad': '0.1,0.1,0.9,0.1,0.9,0.9,0.1,0.9',
            'quad_source': 'rect'}, files=files)
        old = client.post('/scans', data={'stream_results': 'true'}, files=files)
    assert new.status_code == old.status_code == 200
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith('scan_summary')]
    assert len(lines) == 2
    assert all(p in lines[0].split() for p in
               ('platform=ios', 'capture=auto', 'camera=native', 'build=1.0.0+61', 'quad=rect', 'quad_valid=true'))
    assert 'platform=unknown' in lines[1].split() and 'quad=none' in lines[1].split()


def test_locale_reaches_recognition(monkeypatch):
    from app.routes import scans
    client, executor = stream_app(monkeypatch, enabled=True)
    seen = []
    inner = scans.recognize_bytes
    monkeypatch.setattr(scans, 'recognize_bytes', lambda data, **kw: (seen.append(kw.get('locale')), inner(data, **kw))[1])
    files = {'image': ('card.jpg', b'jpeg', 'image/jpeg')}
    with client, executor:
        client.post('/scans', data={'stream_results': 'true', 'locale': 'ja_JP'}, files=files)
        client.post('/scans', data={'stream_results': 'true'}, files=files)
    assert seen == ['ja_JP', None]
