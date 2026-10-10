from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Form, HTTPException, Request, Response, UploadFile

from app.client_diagnostics import phone_diagnostic_lines
from app.cardmarket import (
    MappingError, normalize_product_url, resolve_variant_choice, url_for_row, variants_for_row,
)
from app.db import coverage_payload
from app.recognition.artifacts import ArtifactError
from app.recognition.images import ImageError
from app.recognition.captures import apply_feedback
from app.recognition.pipeline import recognize_bytes
from app.recognition.grading_completion import schedule_grading_completion
from app.recognition.presentation import match_presentation
from app.recognition.progress import scan_stream
from app.recognition.upload import read_upload_limited
from app.scan_summary import parse_quad, scan_flags, scan_outcome_line, scan_source, scan_summary_line
from app.schemas import (
    Candidate,
    FeedbackRequest,
    FeedbackResponse,
    ScanResponse,
)
from app.session import get_or_create_session, require_scan_owner

router = APIRouter()


@router.post("/diagnostics", status_code=204)
async def phone_diagnostics(request: Request, response: Response) -> Response:
    """Accept a short batch of phone timings. The scan itself never waits on this."""
    logger = logging.getLogger("scan.diagnostics")
    try:
        payload = await request.json()
        lines = phone_diagnostic_lines(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="diagnostics body must be JSON") from exc
    get_or_create_session(request, response, request.app.state.dbs, request.app.state.settings)
    for line in lines:
        logger.info("%s", line)
    return Response(status_code=204)


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
    graded: bool | None = Form(default=None),
    stream_results: bool = Form(default=False),
    # Where the scan came from. All optional; used for logs and comparisons only.
    platform: str | None = Form(default=None),
    capture: str | None = Form(default=None),
    camera: str | None = Form(default=None),
    app_build: str | None = Form(default=None),
    locale: str | None = Form(default=None),
    card_quad: str | None = Form(default=None),
    quad_source: str | None = Form(default=None),
) -> ScanResponse | Response:
    settings = request.app.state.settings
    started = time.perf_counter()
    logger = logging.getLogger("scan.diagnostics")
    trace = getattr(request.state, "scan_trace", "none")
    limiter = request.app.state.scan_limiter
    session_id = get_or_create_session(
        request, response, request.app.state.dbs, settings
    )
    data = await read_upload_limited(image, settings.max_upload_bytes)
    logger.info("upload_read trace=%s bytes=%s elapsed_ms=%.1f", trace, len(data), (time.perf_counter()-started)*1000)
    acquired = await limiter.acquire()
    if not acquired:
        raise HTTPException(
            status_code=503,
            detail="Recognition is busy. Try again shortly.",
            headers={"Retry-After": "3"},
        )
    def recognize(observer=None):
        return recognize_bytes(
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
            skip_detect=skip_detect and not detect_on_server,
            language=language,
            graded=graded,
            locale=locale,
            card_quad=parse_quad(card_quad),
            _progress_observer=observer,
            _grading_completion=lambda scan_id, job: schedule_grading_completion(
                request.app.state.loop, request.app.state.dbs.results, scan_id, job),
        )

    streaming = bool(stream_results and settings.scan_stream_results)
    source = scan_source(platform=platform, capture=capture, camera=camera, app_build=app_build,
                         locale=locale, card_quad=card_quad, quad_source=quad_source)
    flags = scan_flags(settings, stream=streaming, skip_detect=skip_detect, graded=graded)
    # A phone-flattened photo is only trusted once TRUST_CLIENT_WARP is on.
    detect_on_server = skip_detect and not settings.trust_client_warp
    if detect_on_server:
        flags.append('server_detect_override')

    def log_summary(result: ScanResponse) -> None:
        logger.info("%s", scan_summary_line(result, settings, trace=trace,
                                            upload_bytes=len(data), flags=flags, source=source))

    def after_stream(result: ScanResponse) -> None:
        log_summary(result)
        schedule_parallel_read(result)

    def schedule_parallel_read(result: ScanResponse) -> None:
        from app.cardmarket_queue import schedule_scan_parallel_read

        top = result.suggestions[0].cardmarket_url if result.suggestions else None
        schedule_scan_parallel_read(
            request.app.state.dbs.catalog,
            status=result.status.value,
            url=top,
        )

    if streaming:
        # The stream owns the admission slot from here and releases it itself.
        return scan_stream(loop=request.app.state.loop, executor=request.app.state.executor,
            limiter=limiter, response=response, trace=trace,
            recognize=recognize, on_final=after_stream)
    try:
        future = request.app.state.loop.run_in_executor(
            request.app.state.executor, recognize)
        try:
            result = await asyncio.shield(future)
            logger.info("recognition_done trace=%s scan_id=%s status=%s timings_ms=%s", trace, result.id, result.status.value, result.timings_ms.model_dump() if hasattr(result.timings_ms, "model_dump") else result.timings_ms)
            try:
                log_summary(result)
            except Exception:
                logger.exception("scan summary failed trace=%s", trace)
            try:
                schedule_parallel_read(result)
            except Exception:
                logger.exception("scan parallel schedule failed trace=%s", trace)
            return result
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


