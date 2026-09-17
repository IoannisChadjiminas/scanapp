from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.cardmarket import is_job_url, normalize_product_url
from app.cardmarket_queue import (
    AuthError,
    QueueError,
    authenticate_helper,
    claim_job,
    complete_job,
    enqueue_job,
    prices_payload,
    queue_counts,
    recover_job,
    release_job,
    renew_claim,
    retry_or_fail_job,
    update_helper_status,
)

router = APIRouter()


class JobRequest(BaseModel):
    url: str
    card_id: str | None = None
    filters: dict[str, str] = Field(default_factory=dict)


class JobResponse(BaseModel):
    id: str
    url: str
    card_id: str = ""
    claim_token: str | None = None
    claim_expires_at: str | None = None
    filters: dict[str, str] = Field(default_factory=dict)
    product_identity: str | None = None
    attempts: int = 0
    status: str | None = None


class PriceItem(BaseModel):
    label: str
    amount: float
    currency: str = "EUR"


class CompleteRequest(BaseModel):
    job_id: str
    claim_token: str
    submission_id: str
    url: str
    prices: list[PriceItem] = Field(default_factory=list)
    empty: bool = False
    observed_at: str | None = None
    parser_version: str | None = None
    sampled_offer_count: int | None = None


class ClaimRequest(BaseModel):
    job_id: str | None = None
    claim_token: str | None = None


class ClaimActionRequest(BaseModel):
    job_id: str
    claim_token: str


class ReleaseRequest(ClaimActionRequest):
    reason: str | None = None


class FailRequest(ReleaseRequest):
    reason: str
    terminal: bool = False


class HelperStatusRequest(BaseModel):
    ready: bool | None = None
    paused: bool | None = None
    attention: str | None = None
    current_job_id: str | None = None
    current_card: str | None = None
    success: bool | None = None
    failure_reason: str | None = None


class PriceResponse(BaseModel):
    url: str | None = None
    prices: list[PriceItem] = Field(default_factory=list)
    status: str | None = None
    helper_online: bool = False
    helper_ready: bool = False
    helper_paused: bool = False
    helper_attention: str | None = None
    observed_at: str | None = None
    sampled_offer_count: int | None = None
    freshness: str | None = None
    queued: int | None = None
    pending: int | None = None
    claimed: int | None = None
    helper_id: str | None = None
    idempotent: bool | None = None


