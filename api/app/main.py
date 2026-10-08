from __future__ import annotations

import asyncio
import logging
import faulthandler
import signal
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


class _SkipHealthAccess(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            path = str(record.args[2]).split("?", 1)[0]
            return path not in {"/health", "/api/v1/health"}
        message = record.getMessage()
        return "GET /health " not in message and "GET /api/v1/health " not in message


def _quiet_health_access() -> None:
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, _SkipHealthAccess) for item in access.filters):
        access.addFilter(_SkipHealthAccess())


_quiet_health_access()

from app.admission import ScanLimiter
from app.cardmarket_events import bind_loop
from app.cardmarket_daily import run_once, should_schedule
from app.cardmarket_scraper import LanePool

log = logging.getLogger("cardmarket.daily")


def _seconds_until_utc_day() -> float:
    now = time.time()
    return max(1.0, (int(now) // 86400 + 1) * 86400 - now)


async def _price_sources(stop: asyncio.Event, catalog=None) -> None:
    """Import Cardmarket's price file and TCGdex prices once a day.

    The guide file is written around 02:50 CET, so the pass runs a little after
    00:00 UTC and again every day. A failed source keeps the older data.
    """
    from app.price_sources import refresh_all_on_own_connection

    while not stop.is_set():
        settings = get_settings()
        try:
            await asyncio.to_thread(refresh_all_on_own_connection, settings, catalog)
        except Exception as exc:
            log.info("price sources pass failed error=%s", type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=_seconds_until_utc_day() + 3 * 3600)
        except TimeoutError:
            continue
        return


async def _daily_prices(stop: asyncio.Event) -> None:
    """Refresh holdings, then wait for the next UTC day. A restart continues the remainder."""
    while not stop.is_set():
        settings = get_settings()
        if not should_schedule(settings):
            return
        try:
            status = await asyncio.to_thread(run_once, settings)
        except Exception as exc:
            log.info("daily pass failed error=%s", type(exc).__name__)
            status = "blocked"
        delay = _seconds_until_utc_day() if status in {"done", "capped"} else 60
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
        except TimeoutError:
            continue
        return
from app.config import get_settings
from app.db import Databases
from app.recognition.runtime import Runtime
from app.routes.cardmarket import router as cardmarket_router
from app.routes.cards import router as cards_router
from app.routes.health import router as health_router
from app.routes.images import router as images_router
from app.routes.review import router as review_router
from app.routes.scans import router as scans_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    _quiet_health_access()
    if hasattr(faulthandler, "register") and hasattr(signal, "SIGUSR1"):
        # Dumps stacks, not local variables or secrets, even if the GIL stalls.
        faulthandler.register(signal.SIGUSR1, all_threads=True)
    settings = get_settings()
    logging.getLogger("cardmarket.scraper").info(
        "price config webview_enabled=%s helper_enabled=%s scraper_enabled=%s "
        "scraper_url_configured=%s scraper_key_configured=%s daily_pages=%s daily_mb=%s",
        settings.cardmarket_webview_enabled,
        settings.cardmarket_helper_enabled,
        settings.scraper_enabled,
        bool(settings.scraper_url),
        bool(settings.scraper_api_key),
        settings.scraper_daily_pages,
        settings.scraper_daily_mb,
    )
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    dbs = Databases(settings)
    runtime = Runtime(settings=settings)
    runtime.load(dbs.cloud_snapshot)
    runtime.bind_card_languages(dbs.catalog)
    app.state.settings = settings
    app.state.dbs = dbs
    app.state.runtime = runtime
    app.state.scan_limiter = ScanLimiter(settings.scan_wait_limit)
    app.state.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scan")
    app.state.image_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="image")
    app.state.loop = asyncio.get_running_loop()
    bind_loop(app.state.loop)
    worker = LanePool(settings) if settings.scraper_enabled and settings.lane_urls else None
    if worker is not None:
        worker.start()
    app.state.scraper_worker = worker
    daily_stop = asyncio.Event()
    daily_task = asyncio.create_task(_daily_prices(daily_stop)) if should_schedule(settings) else None
    sources_task = None
    if settings.price_guide_enabled or settings.tcgdex_prices_enabled:
        sources_task = asyncio.create_task(_price_sources(daily_stop, dbs.catalog))
    try:
        yield
    finally:
        daily_stop.set()
        if daily_task is not None:
            daily_task.cancel()
        if sources_task is not None:
            sources_task.cancel()
        if worker is not None:
            worker.stop()
        bind_loop(None)
        from app.recognition.progress import drain_scan_streams
        await drain_scan_streams()
        app.state.executor.shutdown(wait=False, cancel_futures=True)
        app.state.image_executor.shutdown(wait=False, cancel_futures=True)
        runtime.close()
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
    allow_origin_regex=r"chrome-extension://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def scan_diagnostics(request, call_next):
    if request.method != "POST" or request.url.path != "/api/v1/scans":
        return await call_next(request)
    trace = request.headers.get("x-scan-trace", "")
    if not trace or len(trace) > 64 or any(c not in "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_" for c in trace):
        trace = str(uuid.uuid4())
    logger = logging.getLogger("scan.diagnostics")
    request.state.scan_trace = trace
    started = time.perf_counter()
    logger.info("request_start trace=%s", trace)
    try:
        response = await call_next(request)
        response.headers["X-Scan-Trace"] = trace
        logger.info("request_done trace=%s status=%s elapsed_ms=%.1f", trace, response.status_code, (time.perf_counter()-started)*1000)
        return response
    except Exception as exc:
        # Never include exception text, request bodies, cookies or URLs.
        logger.error("request_failed trace=%s error_type=%s elapsed_ms=%.1f", trace, type(exc).__name__, (time.perf_counter()-started)*1000)
        raise

from app.planetscale import CatalogueReadOnly


@app.exception_handler(CatalogueReadOnly)
async def catalogue_read_only(request, exc):
    return JSONResponse(status_code=409, content={"detail": str(exc)})

app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(images_router, prefix="/api/v1", tags=["images"])
app.include_router(review_router, prefix="/api/v1", tags=["review"])
app.include_router(scans_router, prefix="/api/v1", tags=["scans"])
app.include_router(cards_router, prefix="/api/v1", tags=["cards"])
app.include_router(cardmarket_router, prefix="/api/v1", tags=["cardmarket"])
