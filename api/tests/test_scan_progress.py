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
        assert [e['type'] for e in events] == ['provisional', 'final']
        assert events[0]['candidates'][0]['card_id'] == 'initial-card'
        assert events[1]['result']['best_match']['card_id'] == 'different-final-card'
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
        assert events == [dict(type='error', code=code)] and not limiter._busy
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