def _bearer_token(authorization: str | None) -> str | None:
    raw = (authorization or "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return None


def _helper(conn, authorization: str | None) -> dict[str, str]:
    try:
        return authenticate_helper(conn, _bearer_token(authorization))
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _raise_queue(exc: QueueError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _job_response(job: dict[str, Any]) -> JobResponse:
    return JobResponse(
        id=str(job["id"]),
        url=str(job["url"]),
        card_id=str(job.get("card_id") or ""),
        claim_token=job.get("claim_token"),
        claim_expires_at=job.get("claim_expires_at"),
        filters=job.get("filters") or {},
        product_identity=job.get("product_identity"),
        attempts=int(job.get("attempts") or 0),
        status=job.get("status"),
    )


def _price_response(payload: dict[str, Any]) -> PriceResponse:
    prices = [PriceItem.model_validate(item) for item in payload.get("prices") or []]
    return PriceResponse(
        url=payload.get("url"),
        prices=prices,
        status=payload.get("status"),
        helper_online=bool(payload.get("helper_online")),
        helper_ready=bool(payload.get("helper_ready")),
        helper_paused=bool(payload.get("helper_paused")),
        helper_attention=payload.get("helper_attention"),
        observed_at=payload.get("observed_at"),
        sampled_offer_count=payload.get("sampled_offer_count"),
        freshness=payload.get("freshness"),
        queued=payload.get("queued"),
        pending=payload.get("pending"),
        claimed=payload.get("claimed"),
        helper_id=payload.get("helper_id"),
        idempotent=payload.get("idempotent"),
    )


@router.post("/cardmarket/jobs", response_model=JobResponse)
def create_job(payload: JobRequest, request: Request) -> JobResponse:
    url = normalize_product_url(payload.url)
    if not is_job_url(url):
        raise HTTPException(status_code=400, detail="Need a Cardmarket product URL")
    try:
        job_id = enqueue_job(
            request.app.state.dbs.catalog,
            payload.url,
            payload.card_id,
            payload.filters or None,
        )
    except QueueError as exc:
        _raise_queue(exc)
    job = {
        "id": job_id,
        "url": url,
        "card_id": payload.card_id or "",
        "filters": payload.filters or {},
        "status": "pending",
    }
    return _job_response(job)


@router.post("/cardmarket/helper/claim", response_model=None)
def helper_claim(
    request: Request,
    payload: ClaimRequest | None = None,
    authorization: str | None = Header(default=None),
):
    catalog = request.app.state.dbs.catalog
    helper = _helper(catalog, authorization)
    body = payload or ClaimRequest()
    try:
        recovered = recover_job(catalog, helper["helper_id"], body.job_id, body.claim_token)
        job = recovered or claim_job(catalog, helper["helper_id"])
    except QueueError as exc:
        _raise_queue(exc)
    if job is None:
        counts = queue_counts(catalog)
        return _price_response({"status": "idle", **counts})
    return _job_response(job)


@router.post("/cardmarket/helper/renew", response_model=JobResponse)
def helper_renew(
    payload: ClaimActionRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> JobResponse:
    catalog = request.app.state.dbs.catalog
    helper = _helper(catalog, authorization)
    try:
        job = renew_claim(catalog, helper["helper_id"], payload.job_id, payload.claim_token)
    except QueueError as exc:
        _raise_queue(exc)
    return _job_response(job)


@router.post("/cardmarket/helper/complete", response_model=PriceResponse)
def helper_complete(
    payload: CompleteRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> PriceResponse:
    catalog = request.app.state.dbs.catalog
    helper = _helper(catalog, authorization)
    prices = [item.model_dump() for item in payload.prices[:8]]
    try:
        result = complete_job(
            catalog,
            helper["helper_id"],
            payload.job_id,
            payload.claim_token,
            submission_id=payload.submission_id,
            url=payload.url,
            prices=prices,
            empty=payload.empty,
            observed_at=payload.observed_at,
            parser_version=payload.parser_version,
            sampled_offer_count=payload.sampled_offer_count,
        )
    except QueueError as exc:
        _raise_queue(exc)
    update_helper_status(
        catalog,
        helper["helper_id"],
        ready=True,
        attention=None,
        current_job_id=None,
        success=True,
    )
    return _price_response(result)


@router.post("/cardmarket/helper/fail", response_model=PriceResponse)
def helper_fail(
    payload: FailRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> PriceResponse:
    catalog = request.app.state.dbs.catalog
    helper = _helper(catalog, authorization)
    if payload.reason == "challenge":
        try:
            released = release_job(
                catalog,
                helper["helper_id"],
                payload.job_id,
                payload.claim_token,
                reason=payload.reason,
            )
        except QueueError as exc:
            _raise_queue(exc)
        update_helper_status(
            catalog,
            helper["helper_id"],
            ready=False,
            paused=True,
            attention="challenge",
            current_job_id=None,
            success=False,
            failure_reason="challenge",
        )
        return PriceResponse(url=released.get("url"), status=released.get("status"))
    try:
        status = retry_or_fail_job(
            catalog,
            payload.job_id,
            helper_id=helper["helper_id"],
            claim_token=payload.claim_token,
            reason=payload.reason,
            terminal=payload.terminal or payload.reason == "wrong_product",
        )
    except QueueError as exc:
        _raise_queue(exc)
    update_helper_status(
        catalog,
        helper["helper_id"],
        current_job_id=None,
        success=False,
        failure_reason=payload.reason,
        attention="challenge" if payload.reason == "challenge" else None,
    )
    return PriceResponse(status=status)


@router.post("/cardmarket/helper/release", response_model=PriceResponse)
def helper_release(
    payload: ReleaseRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> PriceResponse:
    catalog = request.app.state.dbs.catalog
    helper = _helper(catalog, authorization)
    try:
        released = release_job(
            catalog,
            helper["helper_id"],
            payload.job_id,
            payload.claim_token,
            reason=payload.reason,
        )
    except QueueError as exc:
        _raise_queue(exc)
    return PriceResponse(url=released.get("url"), status=released.get("status"))


@router.post("/cardmarket/helper/status", response_model=PriceResponse)
def helper_status(
    payload: HelperStatusRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> PriceResponse:
    catalog = request.app.state.dbs.catalog
    helper = _helper(catalog, authorization)
    state = update_helper_status(
        catalog,
        helper["helper_id"],
        ready=payload.ready,
        paused=payload.paused,
        attention=payload.attention,
        current_job_id=payload.current_job_id,
        success=payload.success,
        failure_reason=payload.failure_reason,
    )
    return _price_response(state)


@router.get("/cardmarket/prices", response_model=PriceResponse)
def get_prices(
    request: Request, url: str = Query(min_length=8, max_length=500)
) -> PriceResponse:
    return _price_response(prices_payload(request.app.state.dbs.catalog, url))