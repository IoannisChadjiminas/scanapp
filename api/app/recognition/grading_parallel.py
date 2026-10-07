"""Optional label work on an isolated worker, with no pending-job backlog."""
from concurrent.futures import Future, ThreadPoolExecutor
from functools import wraps
from threading import BoundedSemaphore, Event
import time
from typing import Any

from PIL import Image
from app.recognition.grading_control import grading_cancellation_scope


class GradingJob:
    def __init__(self, reader: Any, executor: ThreadPoolExecutor, slots=None):
        self.reader = reader
        self.executor = executor
        self.future: Future | None = None
        self.elapsed_ms = 0.
        self.slots = slots if slots is not None else BoundedSemaphore(1)
        self.stop_event = Event()
        self.started = False
        self.started_at = None

    def start(self, image: Image.Image) -> None:
        if self.started:
            return
        self.started = True
        if not self.slots.acquire(blocking=False):
            return
        # Pillow images may lazily mutate internal state while being read.
        # Grade the exact original/cropped pixels, but own their storage.
        try:
            pixels = image.copy()
        except Exception as exc:
            self.slots.release()
            self.future = Future()
            self.future.set_exception(exc)
            return
        def read():
            started = time.perf_counter()
            try:
                with grading_cancellation_scope(self.stop_event):
                    return self.reader.read_grading(pixels)
            finally:
                self.elapsed_ms = (time.perf_counter() - started) * 1000
        def cleanup(future):
            pixels.close()
            self.slots.release()
            # Consume abandoned exceptions. A late result never modifies the
            # already returned/saved scan or the user's confirmation choice.
            if not future.cancelled():
                future.exception()
        try:
            self.started_at = time.perf_counter()
            self.future = self.executor.submit(read)
            self.future.add_done_callback(cleanup)
        except Exception as exc:
            pixels.close()
            self.slots.release()
            self.future = Future()
            self.future.set_exception(exc)

    def stop(self):
        self.stop_event.set()
        if self.future is not None:
            self.future.cancel()

    def result(self):
        if self.future is None:
            raise RuntimeError('Grading job was not started')
        return self.future.result()

    def drain(self) -> None:
        if self.future is not None:
            try:
                self.future.result()
            except Exception:
                # The recognition path already handles grading failures;
                # cleanup must not mask the original recognition exception.
                pass


def grading_requested(settings, graded: bool | None) -> bool:
    """Hints only matter once GRADING_REQUIRES_CLIENT_HINT is on.

    Until then every scan is graded as before, so a rollout can compare the
    client's guess with what grading actually found.
    """
    if not getattr(settings, 'grading_requires_client_hint', False):
        return True
    return bool(graded)


def parallel_grading_scope(recognize):
    @wraps(recognize)
    def scoped(data, *, settings, runtime, **kwargs):
        if not grading_requested(settings, kwargs.get('graded')):
            return recognize(data, settings=settings, runtime=runtime, **kwargs)
        reader = getattr(runtime, 'grading_ocr', None)
        executor = getattr(runtime, 'grading_executor', None)
        deadline = getattr(settings, 'grading_at_card_deadline', False)
        enabled = ((getattr(settings, 'parallel_grading', False) or deadline)
                   and getattr(settings, 'use_ocr', True)
                   and getattr(settings, 'use_grading', True))
        if not enabled or reader is None or executor is None:
            return recognize(data, settings=settings, runtime=runtime, **kwargs)
        if reader is getattr(runtime, 'ocr', None):
            raise RuntimeError('Parallel grading requires an isolated OCR engine')
        slots = getattr(runtime, 'grading_slots', None)
        if slots is None:
            slots = runtime.grading_slots = BoundedSemaphore(1)
        job = GradingJob(reader, executor, slots)
        try:
            return recognize(data, settings=settings, runtime=runtime,
                             _grading_job=job, **kwargs)
        finally:
            if deadline:
                job.stop()
            else:
                job.drain()
    return scoped
