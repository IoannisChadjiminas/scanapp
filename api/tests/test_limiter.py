from __future__ import annotations

import asyncio

from app.admission import ScanLimiter


def test_cancelled_waiter_does_not_consume_capacity() -> None:
    async def run() -> None:
        limiter = ScanLimiter(wait_limit=2)
        assert await limiter.acquire() is True
        first = asyncio.create_task(limiter.acquire())
        second = asyncio.create_task(limiter.acquire())
        await asyncio.sleep(0)
        first.cancel()
        with _raises_cancelled():
            await first
        await limiter.release()
        assert await second is True
        third = asyncio.create_task(limiter.acquire())
        await asyncio.sleep(0)
        await limiter.release()
        assert await third is True
        await limiter.release()
        assert await limiter.acquire() is True
        await limiter.release()

    asyncio.run(run())


def test_wait_limit_rejects_additional_waiters() -> None:
    async def run() -> None:
        limiter = ScanLimiter(wait_limit=1)
        assert await limiter.acquire() is True
        waiter = asyncio.create_task(limiter.acquire())
        await asyncio.sleep(0)
        assert await limiter.acquire() is False
        waiter.cancel()
        try:
            await waiter
        except asyncio.CancelledError:
            pass
        await limiter.release()

    asyncio.run(run())


class _raises_cancelled:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return exc_type is asyncio.CancelledError
