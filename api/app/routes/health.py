from __future__ import annotations

from fastapi import APIRouter, Request

from app.db import coverage
from app.schemas import Coverage, HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    runtime = request.app.state.runtime
    dbs = request.app.state.dbs
    cards, indexed, missing = coverage(dbs.catalog)
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
        coverage=Coverage(cards=cards, indexed=indexed, missing_images=missing),
        detail=runtime.error,
    )
