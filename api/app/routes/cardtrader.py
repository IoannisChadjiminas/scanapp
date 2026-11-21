"""CardTrader seller listings for a card page (app/cardtrader.py)."""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.cardtrader import CONDITIONS

router = APIRouter()
log = logging.getLogger("cardtrader")


class CardTraderPrice(BaseModel):
    label: str
    amount: float
    currency: str
    source: str = "cardtrader"


class CardTraderPrices(BaseModel):
    # False when the server has no CardTrader token.
    enabled: bool = False
    # Whether CardTrader lists this card at all.
    matched: bool = False
    count: int = 0
    prices: list[CardTraderPrice] = Field(default_factory=list)
    observed_at: str | None = None


@router.get("/cardtrader/prices", response_model=CardTraderPrices)
def get_prices(
    request: Request,
    card_id: str = Query(min_length=1, max_length=120),
    condition: str = Query(default="NM", max_length=2),
    reverse: bool = False,
    first_edition: bool | None = None,
) -> CardTraderPrices:
    reader = getattr(request.app.state, "cardtrader", None)
    if reader is None:
        return CardTraderPrices()
    if condition not in CONDITIONS.values():
        raise HTTPException(status_code=422, detail="Unknown condition")
    row = request.app.state.dbs.catalog.execute(
        "SELECT cardmarket_id, language FROM cards WHERE id = ?", (card_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Card not found")
    if row["cardmarket_id"] is None:
        return CardTraderPrices(enabled=True)
    try:
        return CardTraderPrices.model_validate(
            reader.prices(
                int(row["cardmarket_id"]),
                str(row["language"] or "en"),
                condition=condition,
                reverse=reverse,
                first_edition=first_edition,
            )
        )
    except (httpx.HTTPError, ValueError) as exc:
        # Never the token or the request: only what kind of failure it was.
        log.warning("cardtrader read failed error_type=%s", type(exc).__name__)
        return CardTraderPrices(enabled=True)
