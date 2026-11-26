"""CardTrader seller listings for a card page (app/cardtrader.py)."""
from __future__ import annotations

import logging
import sqlite3

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.cardmarket import normalize_product_url
from app.cardtrader import CONDITIONS
from app.live_permit import require_live_permit
from app.market_match import card_names, plain, set_names
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
        "SELECT cardmarket_id, cardmarket_url, language, collector_number, set_id, set_name, name "
        "FROM cards WHERE id = ?",
        (card_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Card not found")
    from app.card_products import product_for

    main = product_for(request.app.state.dbs.catalog, card_id, row["cardmarket_id"])
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


def _set_cards(request: Request, row) -> tuple[list[int], list[str]]:
    """The Cardmarket ids and addresses of every card in the card's set."""
    rows = request.app.state.dbs.catalog.execute(
        "SELECT cardmarket_id, cardmarket_url FROM cards WHERE set_id = ? AND language = ?",
        (row["set_id"], row["language"]),
    ).fetchall()
    return (
        [int(item["cardmarket_id"]) for item in rows if item["cardmarket_id"] is not None],
        [str(item["cardmarket_url"]) for item in rows if item["cardmarket_url"]],
    )


def _main(row, product: int | None) -> bool:
    """Whether the prices are for the card's own main listing (not a picked
    V2 or a first edition kept elsewhere): only then may the card be looked
    for by its set, number and name."""
    main = row["cardmarket_id"]
    return product == (int(main) if main is not None else None)


def _on_cardtrader(request: Request, reader, row) -> tuple[int, int | None] | None:
    """The card on CardTrader by its set, number and name (app/market_match.py):
    (blueprint, TCGplayer product or None)."""
    language = str(row["language"] or "en").lower()
    key = (language, str(row["set_id"]))
    expansions = reader.set_expansions.get(key)
    if expansions is None:
        ids, urls = _set_cards(request, row)
        expansions = reader.expansions_for(
            ids, set_names(language, key[1], row["set_name"], urls), plain(key[1]), language
        )
        reader.set_expansions[key] = expansions
    return reader.find(
        expansions,
        row["collector_number"],
        card_names(row["cardmarket_url"], row["name"]),
        language,
    )


def _on_tcgplayer(request: Request, reader, store, row) -> int | None:
    """The card's TCGplayer product by its set and number."""
    language = str(row["language"] or "en").lower()
    key = (language, str(row["set_id"]))
    groups = store.set_groups.get(key)
    if groups is None:
        ids, _ = _set_cards(request, row)
        groups = store.groups_for(reader.tcgplayer_products(ids), key[1], language)
        store.set_groups[key] = groups
    return store.find(groups, row["collector_number"], card_names(row["cardmarket_url"], row["name"]))


def _tcgplayer_candidates(
    request: Request, reader, store, row, product: int | None, first_edition: bool | None
) -> list[int]:
    """The TCGplayer products that may be the card, most trusted first: the
    one CardTrader names for the card; else the card in TCGplayer's own set,
    or the product of the CardTrader card found by set and number."""
    main = _main(row, product)
    if product is None and not main:
        return []
    if first_edition and product is not None:
        product = reader.first_edition_product(product) or product
        main = _main(row, product)
    candidates = [reader.tcgplayer_id(product) if product is not None else None]
    if main:
        candidates.append(_on_tcgplayer(request, reader, store, row))
        found = _on_cardtrader(request, reader, row)
        candidates.append(None if found is None else found[1])
    return list(dict.fromkeys(item for item in candidates if item is not None))


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
    # The card's CardTrader page; None when no card was matched.
    url: str | None = None
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
    main = _main(row, product)
    if product is None and not main:
        # A picked listing whose product is not known.
        return CardTraderPrices(enabled=True)
    # A live read is a Pro check: it spends one permit (no-op before the gate is ready).
    require_live_permit(request, 'cardtrader')
    if first_edition and product is not None:
        product = reader.first_edition_product(product) or product
    try:
        found = _on_cardtrader(request, reader, row) if main else None
        if product is None and found is None:
            return CardTraderPrices(enabled=True)
        return CardTraderPrices.model_validate(
            reader.prices(
                product if product is not None else 0,
                str(row["language"] or "en"),
                condition=condition,
                reverse=reverse,
                first_edition=first_edition,
                fallback=None if found is None else found[0],
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
    # The matched product's TCGplayer page; None without a priced product.
    url: str | None = None
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
    if str(row["language"] or "en").lower() not in {"en", "ja"}:
        return TcgplayerPrices(enabled=True)
    answer = store.prices(None)
    for candidate in _tcgplayer_candidates(request, reader, store, row, product, first_edition):
        answer = store.prices(candidate, reverse=reverse, first_edition=first_edition)
        if answer["prices"]:
            break
    return TcgplayerPrices.model_validate(answer)


class HistoryPoint(BaseModel):
    day: str
    amount: float


class PriceHistory(BaseModel):
    # Cardmarket's daily trend, in euros, on the days it changed, with the
    # newest day repeated so the line reaches it.
    cardmarket: list[HistoryPoint] = Field(default_factory=list)
    # TCGplayer's market price (or lowest listing), in dollars, likewise.
    tcgplayer: list[HistoryPoint] = Field(default_factory=list)


def _reaching(points: list[tuple[str, float]], last_day: str | None) -> list[HistoryPoint]:
    """The stored changes as a line that runs to [last_day]."""
    found = [HistoryPoint(day=day, amount=round(amount, 2)) for day, amount in points if amount > 0]
    if found and last_day and last_day > found[-1].day:
        found.append(HistoryPoint(day=last_day, amount=found[-1].amount))
    return found


@router.get("/prices/history", response_model=PriceHistory)
def get_price_history(
    request: Request,
    card_id: str = Query(min_length=1, max_length=120),
    reverse: bool = False,
    first_edition: bool | None = None,
    url: str | None = Query(default=None, max_length=500),
) -> PriceHistory:
    """A card's price over time, for a chart, from what the server kept."""
    from app import price_history

    row, product = _product(request, card_id, url)
    answer = PriceHistory()
    # Cardmarket's trend is the unlimited print's: a first edition has none.
    if product is not None and not first_edition:
        history = request.app.state.dbs.portfolio
        first, second = ("trend_holo", "trend") if reverse else ("trend", "trend_holo")
        try:
            rows = price_history.guide_history(history, product)
            last = history.execute("SELECT MAX(day) FROM price_guide_import_days").fetchone()
        except Exception as exc:  # no history tables yet
            log.warning("price history read failed error_type=%s", type(exc).__name__)
            rows, last = [], None
        points: list[tuple[str, float]] = []
        for item in rows:
            amount = item.get(first) or item.get(second)
            # Rows are kept when any figure changed: only a new trend is a point.
            if amount and (not points or points[-1][1] != amount):
                points.append((str(item["day"]), float(amount)))
        answer.cardmarket = _reaching(points, None if last is None else str(last[0] or "") or None)
    reader = getattr(request.app.state, "cardtrader", None)
    store = getattr(request.app.state, "tcgplayer", None)
    if reader is not None and store is not None and str(row["language"] or "en").lower() in {"en", "ja"}:
        for candidate in _tcgplayer_candidates(request, reader, store, row, product, first_edition):
            points = store.history(candidate, reverse=reverse, first_edition=first_edition)
            if points:
                priced = (store._meta("priced_at") or "")[:10] or None
                answer.tcgplayer = _reaching(points, priced)
                break
    return answer


class TcgplayerCopy(BaseModel):
    card_id: str = Field(min_length=1, max_length=120)
    reverse: bool = False
    first_edition: bool | None = None
    url: str | None = Field(default=None, max_length=500)


class TcgplayerCopies(BaseModel):
    copies: list[TcgplayerCopy] = Field(max_length=500)


class TcgplayerValue(BaseModel):
    # TCGplayer's market price in euros at the day's reference rate; None
    # without a market price (listings alone are not a value) or a rate.
    value_eur: float | None = None
    market: float | None = None
    # What value_eur is: "tcgplayer", or "cardmarket_low" when TCGplayer has
    # no market price and Cardmarket's file has only a lowest listing for the
    # product. The last resort: a lowest listing is often a damaged copy.
    source: str | None = None


def _lowest_listing(request: Request, product: int | None, copy: TcgplayerCopy) -> float | None:
    """Cardmarket's lowest listing for a product its file has no trend for.
    None for a first edition: the file prices the unlimited print."""
    from app.price_sources import guide_market, market_trend

    if product is None or copy.first_edition:
        return None
    try:
        market = guide_market(request.app.state.dbs.catalog, product)
    except sqlite3.Error:
        return None
    if not market or market_trend(market, reverse=copy.reverse):
        return None
    for key in ("low-holo",) if copy.reverse else ("low", "low-holo"):
        value = market.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return round(float(value), 2)
    return None


class TcgplayerValues(BaseModel):
    enabled: bool = False
    # One for each copy asked about, in the same order.
    values: list[TcgplayerValue] = Field(default_factory=list)


@router.post("/tcgplayer/values", response_model=TcgplayerValues)
def tcgplayer_values(payload: TcgplayerCopies, request: Request) -> TcgplayerValues:
    """What TCGplayer's market price values a collection's copies at, in
    euros: for the copies Cardmarket has no price for. Read from the day's
    stored prices; nothing is fetched."""
    reader = getattr(request.app.state, "cardtrader", None)
    store = getattr(request.app.state, "tcgplayer", None)
    rate = getattr(request.app.state, "fx", None)
    if reader is None or store is None or rate is None:
        return TcgplayerValues(values=[TcgplayerValue() for _ in payload.copies])
    values: list[TcgplayerValue] = []
    for copy in payload.copies:
        market = None
        product = None
        try:
            row, product = _product(request, copy.card_id, copy.url)
        except HTTPException:
            row = None
        if row is not None and str(row["language"] or "en").lower() in {"en", "ja"}:
            for candidate in _tcgplayer_candidates(
                request, reader, store, row, product, copy.first_edition
            ):
                prices = store.prices(
                    candidate, reverse=copy.reverse, first_edition=copy.first_edition
                )["prices"]
                if prices:
                    market = next(
                        (item["amount"] for item in prices if item["label"] == "Market"), None
                    )
                    break
        euros = rate.usd_to_eur(market)
        if euros:
            values.append(TcgplayerValue(value_eur=euros, market=market, source="tcgplayer"))
        elif low := _lowest_listing(request, product, copy) if row is not None else None:
            values.append(TcgplayerValue(value_eur=low, source="cardmarket_low"))
        else:
            values.append(TcgplayerValue(market=market))
    return TcgplayerValues(enabled=True, values=values)