@router.get("/scans/{scan_id}/grading")
async def scan_grading(scan_id: str, request: Request, response: Response) -> dict:
    dbs = request.app.state.dbs
    session_id = get_or_create_session(request, response, dbs, request.app.state.settings)
    require_scan_owner(dbs, scan_id, session_id)
    row = dbs.results.execute("SELECT ocr_json FROM scans WHERE id=?", (scan_id,)).fetchone()
    return {"scan_id": scan_id, "grading": json.loads(row['ocr_json'] or '{}').get('grading', {})}


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
    saved_scan = dbs.results.execute("SELECT status, ocr_json, confirmed_card_id, combined_ranking_json FROM scans WHERE id = ?", (scan_id,)).fetchone()
    if payload.action == "confirm" and saved_scan["status"] in {"retake", "no_match", "failed"} and payload.card_id != saved_scan["confirmed_card_id"]:
        raise HTTPException(status_code=409, detail="This scan has no verified suggestion. Retake or use manual correction.")
    if payload.action == "confirm" and saved_scan["status"] == "printing_ambiguous":
        review = json.loads(saved_scan["ocr_json"] or "{}").get("printing_review") or {}
        offered = {r["card_id"] for r in review.get("plausible_printings", [])}
        if saved_scan["confirmed_card_id"]:
            offered.add(saved_scan["confirmed_card_id"])
        if not payload.printing_selected or payload.card_id not in offered:
            raise HTTPException(status_code=409, detail="Choose an offered printing explicitly, or use manual correction.")
        if dbs.catalog.execute("SELECT 1 FROM cards WHERE id=?", (payload.card_id,)).fetchone() is None:
            raise HTTPException(status_code=409, detail="The selected printing is no longer in this catalogue.")
        selected_row = dbs.catalog.execute("SELECT * FROM cards WHERE id=?", (payload.card_id,)).fetchone()
        finish_choices = variants_for_row(dbs.catalog, selected_row)
        if len(finish_choices) >= 2 and not payload.cardmarket_url:
            raise HTTPException(status_code=409, detail="Choose this printing's finish explicitly.")
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
        if saved_scan["status"] == "printing_ambiguous" and payload.action == "confirm":
            # Manual printing selection may choose only this printing's
            # identity-filtered finish links. Do not learn a new mapping from
            # an arbitrary pasted URL, even with an editable local catalogue.
            allowed = {item["url"] for item in finish_choices}
            primary_url = url_for_row(selected_row)
            if primary_url:
                allowed.add(primary_url)
            if normalize_product_url(payload.cardmarket_url) not in allowed:
                raise HTTPException(status_code=409, detail="Choose a validated finish belonging to the selected printing.")
        try:
            picked = resolve_variant_choice(
                dbs.catalog,
                settings.data_dir,
                scanned_card_id=confirmed,
                url=payload.cardmarket_url,
            )
        except MappingError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        if saved_scan["status"] == "printing_ambiguous" and payload.action == "confirm":
            # A finish URL must not silently switch the explicitly selected
            # printing to a same-name card in a different set.
            selected = dbs.catalog.execute("SELECT set_name,collector_number,language FROM cards WHERE id=?", (confirmed,)).fetchone()
            owner = dbs.catalog.execute("SELECT set_name,collector_number,language FROM cards WHERE id=?", (picked["card_id"],)).fetchone()
            if selected is None or owner is None or tuple(selected) != tuple(owner):
                raise HTTPException(status_code=409, detail="The chosen listing belongs to a different printing. Choose its set explicitly.")
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
        logging.getLogger("scan.diagnostics").info("%s", scan_outcome_line(
            scan_id, action=payload.action.value, chosen=confirmed,
            status=saved_scan["status"], combined_ranking_json=saved_scan["combined_ranking_json"]))
    except Exception:  # noqa: BLE001 - logging must never fail feedback
        pass
    try:
        # File writes stay off the event loop; the review index rebuilds later.
        await asyncio.to_thread(
            apply_feedback,
            settings,
            scan_id,
            action=payload.action.value,
            confirmed_card_id=confirmed,
            rejected=bool(rejected),
            rebuild_index=False,
        )
    except Exception:  # noqa: BLE001 - review files must never fail feedback
        pass
    return FeedbackResponse(id=scan_id, action=payload.action, confirmed_card_id=confirmed)


