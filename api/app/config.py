from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("/data")
    catalogue_backend: str = "sqlite"
    planetscale_database_url: SecretStr = SecretStr("")
    # Writable portfolio store: PlanetScale database pokesingle-product.
    # Empty keeps holdings in the local catalogue file for tests.
    portfolio_database_url: SecretStr = SecretStr("")
    planetscale_schema: str = "pokesingle_import_20261001"
    planetscale_import_id: str = "PS-IMPORT-001-20261001"
    tmp_dir: Path = Path("/tmp/scanapp")
    preprocess_config: str = "pad"
    use_ocr: bool = True
    use_grading: bool = True
    # Opt-in: a separate OCR engine overlaps label work with card recognition.
    parallel_grading: bool = False
    # Return at card completion; unfinished/unidentified grading defaults Raw.
    grading_at_card_deadline: bool = False
    # Label OCR competes with card OCR for CPU. When on, grade only uploads
    # whose client sent graded=true. Off, the hint is ignored and logged so a
    # rollout can compare it with what grading found.
    grading_requires_client_hint: bool = False
    # Retrieval windows may omit metadata. Try the supplied card-shaped frame
    # for OCR first, without changing the visual/artwork retrieval crop.
    ocr_complete_frame_first: bool = False
    # Keep initial OCR unchanged; omit optional footer retries only for a
    # strongly supported, reviewable identity. Never certify its printing.
    ocr_adaptive_footer: bool = False
    # Requires ocr_adaptive_footer. Read only the title strip when the visual
    # leader has exactly one same-art printing and both visual streams agree.
    # A policy change: replay the frozen panel before enabling it.
    ocr_title_only_single_printing: bool = False
    # One isolated footer reader overlaps initial title/footer inference.
    # Its auxiliary CPU lane is shared with optional grading, not added to it.
    ocr_parallel_regions: bool = False
    # Optional NDJSON progress stream; legacy scans remain a single JSON response.
    scan_stream_results: bool = False
    enable_matched: bool = True
    ort_intra_threads: int = 1
    ort_inter_threads: int = 1
    max_image_pixels: int = 12_000_000
    max_upload_bytes: int = 12_582_912
    scan_wait_limit: int = 2
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    session_cookie: str = "scanapp_session"
    session_ttl_days: int = 30
    store_captures: bool = True
    review_token: str = ""
    session_create_hourly: int = 30
    cardmarket_helper_enabled: bool = False
    cardmarket_webview_enabled: bool = True
    cardmarket_challenge_fallback_minutes: int = 10
    cardmarket_price_fresh_minutes: int = 15
    scraper_enabled: bool = False
    scraper_url: str = ""
    scraper_api_key: str = ""
    scraper_session_hourly: int = 10
    scraper_ip_hourly: int = 20
    scraper_daily_pages: int = 50
    scraper_daily_mb: int = 50
    scraper_reserve_kb: int = 500
    scraper_url_cooldown_s: int = 1800
    scraper_attempt_seconds: int = 70
    scraper_page_gap_s: float = 0
    scraper_browser_lifetime_s: float = 1800
    scraper_urls: str = ""
    cardmarket_interactive_start_s: int = 30
    scraper_interactive_reserve_pages: int = 0
    scraper_breaker_failures: int = 3
    scraper_breaker_base_s: float = 30
    scraper_breaker_max_s: float = 300
    daily_prices_enabled: bool = False
    daily_gap_min_s: float = 2
    daily_gap_max_s: float = 60
    daily_gap_step_s: float = 5
    daily_session_pages: int = 30
    daily_session_rotate_before_s: float = 120
    daily_browsers: int = 1
    photo_scrape_active: bool = False
    config_ttl_s: int = 600
    # Tell the phone (GET /config) to look for a graded slab on each photo and
    # send graded=true/false. Off until switched on here, no app rebuild.
    app_slab_detection: bool = False
    # Phone photo prep, sent through GET /config. Defaults match the app today.
    app_capture_preset: str = 'max'
    app_jpeg_quality: int = 95
    app_native_codec: bool = False
    # Tell the phone to find and flatten the card before upload.
    app_card_warp: bool = False
    # Honour skip_detect from the phone. Off: the server still runs its own
    # detection on a phone-flattened photo, so both can be compared first.
    trust_client_warp: bool = False
    scan_price_start_on_provisional: bool = True
    scan_price_candidate_reads: int = 2
    scan_price_warm_reader: bool = True
    scan_price_show_stale: bool = True
    scan_price_stale_max_days: int = 30
    # off: never. fallback: the phone asks after its own read fails.
    # parallel: the server queues a paid read when a confident scan has no fresh price.
    scan_price_server_read: str = "fallback"
    scan_price_server_read_statuses: str = "matched"
    scan_price_server_read_delay_ms: int = 3000
    scan_price_server_read_daily_pages: int = 0

    ranking_version: str = "rank-v15-holder-printing-review"
    # Opt-in only; an invalid explicitly configured bundle fails validation.
    artwork_bundle_dir: Path | None = None
    # Immutable, catalogue-bound local geometry/printing probes. Opt-in only.
    reference_features_dir: Path | None = None
    ocr_version: str = "rapidocr-ppocrv6-small-regions-v7-layout-orientation"
    model_name: str = "dinov2-small"

    @property
    def catalog_sqlite(self) -> Path:
        return self.data_dir / "catalog.sqlite"

    @property
    def results_sqlite(self) -> Path:
        return self.data_dir / "results.sqlite"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def vectors_dir(self) -> Path:
        return self.data_dir / "vectors" / self.snapshot_name

    @property
    def snapshot_name(self) -> str:
        return self.preprocess_config

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "reference-images"

    @property
    def review_dir(self) -> Path:
        return self.data_dir / "review"

    @property
    def dinov2_path(self) -> Path:
        return self.models_dir / "dinov2_small.onnx"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def lane_urls(self) -> list[str]:
        raw = [item.strip() for item in self.scraper_urls.split(",") if item.strip()]
        if raw:
            return raw
        return [self.scraper_url] if self.scraper_url else []

    def scan_candidate_reads(self) -> int:
        return max(0, min(int(self.scan_price_candidate_reads), 3))

    def scan_server_read_mode(self) -> str:
        mode = (self.scan_price_server_read or "").strip().lower()
        if mode in {"off", "fallback", "parallel"}:
            return mode
        return "fallback"

    def scan_server_read_statuses(self) -> set[str]:
        return {
            item.strip()
            for item in self.scan_price_server_read_statuses.split(",")
            if item.strip()
        }

    def interactive_reserve_pages(self) -> int:
        if self.scraper_interactive_reserve_pages > 0:
            return self.scraper_interactive_reserve_pages
        return max(1, int(self.scraper_daily_pages * 0.2)) if self.scraper_daily_pages else 0

    threshold_min_visual: float = Field(default=0.78)
    threshold_min_visual_ocr: float = Field(default=0.70)
    threshold_min_gap: float = Field(default=0.04)
    threshold_blur: float = Field(default=28.0)
    threshold_min_side: int = Field(default=180)


@lru_cache
def get_settings() -> Settings:
    return Settings()
