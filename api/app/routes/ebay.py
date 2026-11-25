"""Graded asking prices on eBay for a card page (app/ebay.py)."""
from __future__ import annotations

import logging
import sqlite3

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.live_permit import require_live_permit
from app.ebay import (
    GRADE, GRADERS, PATTERNS, PRISTINE, PRISTINE_GRADERS, GradedCard, name_from_listing,
)

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
    # The same in euros at the day's reference rate, for a collection's total.
    average_eur: float | None = None
    currency: str = "USD"
    count: int = 0
    listings: list[EbayListing] = Field(default_factory=list)
    observed_at: str | None = None
    # The move over the last [change_days], once there is a week of history.
    change_percent: float | None = None
    change_days: int | None = None


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


def _grade_known(grader: str, grade: str) -> bool:
    """A grader the app offers and a grade it awards: 1 to 10 in half steps,
    and "P10", a Pristine 10, from the graders that have one."""
    if grader not in GRADERS or not GRADE.match(grade):
        return False
    return grade != PRISTINE or grader in PRISTINE_GRADERS


def _pattern(catalog, card_id: str, listing: str | None) -> str | None:
    """The reverse pattern a copy is, from the Cardmarket listing the
    collector chose for it: a key of PATTERNS, "" for the card's own listing,
    and None for a version eBay's titles cannot tell apart (an unnamed
    pattern, an Energy or Team Rocket one, a stamped promo), which is then
    not priced from eBay rather than priced as the plain card."""
    url = (listing or "").split("?")[0].strip()
    if not url:
        return ""
    try:
        row = catalog.execute(
            "SELECT pattern FROM cardmarket_pattern_products WHERE url = ? AND card_id = ?",
            (url, card_id),
        ).fetchone()
    except sqlite3.Error:
        return ""
    if row is None:
        return ""
    pattern = str(row[0] or "")
    return pattern if pattern in PATTERNS else None