@router.get("/session/results")
async def session_results(request: Request, response: Response) -> dict:
    from app.schemas import MatchPresentation, PrintingReview, SessionResult, SessionResultsResponse, ScanStatus

    settings = request.app.state.settings
    dbs = request.app.state.dbs
    session_id = get_or_create_session(request, response, dbs, settings)
    rows = dbs.results.execute(
        """
        SELECT id, created_at, status, combined_ranking_json, confirmed_card_id,
               rejected, timings_json, chosen_cardmarket_url, ocr_json
        FROM scans
        WHERE session_id = ?
        ORDER BY created_at DESC
        """,
        (session_id,),
    ).fetchall()
    results: list[SessionResult] = []
    for row in rows:
        ranking = json.loads(row["combined_ranking_json"] or "[]")
        shown = [] if row["status"] in {"retake", "no_match", "failed"} else ranking[:1]
        suggestions = [Candidate.model_validate(item) for item in shown]
        evidence = json.loads(row['ocr_json'] or '{}')
        review = PrintingReview.model_validate(evidence['printing_review']) if evidence.get('printing_review') else None
        # Persist new responses exactly; derive the additive display fields for
        # legacy scans without changing their ranking/status/feedback.
        presentation = (MatchPresentation.model_validate(evidence['match_presentation'])
            if evidence.get('match_presentation') else match_presentation(ranking,
                status=row['status'], printing_review=review,
                min_visual=settings.threshold_min_visual_ocr))
        results.append(
            SessionResult(
                scan_id=row["id"],
                created_at=row["created_at"],
                status=ScanStatus(row["status"]),
                suggestions=suggestions,
                confirmed_card_id=row["confirmed_card_id"],
                chosen_cardmarket_url=row["chosen_cardmarket_url"],
                rejected=bool(row["rejected"]),
                timings_ms=json.loads(row["timings_json"] or "{}"),
                printing_review=review,
                confidence=evidence.get("confidence"),
                grading=evidence.get("grading") or {},
                **presentation.model_dump(mode='json'),
            )
        )
    coverage_model = coverage_payload(dbs.catalog)
    return SessionResultsResponse(
        session_id=session_id,
        results=results,
        coverage=coverage_model,
    ).model_dump(mode="json")
