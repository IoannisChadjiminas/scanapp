from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import Databases
from app.recognition.runtime import Runtime
from app.routes.cards import router as cards_router
from app.routes.health import router as health_router
from app.routes.images import router as images_router
from app.routes.scans import router as scans_router


class ScanLimiter:
    def __init__(self, wait_limit: int) -> None:
        self._lock = asyncio.Lock()
        self._busy = False
        self._waiting = 0
        self.wait_limit = wait_limit

    async def acquire(self) -> bool:
        async with self._lock:
            if not self._busy:
                self._busy = True
                return True
            if self._waiting >= self.wait_limit:
                return False
            self._waiting += 1
        while True:
            await asyncio.sleep(0.05)
            async with self._lock:
                if not self._busy:
                    self._waiting -= 1
                    self._busy = True
                    return True

    def release(self) -> None:
        self._busy = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    dbs = Databases(settings)
    runtime = Runtime(settings=settings)
    runtime.load()
    runtime.bind_card_languages(dbs.catalog)
    app.state.settings = settings
    app.state.dbs = dbs
    app.state.runtime = runtime
    app.state.scan_limiter = ScanLimiter(settings.scan_wait_limit)
    app.state.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scan")
    app.state.loop = asyncio.get_running_loop()
    try:
        yield
    finally:
        app.state.executor.shutdown(wait=False, cancel_futures=True)
        dbs.close()


app = FastAPI(
    title="Scanapp API",
    version="0.1.0",
    lifespan=lifespan,
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(images_router, prefix="/api/v1", tags=["images"])
app.include_router(scans_router, prefix="/api/v1", tags=["scans"])
app.include_router(cards_router, prefix="/api/v1", tags=["cards"])
