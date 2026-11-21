"""Graded asking prices on eBay for a card page (app/ebay.py)."""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.ebay import GRADE, GRADERS

router = APIRouter()
log = logging.getLogger("ebay")


class EbayListing(BaseModel):
    title: str
    amount: float
    currency: str
    country: str = ""
    url: str = ""


class EbayGraded(BaseModel):
    # False when the server has no eBay keys.
    enabled: bool = False
    # The average of the cheapest listings; None with too few to mean much.
    average: float | None = None
    currency: str = "USD"
    count: int = 0
    listings: list[EbayListing] = Field(default_factory=list)
    observed_at: str | None = None


@router.get("/ebay/graded", response_model=EbayGraded)
def get_graded(
    request: Request,
    q: str = Query(min_length=3, max_length=120),
    grader: str = Query(min_length=3, max_length=3),
    grade: str = Query(min_length=1, max_length=3),
) -> EbayGraded:
    reader = getattr(request.app.state, "ebay", None)
    if reader is None:
        return EbayGraded()
    grader = grader.upper()
    # The search is the app's own eBay search for the card; it must be for
    # this grade, so the endpoint is no general way into eBay.
    if grader not in GRADERS or not GRADE.match(grade) or grader.lower() not in q.lower():
        raise HTTPException(status_code=422, detail="Unknown grade")
    try:
        return EbayGraded.model_validate(reader.graded(q, grader, grade))
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        # Never the keys or the request: only what kind of failure it was.
        log.warning("ebay read failed error_type=%s", type(exc).__name__)
        return EbayGraded(enabled=True)
