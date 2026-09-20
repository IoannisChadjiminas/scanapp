from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Form, HTTPException, Request, Response, UploadFile

from app.cardmarket import MappingError, resolve_variant_choice
from app.db import coverage_payload
from app.recognition.artifacts import ArtifactError
from app.recognition.images import ImageError
from app.recognition.captures import apply_feedback
from app.recognition.pipeline import recognize_bytes
from app.recognition.upload import read_upload_limited
from app.schemas import (
    Candidate,
    FeedbackRequest,
    FeedbackResponse,
    ScanResponse,
)
from app.session import get_or_create_session, require_scan_owner

router = APIRouter()


@router.post("/scans", response_model=ScanResponse)
async def create_scan(
    request: Request,
    response: Response,
    image: UploadFile,
    crop_x: float | None = Form(default=None),
    crop_y: float | None = Form(default=None),
    crop_w: float | None = Form(default=None),
    crop_h: float | None = Form(default=None),
    rotation: int = Form(default=0),
    skip_detect: bool = Form(default=False),
    language: str = Form(default="auto"),
) -> ScanResponse:
    settings = request.app.state.settings
    limiter = request.app.state.scan_limiter
    session_id = get_or_create_session(
        request, response, request.app.state.dbs, settings
    )
    data = await read_upload_limited(image, settings.max_upload_bytes)
    acquired = await limiter.acquire()
    if not acquired:
        raise HTTPException(
            status_code=503,
            detail="Recognition is busy. Try again shortly.",
            headers={"Retry-After": "3"},
        )
    try:
        future = request.app.state.loop.run_in_executor(
            request.app.state.executor,
            lambda: recognize_bytes(
                data,
                settings=settings,
                runtime=request.app.state.runtime,
                catalog=request.app.state.dbs.catalog,
                results=request.app.state.dbs.results,
                session_id=session_id,
                crop_x=crop_x,
                crop_y=crop_y,
                crop_w=crop_w,
                crop_h=crop_h,
                rotation=rotation,
                skip_detect=skip_detect,
                language=language,
            ),
        )
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(future)
            except Exception:
                pass
            raise
    except ArtifactError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await limiter.release()


@router.post("/scans/{scan_id}/feedback", response_model=FeedbackResponse)
async def scan_feedback(
    scan_id: str,
    payload: FeedbackRequest,
    request: Request,
    response: Response,
) -> FeedbackResponse:
    settings = request.app.state.settings
    dbs = request.app.state.dbs
    session_id = get_or_create_session(request, response, dbs, settings)
    require_scan_owner(dbs, scan_id, session_id)
    confirmed = None
    rejected = 0
    chosen_url = payload.cardmarket_url
    if payload.action == "confirm":
        confirmed = payload.card_id
        if not confirmed:
            raise HTTPException(status_code=400, detail="card_id is required to confirm")
    elif payload.action == "correct":
        confirmed = payload.card_id
        if not confirmed:
            raise HTTPException(status_code=400, detail="card_id is required to correct")
    elif payload.action == "reject":
        rejected = 1
        chosen_url = None
    if confirmed and payload.cardmarket_url:
        try:
            picked = resolve_variant_choice(
                dbs.catalog,
                settings.data_dir,
                scanned_card_id=confirmed,
                url=payload.cardmarket_url,
            )
        except MappingError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        confirmed = str(picked["card_id"])
        chosen_url = str(picked["url"])
    dbs.results.execute(
        """
        UPDATE scans
        SET confirmed_card_id = ?, rejected = ?, chosen_cardmarket_url = ?
        WHERE id = ?
        """,
        (confirmed, rejected, chosen_url, scan_id),
    )
    dbs.results.commit()
    try:
        apply_feedback(
            settings,
            scan_id,
            action=payload.action.value,
            confirmed_card_id=confirmed,
            rejected=bool(rejected),
        )
    except Exception:  # noqa: BLE001 - review files must never fail feedback
        pass
    return FeedbackResponse(id=scan_id, action=payload.action, confirmed_card_id=confirmed)


@router.get("/session/results")
async def session_results(request: Request, response: Response) -> dict:
    from app.schemas import SessionResult, SessionResultsResponse, ScanStatus

    settings = request.app.state.settings
    dbs = request.app.state.dbs
    session_id = get_or_create_session(request, response, dbs, settings)
    rows = dbs.results.execute(
        """
        SELECT id, created_at, status, combined_ranking_json, confirmed_card_id,
               rejected, timings_json
        FROM scans
        WHERE session_id = ?
        ORDER BY created_at DESC
        """,
        (session_id,),
    ).fetchall()
    results: list[SessionResult] = []
    for row in rows:
        ranking = json.loads(row["combined_ranking_json"] or "[]")
        suggestions = [Candidate.model_validate(item) for item in ranking[:1]]
        results.append(
            SessionResult(
                scan_id=row["id"],
                created_at=row["created_at"],
                status=ScanStatus(row["status"]),
                suggestions=suggestions,
                confirmed_card_id=row["confirmed_card_id"],
                rejected=bool(row["rejected"]),
                timings_ms=json.loads(row["timings_json"] or "{}"),
            )
        )
    coverage_model = coverage_payload(dbs.catalog)
    return SessionResultsResponse(
        session_id=session_id,
        results=results,
        coverage=coverage_model,
    ).model_dump(mode="json")
