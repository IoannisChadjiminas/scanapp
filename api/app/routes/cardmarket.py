from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from app.cardmarket import (
    claim_job,
    complete_job,
    enqueue_job,
    helper_is_online,
    is_job_url,
    job_by_id,
    latest_job_status,
    normalize_product_url,
    retry_or_fail_job,
    save_snapshot,
    snapshot_prices,
    touch_helper,
)

router = APIRouter()


class JobRequest(BaseModel):
    url: str
    card_id: str | None = None


class JobResponse(BaseModel):
    id: str
    url: str
    card_id: str = ""


class PriceItem(BaseModel):
    label: str
    amount: float
    currency: str = "EUR"


class OfferPayload(BaseModel):
    url: str
    job_id: str | None = None
    prices: list[PriceItem] = Field(default_factory=list)


class PriceResponse(BaseModel):
    url: str | None = None
    prices: list[PriceItem] = Field(default_factory=list)
    status: str | None = None
    helper_online: bool = False


@router.post("/cardmarket/jobs", response_model=JobResponse)
def create_job(payload: JobRequest, request: Request) -> JobResponse:
    url = normalize_product_url(payload.url)
    if not is_job_url(url):
        raise HTTPException(status_code=400, detail="Need a Cardmarket product URL")
    job_id = enqueue_job(request.app.state.dbs.catalog, url, payload.card_id)
    return JobResponse(id=job_id, url=url, card_id=payload.card_id or "")


@router.get("/cardmarket/jobs/next", response_model=None)
def next_job(request: Request) -> JobResponse | Response:
    job = claim_job(request.app.state.dbs.catalog)
    if job is None:
        return Response(status_code=204)
    return JobResponse(id=job["id"], url=job["url"], card_id=job["card_id"] or "")


@router.post("/cardmarket/helper/ping")
def ping_helper(request: Request) -> dict[str, bool]:
    touch_helper(request.app.state.dbs.catalog)
    return {"online": True}


@router.post("/cardmarket/offers")
def save_offers(payload: OfferPayload, request: Request) -> PriceResponse:
    url = normalize_product_url(payload.url)
    if not url:
        raise HTTPException(status_code=400, detail="Need a Cardmarket URL")
    prices = [item.model_dump() for item in payload.prices[:8]]
    if not prices:
        raise HTTPException(status_code=400, detail="Need at least one price")
    key = save_snapshot(request.app.state.dbs.catalog, url, prices)
    catalog = request.app.state.dbs.catalog
    if payload.job_id:
        job = job_by_id(catalog, payload.job_id)
        if job and job["url"] and job["url"] != key:
            save_snapshot(catalog, job["url"], prices)
        complete_job(catalog, payload.job_id)
    else:
        pending = catalog.execute(
            """
            SELECT id, url FROM cardmarket_jobs
            WHERE status IN ('pending', 'claimed')
            """,
        ).fetchall()
        for row in pending:
            job_url = str(row["url"] or "")
            if job_url == key or job_url == url:
                complete_job(catalog, str(row["id"]))
    return PriceResponse(
        url=key,
        prices=[PriceItem.model_validate(item) for item in prices],
        status="done",
        helper_online=True,
    )


@router.post("/cardmarket/jobs/{job_id}/fail")
def fail_job(job_id: str, request: Request) -> PriceResponse:
    job = job_by_id(request.app.state.dbs.catalog, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    status = retry_or_fail_job(request.app.state.dbs.catalog, job_id)
    return PriceResponse(url=job["url"], prices=[], status=status)


@router.get("/cardmarket/prices", response_model=PriceResponse)
def get_prices(
    request: Request, url: str = Query(min_length=8, max_length=500)
) -> PriceResponse:
    key = normalize_product_url(url)
    catalog = request.app.state.dbs.catalog
    prices = snapshot_prices(catalog, key)
    return PriceResponse(
        url=key,
        prices=[PriceItem.model_validate(item) for item in prices],
        status=latest_job_status(catalog, key),
        helper_online=helper_is_online(catalog),
    )
