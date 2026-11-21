"""CardTrader seller listings for a card page (app/cardtrader.py)."""
from __future__ import annotations

import logging
import sqlite3

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.cardmarket import normalize_product_url
from app.cardtrader import CONDITIONS
from app.price_sources import product_id_for_url

router = APIRouter()
log = logging.getLogger("cardtrader")


def _product(request: Request, card_id: str, url: str | None):
    """The card's row and the Cardmarket product the prices are for.

    A card can have several Cardmarket listings (V1, V2: separate products).
    [url] is the one the collector picked; its own product number is used, so
    the other marketplaces price the same version. A picked listing whose
    number is not known gives no product: no price is better than the price
    of another version. Any other address means the card's main listing.
    """
    row = request.app.state.dbs.catalog.execute(
        "SELECT cardmarket_id, cardmarket_url, language FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Card not found")
    main = int(row["cardmarket_id"]) if row["cardmarket_id"] is not None else None
    picked = normalize_product_url(url)
    if picked is None or picked == normalize_product_url(row["cardmarket_url"]):
        return row, main
    catalog = request.app.state.dbs.catalog
    # Only a listing stored as another one of this card changes the product:
    # an address spelt differently by an older app still means the card.
    try:
        other = catalog.execute(
            "SELECT 1 FROM cardmarket_expansion_products WHERE url = ? AND card_id = ? AND matched = 1",
            (picked, card_id),
        ).fetchone()
    except sqlite3.OperationalError:
        other = None
    if other is None:
        return row, main
    return row, product_id_for_url(catalog, picked)


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
    url: str | None = Query(default=None, max_length=500),
) -> CardTraderPrices:
    reader = getattr(request.app.state, "cardtrader", None)
    if reader is None:
        return CardTraderPrices()
    if condition not in CONDITIONS.values():
        raise HTTPException(status_code=422, detail="Unknown condition")
    row, product = _product(request, card_id, url)
    if product is None:
        return CardTraderPrices(enabled=True)
    try:
        return CardTraderPrices.model_validate(
            reader.prices(
                product,
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


class TcgplayerPrices(BaseModel):
    # False when the server cannot find TCGplayer products (no CardTrader token).
    enabled: bool = False
    # Market first, then Low and Mid, in dollars; empty when there is no price.
    prices: list[CardTraderPrice] = Field(default_factory=list)
    observed_at: str | None = None


@router.get("/tcgplayer/prices", response_model=TcgplayerPrices)
def get_tcgplayer_prices(
    request: Request,
    card_id: str = Query(min_length=1, max_length=120),
    reverse: bool = False,
    first_edition: bool | None = None,
    url: str | None = Query(default=None, max_length=500),
) -> TcgplayerPrices:
    reader = getattr(request.app.state, "cardtrader", None)
    store = getattr(request.app.state, "tcgplayer", None)
    if reader is None or store is None:
        return TcgplayerPrices()
    row, product = _product(request, card_id, url)
    # TCGplayer prices English and Japanese printings only.
    if product is None or str(row["language"] or "en").lower() not in {"en", "ja"}:
        return TcgplayerPrices(enabled=True)
    return TcgplayerPrices.model_validate(
        store.prices(
            reader.tcgplayer_id(product),
            reverse=reverse,
            first_edition=first_edition,
        )
    )
