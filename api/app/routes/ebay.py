"""Graded asking prices on eBay for a card page (app/ebay.py)."""
from __future__ import annotations

import logging
import sqlite3

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.ebay import GRADE, GRADERS, GradedCard, name_from_listing

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


def _year(conn, language: str, set_id: str) -> int | None:
    try:
        row = conn.execute(
            "SELECT release_date FROM set_releases WHERE language = ? AND set_id = ?",
            (language, set_id),
        ).fetchone()
    except sqlite3.Error:
        return None
    text = str(row[0] or "") if row else ""
    return int(text[:4]) if text[:4].isdigit() else None


def _total(conn, language: str, set_id: str) -> int | None:
    try:
        row = conn.execute(
            "SELECT official_total FROM set_totals WHERE language = ? AND set_id = ?",
            (language, set_id),
        ).fetchone()
    except sqlite3.Error:
        return None
    return int(row[0]) if row and row[0] else None


@router.get("/ebay/graded", response_model=EbayGraded)
def get_graded(
    request: Request,
    card_id: str = Query(min_length=1, max_length=120),
    grader: str = Query(min_length=3, max_length=3),
    grade: str = Query(min_length=1, max_length=3),
    reverse: bool = False,
    first_edition: bool | None = None,
) -> EbayGraded:
    reader = getattr(request.app.state, "ebay", None)
    if reader is None:
        return EbayGraded()
    grader = grader.upper()
    if grader not in GRADERS or not GRADE.match(grade):
        raise HTTPException(status_code=422, detail="Unknown grade")
    catalog = request.app.state.dbs.catalog
    row = catalog.execute(
        "SELECT name, set_id, set_name, collector_number, language, cardmarket_url "
        "FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Card not found")
    language = str(row["language"] or "en").lower()
    # Sellers title cards in English: a Japanese card's name comes from its
    # Cardmarket address.
    name = str(row["name"] or "")
    if not name.isascii():
        name = name_from_listing(row["cardmarket_url"])
    number = str(row["collector_number"] or "").strip()
    if language not in {"en", "ja"} or not name.strip() or not number:
        return EbayGraded(enabled=True)
    card = GradedCard(
        name=name.strip(),
        number=number,
        grader=grader,
        grade=grade,
        total=_total(catalog, language, str(row["set_id"])),
        year=_year(catalog, language, str(row["set_id"])),
        japanese=language == "ja",
        reverse=reverse,
        first_edition=first_edition,
        set_name=str(row["set_name"] or ""),
    )
    try:
        return EbayGraded.model_validate(reader.graded(card))
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        # Never the keys or the request: only what kind of failure it was.
        log.warning("ebay read failed error_type=%s", type(exc).__name__)
        return EbayGraded(enabled=True)
