"""Cooperative cancellation of optional label recovery; never interrupt card OCR."""
from contextlib import contextmanager
from contextvars import ContextVar

_stop = ContextVar('grading_stop', default=None)


class GradingCancelled(Exception):
    pass


def check_grading_cancelled():
    event = _stop.get()
    if event is not None and event.is_set():
        raise GradingCancelled('Optional grading work cancelled')


@contextmanager
def grading_cancellation_scope(event):
    token = _stop.set(event)
    try:
        check_grading_cancelled()
        yield
    finally:
        _stop.reset(token)
