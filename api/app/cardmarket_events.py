from __future__ import annotations

import asyncio
import threading
from typing import Any

from app.cardmarket import sample_key

_guard = threading.Lock()
_waiters: dict[str, list[asyncio.Event]] = {}
_loop: asyncio.AbstractEventLoop | None = None


def bind_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    global _loop
    _loop = loop


def notify_product(url: str | None, filters: dict[str, str] | None = None) -> None:
    key = sample_key(url, filters)
    if not key:
        return
    with _guard:
        events = list(_waiters.get(key, ()))
    loop = _loop
    for event in events:
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(event.set)
        else:
            event.set()


async def wait_for_product(
    url: str | None, timeout: float, filters: dict[str, str] | None = None
) -> bool:
    key = sample_key(url, filters)
    if not key:
        await asyncio.sleep(min(timeout, 1.0))
        return False
    event = asyncio.Event()
    with _guard:
        _waiters.setdefault(key, []).append(event)
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        return True
    except TimeoutError:
        return False
    finally:
        with _guard:
            bucket = _waiters.get(key, [])
            if event in bucket:
                bucket.remove(event)
            if not bucket:
                _waiters.pop(key, None)
