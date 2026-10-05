"""Optional, request-local visual preview. Never a saved or confirmable match."""
import asyncio
import json
import logging

from starlette.responses import StreamingResponse

from app.recognition.artifacts import ArtifactError
from app.recognition.images import ImageError


_running = set()


async def drain_scan_streams():
    """Finish owned workers before application shutdown closes their DBs."""
    if _running:
        await asyncio.gather(*tuple(_running), return_exceptions=True)


def scan_stream(*, loop, executor, recognize, limiter, response, trace):
    """Own the worker and admission slot even if the streaming client leaves.

    One upload, one recognition, one persisted final result. No rerun on a
    dropped stream. Preview/error events contain no confirmation credentials.
    """
    events = asyncio.Queue()
    sent_preview = False
    preview_payload = None
    preview_delivered = False
    logger = logging.getLogger('scan.diagnostics')

    def deliver_preview():
        nonlocal preview_delivered
        if preview_payload is not None and not preview_delivered:
            preview_delivered = True
            events.put_nowait(preview_payload)

    def preview(payload):
        nonlocal sent_preview, preview_payload
        if sent_preview:
            return
        sent_preview = True
        preview_payload = dict(type='provisional', **payload)
        loop.call_soon_threadsafe(deliver_preview)

    async def work():
        try:
            result = await loop.run_in_executor(executor, lambda: recognize(preview))
            # Very fast workers may finish before the queued loop callback is
            # serviced. Deliver exactly once before the final in that race.
            deliver_preview()
            logger.info('recognition_done trace=%s scan_id=%s status=%s timings_ms=%s',
                        trace, result.id, result.status.value, result.timings_ms)
            events.put_nowait(dict(type='final', result=result.model_dump(mode='json')))
        except (ArtifactError, ImageError) as error:
            events.put_nowait(dict(type='error', code='unavailable' if isinstance(error, ArtifactError)
                                  else 'invalid_image'))
        except Exception as error:
            logger.error('recognition_failed trace=%s error_type=%s', trace, type(error).__name__)
            events.put_nowait(dict(type='error', code='failed'))
        finally:
            await limiter.release()

    task = loop.create_task(work())
    _running.add(task)
    task.add_done_callback(_running.discard)

    async def body():
        # Disconnect cancels only this consumer. The owned worker releases its
        # slot after it stops touching engines/DBs, not when the socket closes.
        while True:
            try:
                event = await asyncio.wait_for(events.get(), timeout=10)
            except asyncio.TimeoutError:
                event = dict(type='progress', stage='checking')
            yield json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n'
            if event['type'] in {'final', 'error'}:
                return

    stream = StreamingResponse(body(), media_type='application/x-ndjson', headers={
        'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no',
    })
    # Keep newly created guest-session cookies, including repeated headers.
    stream.raw_headers.extend((key, value) for key, value in response.raw_headers
                             if key.lower() not in {b'content-length', b'content-type', b'transfer-encoding'})
    return stream