def _graded_card(
    catalog, card_id: str, grader: str, grade: str, reverse: bool, first_edition: bool | None,
    listing: str | None = None,
) -> GradedCard | None:
    """What eBay is asked about for a catalogue card and grade. None for a
    card that is not in the catalogue, or that sellers do not title reliably
    (another language, no name or number, a version without a settled name)."""
    pattern = _pattern(catalog, card_id, listing)
    if pattern is None:
        return None
    row = catalog.execute(
        "SELECT name, set_id, set_name, collector_number, language, cardmarket_url "
        "FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()
    if row is None:
        return None
    language = str(row["language"] or "en").lower()
    # Sellers title cards in English: a Japanese card's name comes from its
    # Cardmarket address.
    name = str(row["name"] or "")
    if not name.isascii():
        name = name_from_listing(row["cardmarket_url"])
    number = str(row["collector_number"] or "").strip()
    if language not in {"en", "ja"} or not name.strip() or not number:
        return None
    return GradedCard(
        name=name.strip(),
        number=number,
        grader=grader,
        grade=grade,
        total=_total(catalog, language, str(row["set_id"])),
        year=_year(catalog, language, str(row["set_id"])),
        japanese=language == "ja",
        # A pattern is never the reverse holo of the card's own listing.
        reverse=reverse and not pattern,
        first_edition=first_edition,
        pattern=pattern,
        set_name=str(row["set_name"] or ""),
        set_code=str(row["set_id"] or "").lower(),
        unique_name=catalog.execute(
            "SELECT COUNT(*) FROM cards WHERE set_id = ? AND language = ? AND name = ?",
            (row["set_id"], row["language"], row["name"]),
        ).fetchone()[0] == 1,
    )


def _in_euros(request: Request, answer: dict, card: GradedCard | None = None) -> dict:
    """The answer with its price in euros beside the dollars, and how the
    price moved over the last month once there is a week of history."""
    rate = getattr(request.app.state, "fx", None)
    euros = rate.usd_to_eur(answer.get("average")) if rate is not None else None
    reader = getattr(request.app.state, "ebay", None)
    change = reader.change(card) if reader is not None and card is not None else None
    return {
        **answer,
        "average_eur": euros,
        "change_percent": change["percent"] if change else None,
        "change_days": change["days"] if change else None,
    }


@router.get("/ebay/graded", response_model=EbayGraded)
def get_graded(
    request: Request,
    card_id: str = Query(min_length=1, max_length=120),
    grader: str = Query(min_length=3, max_length=3),
    grade: str = Query(min_length=1, max_length=3),
    reverse: bool = False,
    first_edition: bool | None = None,
    # Only what is already held: eBay is not asked. For showing a price
    # another collector's check already paid for, without a press.
    cached_only: bool = False,
    # The Cardmarket listing of the version the copy is, when the collector
    # chose one: a Master Ball copy is asked for as one.
    listing: str | None = Query(default=None, max_length=500),
) -> EbayGraded:
    reader = getattr(request.app.state, "ebay", None)
    if reader is None:
        return EbayGraded()
    grader = grader.upper()
    grade = grade.upper()
    if not _grade_known(grader, grade):
        raise HTTPException(status_code=422, detail="Unknown grade")
    catalog = request.app.state.dbs.catalog
    if catalog.execute("SELECT 1 FROM cards WHERE id = ?", (card_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="Card not found")
    card = _graded_card(catalog, card_id, grader, grade, reverse, first_edition, listing)
    if card is None:
        return EbayGraded(enabled=True)
    if cached_only:
        kept = reader.kept(card)
        return EbayGraded.model_validate(_in_euros(request, kept, card)) if kept else EbayGraded(enabled=True)
    # A live read is a Pro check: it spends one permit (no-op before the gate is ready).
    require_live_permit(request, 'ebay')
    try:
        return EbayGraded.model_validate(_in_euros(request, reader.graded(card), card))
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        # Never the keys or the request: only what kind of failure it was.
        log.warning("ebay read failed error_type=%s", type(exc).__name__)
        return EbayGraded(enabled=True)


class GradedCopy(BaseModel):
    card_id: str = Field(min_length=1, max_length=120)
    grader: str = Field(min_length=3, max_length=3)
    grade: str = Field(min_length=1, max_length=3)
    reverse: bool = False
    first_edition: bool | None = None
    listing: str | None = Field(default=None, max_length=500)


class GradedCopies(BaseModel):
    copies: list[GradedCopy] = Field(max_length=300)


class GradedValue(BaseModel):
    # What the copy is valued at, in euros; None when eBay has no price for
    # it (fewer than two listings) or it was never asked about.
    value_eur: float | None = None
    average: float | None = None
    currency: str = "USD"
    count: int = 0
    observed_at: str | None = None
    # The move over the last [change_days], once there is a week of history.
    change_percent: float | None = None
    change_days: int | None = None


class GradedValues(BaseModel):
    enabled: bool = False
    # One for each copy asked about, in the same order.
    values: list[GradedValue] = Field(default_factory=list)


@router.post("/ebay/graded/values", response_model=GradedValues)
def graded_values(payload: GradedCopies, request: Request) -> GradedValues:
    """What a collection's graded copies are valued at, from what is held.

    Nothing here waits for eBay: a copy never asked about, or last asked more
    than a day ago, is queued for the background and answered from its last
    price meanwhile (up to 45 days old), so a collection's total does not
    drop to the raw value each time an answer goes stale.
    """
    reader = getattr(request.app.state, "ebay", None)
    if reader is None:
        return GradedValues(values=[GradedValue() for _ in payload.copies])
    catalog = request.app.state.dbs.catalog
    values: list[GradedValue] = []
    for copy in payload.copies:
        grader = copy.grader.upper()
        grade = copy.grade.upper()
        card = (
            _graded_card(
                catalog, copy.card_id, grader, grade, copy.reverse, copy.first_edition,
                copy.listing,
            )
            if _grade_known(grader, grade)
            else None
        )
        if card is None:
            values.append(GradedValue())
            continue
        reader.own(card)
        found = reader.last(card)
        if found is None or found[0] >= reader.reuse_s:
            reader.want(card)
        if found is None:
            values.append(GradedValue())
            continue
        answer = _in_euros(request, found[1], card)
        values.append(GradedValue(
            value_eur=answer["average_eur"],
            average=answer.get("average"),
            currency=str(answer.get("currency") or "USD"),
            count=int(answer.get("count") or 0),
            observed_at=answer.get("observed_at"),
            change_percent=answer["change_percent"],
            change_days=answer["change_days"],
        ))
    return GradedValues(enabled=True, values=values)
