from __future__ import annotations

import asyncio


class ScanLimiter:
    def __init__(self, wait_limit: int) -> None:
        self._lock = asyncio.Lock()
        self._busy = False
        self._waiters: list[asyncio.Event] = []
        self.wait_limit = wait_limit

    async def acquire(self) -> bool:
        while True:
            async with self._lock:
                if not self._busy:
                    self._busy = True
                    return True
                if len(self._waiters) >= self.wait_limit:
                    return False
                waiter = asyncio.Event()
                self._waiters.append(waiter)
            try:
                await waiter.wait()
            except asyncio.CancelledError:
                async with self._lock:
                    if waiter in self._waiters:
                        self._waiters.remove(waiter)
                raise

    async def release(self) -> None:
        async with self._lock:
            self._busy = False
            if self._waiters:
                self._waiters.pop(0).set()
