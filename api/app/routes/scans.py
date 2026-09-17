from __future__ import annotations

import json

from fastapi import APIRouter, Form, HTTPException, Request, Response, UploadFile

from app.db import coverage_payload
from app.recognition.artifacts import ArtifactError
from app.recognition.images import ImageError
from app.recognition.pipeline import recognize_bytes
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
    acquired = await limiter.acquire()
    if not acquired:
        raise HTTPException(
            status_code=503,
            detail="Recognition is busy. Try again shortly.",
            headers={"Retry-After": "3"},
        )
    data = await image.read()
    try:
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="Upload is too large")
        return await request.app.state.loop.run_in_executor(
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
    except ArtifactError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        limiter.release()


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
    dbs.results.execute(
        """
        UPDATE scans
        SET confirmed_card_id = ?, rejected = ?
        WHERE id = ?
        """,
        (confirmed, rejected, scan_id),
    )
    dbs.results.commit()
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
        suggestions = [Candidate.model_validate(item) for item in ranking[:3]]
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
