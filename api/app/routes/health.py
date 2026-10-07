from __future__ import annotations

from fastapi import APIRouter, Request

from pydantic import BaseModel

from app.db import coverage_payload
from app.schemas import HealthResponse


class ServerReadConfig(BaseModel):
    mode: str
    statuses: list[str]
    delay_ms: int
    daily_pages: int


class ScanPriceConfig(BaseModel):
    start_on_provisional: bool
    candidate_reads: int
    warm_reader: bool
    show_stale_price: bool
    stale_max_days: int
    server_read: ServerReadConfig


CAPTURE_PRESETS = ('max', 'ultraHigh', 'veryHigh', 'high')


class CaptureConfig(BaseModel):
    preset: str = 'max'
    jpeg_quality: int = 95
    max_edge: int = 2000
    native_codec: bool = False
    live_outline: bool = False


class AppConfigResponse(BaseModel):
    price_fresh_minutes: int
    config_ttl_s: int
    slab_detection: bool = False
    card_warp: bool = False
    capture: CaptureConfig = CaptureConfig()
    scan_prices: ScanPriceConfig


def scan_price_config(settings) -> AppConfigResponse:
    """Phone settings. The server still enforces the paid-read budget."""
    minutes = int(settings.cardmarket_price_fresh_minutes)
    ttl = int(settings.config_ttl_s)
    delay = int(settings.scan_price_server_read_delay_ms)
    days = int(settings.scan_price_stale_max_days)
    pages = int(settings.scan_price_server_read_daily_pages)
    return AppConfigResponse(
        price_fresh_minutes=max(1, min(minutes, 24 * 60)),
        config_ttl_s=max(30, min(ttl, 24 * 60 * 60)),
        slab_detection=bool(settings.app_slab_detection),
        card_warp=bool(settings.app_card_warp),
        capture=CaptureConfig(
            preset=settings.app_capture_preset if settings.app_capture_preset in CAPTURE_PRESETS else 'max',
            jpeg_quality=max(50, min(int(settings.app_jpeg_quality), 100)),
            max_edge=max(800, min(int(settings.app_max_edge), 4000)),
            native_codec=bool(settings.app_native_codec),
            live_outline=bool(settings.app_live_outline),
        ),
        scan_prices=ScanPriceConfig(
            start_on_provisional=bool(settings.scan_price_start_on_provisional),
            candidate_reads=settings.scan_candidate_reads(),
            warm_reader=bool(settings.scan_price_warm_reader),
            show_stale_price=bool(settings.scan_price_show_stale),
            stale_max_days=max(0, min(days, 365)),
            server_read=ServerReadConfig(
                mode=settings.scan_server_read_mode(),
                statuses=sorted(settings.scan_server_read_statuses()),
                delay_ms=max(0, min(delay, 60_000)),
                daily_pages=max(0, min(pages, 100_000)),
            ),
        ),
    )


router = APIRouter()


@router.get("/config", response_model=AppConfigResponse)
def app_config(request: Request) -> AppConfigResponse:
    """Values the phone applies at startup and again after config_ttl_s."""
    return scan_price_config(request.app.state.settings)


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    runtime = request.app.state.runtime
    dbs = request.app.state.dbs
    coverage_model = coverage_payload(dbs.catalog)
    snapshot = runtime.snapshot
    ready = runtime.ready
    return HealthResponse(
        status="ok" if ready else "not_ready",
        ready=ready,
        catalogue_version=snapshot.catalogue_version if snapshot else None,
        model_revision=snapshot.model_revision if snapshot else None,
        preprocess_config=settings.preprocess_config,
        use_ocr=settings.use_ocr,
        snapshot=settings.snapshot_name,
        coverage=coverage_model,
        detail=runtime.error,
        catalogue_backend=settings.catalogue_backend,
        catalogue_import_id=settings.planetscale_import_id if settings.catalogue_backend == "planetscale" else None,
    )
