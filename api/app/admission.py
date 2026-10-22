from __future__ import annotations

import asyncio


class ScanLimiter:
    def __init__(self, wait_limit: int, slots: int = 1) -> None:
        self._lock = asyncio.Lock()
        self._active = 0
        self._waiters: list[asyncio.Event] = []
        self.wait_limit = wait_limit
        self.slots = max(1, slots)

    async def acquire(self) -> bool:
        while True:
            async with self._lock:
                if self._active < self.slots:
                    self._active += 1
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
            self._active = max(0, self._active - 1)
            if self._waiters:
                self._waiters.pop(0).set()

    async def busy(self) -> bool:
        """Whether a live scan is running or waiting for an admission slot."""
        async with self._lock:
            return self._active > 0 or bool(self._waiters)
