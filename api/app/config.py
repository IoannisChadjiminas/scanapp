from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("/data")
    tmp_dir: Path = Path("/tmp/scanapp")
    preprocess_config: str = "pad"
    use_ocr: bool = True
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

    ranking_version: str = "rank-v4"
    ocr_version: str = "rapidocr-ppocrv6-small"
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

    threshold_min_visual: float = Field(default=0.78)
    threshold_min_visual_ocr: float = Field(default=0.70)
    threshold_min_gap: float = Field(default=0.04)
    threshold_blur: float = Field(default=28.0)
    threshold_min_side: int = Field(default=180)


@lru_cache
def get_settings() -> Settings:
    return Settings()
