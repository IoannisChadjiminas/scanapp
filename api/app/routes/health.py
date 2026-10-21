from __future__ import annotations

from fastapi import APIRouter, Request

from pydantic import BaseModel, Field

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
    auto_capture: bool = False
    native_camera: bool = False
    native_camera_android: bool = False
    card_anywhere: bool = True
    # The phone's own check of each photo, with the server's blur limit.
    photo_check: bool = True
    min_sharpness: float = 40.0
    sharpness_edge: int = 1000
    max_glare: float = 0.08
    auto_retakes: int = 2


class AppConfigResponse(BaseModel):
    search_presets: list[dict] = Field(default_factory=list)
    search_history: dict[str, bool] = Field(default_factory=dict)
    price_fresh_minutes: int
    listing_max_age_s: int = 7 * 86400
    config_ttl_s: int
    slab_detection: bool = False
    # Send the phone's own read of the card's name and number as client_text.
    client_text: bool = False
    # Slab label fields, a phone embedding, and photo quality. Logged only.
    client_label: bool = False
    client_embedding: bool = False
    client_quality: bool = False
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
    from app.routes.cards import SEARCH_PRESETS

    return AppConfigResponse(
        search_presets=SEARCH_PRESETS,
        price_fresh_minutes=max(1, min(minutes, 24 * 60)),
        listing_max_age_s=max(1, min(int(settings.cardmarket_listing_max_age_days), 90)) * 86400,
        config_ttl_s=max(30, min(ttl, 24 * 60 * 60)),
        slab_detection=bool(settings.app_slab_detection),
        client_text=bool(getattr(settings, 'app_client_text', False)),
        client_label=bool(getattr(settings, 'app_client_label', False)),
        client_embedding=bool(getattr(settings, 'app_client_embedding', False)),
        client_quality=bool(getattr(settings, 'app_client_quality', False)),
        card_warp=bool(settings.app_card_warp),
        capture=CaptureConfig(
            preset=settings.app_capture_preset if settings.app_capture_preset in CAPTURE_PRESETS else 'max',
            jpeg_quality=max(50, min(int(settings.app_jpeg_quality), 100)),
            max_edge=max(800, min(int(settings.app_max_edge), 4000)),
            native_codec=bool(settings.app_native_codec),
            live_outline=bool(settings.app_live_outline),
            auto_capture=bool(settings.app_live_outline and settings.app_auto_capture),
            native_camera=bool(settings.app_native_camera),
            native_camera_android=bool(settings.app_native_camera_android),
            card_anywhere=bool(settings.app_card_anywhere),
            photo_check=bool(settings.app_photo_check),
            min_sharpness=max(0.0, float(settings.threshold_blur)),
            sharpness_edge=max(200, min(int(settings.threshold_blur_edge or 1000), 4000)),
            max_glare=max(0.0, min(float(settings.app_max_glare), 1.0)),
            auto_retakes=max(0, min(int(settings.app_auto_retakes), 5)),
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
    config = scan_price_config(request.app.state.settings)
    from app.market_stats import capabilities
    flags = capabilities(request.app.state.dbs.catalog)
    config.search_history = flags
    if flags['change_7d']:
        config.search_presets = [dict(item, params=dict(item['params'], sort='change_7d_asc')) if item['id']=='biggest_drops' else item for item in config.search_presets]
    if flags['change_30d'] and flags['liquidity_30d']:
        config.search_presets = [*config.search_presets, {'id':'steady_climbers', 'label':'Steady climbers', 'icon':'trending_up', 'params':{'preset':'steady_climbers','sort':'change_30d'}}]
    return config


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
        stage1_answers=getattr(getattr(request.app.state, 'stage1_checker', None), 'answers', 0),
        stage1_checks=getattr(getattr(request.app.state, 'stage1_checker', None), 'checks', 0),
        stage1_disagreements=getattr(getattr(request.app.state, 'stage1_checker', None), 'disagreements', 0),
    )
