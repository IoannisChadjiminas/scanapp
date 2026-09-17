from __future__ import annotations

import json
import secrets

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse

from app.cardmarket_queue import AuthError, authenticate_helper
from app.recognition.captures import (
    case_path,
    image_file,
    list_records,
    load_cases,
    review_dir,
    with_api_image_urls,
)

router = APIRouter()


def _bearer(authorization: str | None) -> str:
    raw = (authorization or "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return ""


def _token_matches(given: str, expected: str) -> bool:
    if not given or not expected or len(given) != len(expected):
        return False
    return secrets.compare_digest(given, expected)


def require_review_access(
    request: Request,
    authorization: str | None,
    review_token: str | None,
) -> None:
    token = (review_token or "").strip() or _bearer(authorization)
    expected = str(getattr(request.app.state.settings, "review_token", "") or "").strip()
    if expected and _token_matches(token, expected):
        return
    try:
        authenticate_helper(request.app.state.dbs.catalog, token)
    except (AuthError, AttributeError):
        raise HTTPException(
            status_code=401,
            detail="Review API requires REVIEW_TOKEN or the helper credential.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


@router.get("/review")
def review_index(
    request: Request,
    authorization: str | None = Header(default=None),
    x_review_token: str | None = Header(default=None, alias="X-Review-Token"),
    needs_attention: bool | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    require_review_access(request, authorization, x_review_token)
    return list_records(
        review_dir(request.app.state.settings),
        needs_attention=needs_attention,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/review/summary", response_class=PlainTextResponse)
def review_summary(
    request: Request,
    authorization: str | None = Header(default=None),
    x_review_token: str | None = Header(default=None, alias="X-Review-Token"),
) -> str:
    require_review_access(request, authorization, x_review_token)
    path = review_dir(request.app.state.settings) / "SUMMARY.md"
    if path.is_file():
        return path.read_text()
    records = load_cases(review_dir(request.app.state.settings))
    return f"# Recognition review\n\n- scans: {len(records)}\n"


@router.get("/review/labels", response_class=PlainTextResponse)
def review_labels(
    request: Request,
    authorization: str | None = Header(default=None),
    x_review_token: str | None = Header(default=None, alias="X-Review-Token"),
) -> str:
    require_review_access(request, authorization, x_review_token)
    path = review_dir(request.app.state.settings) / "labels.jsonl"
    if not path.is_file():
        return ""
    return path.read_text()


@router.get("/review/cases/{scan_id}")
def review_case(
    scan_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    x_review_token: str | None = Header(default=None, alias="X-Review-Token"),
) -> dict:
    require_review_access(request, authorization, x_review_token)
    path = case_path(review_dir(request.app.state.settings), scan_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Review case not found")
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise HTTPException(status_code=404, detail="Review case not found")
    return with_api_image_urls(payload)


@router.get("/review/images/{filename}")
def review_image(
    filename: str,
    request: Request,
    authorization: str | None = Header(default=None),
    x_review_token: str | None = Header(default=None, alias="X-Review-Token"),
) -> FileResponse:
    require_review_access(request, authorization, x_review_token)
    path = image_file(review_dir(request.app.state.settings), filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Review image not found")
    return FileResponse(path, media_type="image/jpeg", filename=filename)
