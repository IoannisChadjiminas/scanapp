from __future__ import annotations

from fastapi import APIRouter, Request

from pydantic import BaseModel

from app.db import coverage_payload
from app.schemas import HealthResponse


class AppConfigResponse(BaseModel):
    price_fresh_minutes: int

router = APIRouter()


@router.get("/config", response_model=AppConfigResponse)
def app_config(request: Request) -> AppConfigResponse:
    """Values the phone applies on the collection screen."""
    minutes = int(request.app.state.settings.cardmarket_price_fresh_minutes)
    return AppConfigResponse(price_fresh_minutes=max(1, min(minutes, 24 * 60)))


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
    )
