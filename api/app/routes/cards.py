from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.card_images import display_image_url
from app.cardmarket import url_for_row, variants_for_row
from app.price_sources import scan_prices
from app.market_stats import capabilities
from app.recognition.language import expand_language
from app.set_totals import set_total
from app.schemas import CardMarket, CardmarketVariant, CardSearchResponse, CardSummary
from app.visual_aliases import visual_image_owner

router = APIRouter()

# Newest expansions first; a set with no known date goes last. Then by set and
# by the printed number, read as a number, so 2 comes before 10.
_RELEASES = (
    " LEFT JOIN set_releases ON set_releases.language = cards.language"
    " AND set_releases.set_id = cards.set_id"
)



def _summary(row, catalog=None) -> CardSummary:  # noqa: ANN001
    image_url = display_image_url(row, catalog)
    owner = visual_image_owner(row, catalog)
    url = url_for_row(row)
    return CardSummary(
        id=row["id"],
        name=row["name"],
        set_id=row["set_id"],
        set_name=row["set_name"],
        collector_number=row["collector_number"],
        set_total=set_total(catalog, row["language"], row["set_id"]) if catalog is not None else None,
        language=row["language"],
        rarity="" if str(row["rarity"] or "").strip().lower() in ("none", "null") else str(row["rarity"] or ""),
        market=_market(row),
        has_image=bool(image_url),
        image_url=image_url,
        image_owner_id=owner["id"] if owner is not row else None,
        variants=json.loads(row["variants_json"] or "{}"),
        cardmarket_url=url,
        cardmarket_prices=scan_prices(catalog, row["id"], url) if catalog is not None else [],
    )


# Choose one EUR source for the whole market block, then its normal/holo
# figures. A TCGplayer USD price can never enter this CTE.
_HOLO = "(NOT COALESCE(json_extract(cards.variants_json, '$.normal'), 0) AND (COALESCE(json_extract(cards.variants_json, '$.holo'), 0) OR COALESCE(json_extract(cards.variants_json, '$.reverse'), 0)))"
_GUIDE = "(COALESCE(g.trend>0, 0) OR COALESCE(g.trend_holo>0, 0))"
_DEX = "CASE WHEN json_valid(t.cardmarket_json) THEN t.cardmarket_json ELSE '{}' END"
_EUR = f"json_valid(t.cardmarket_json) AND COALESCE(json_extract({_DEX}, '$.unit'), 'EUR')='EUR'"
_BELOW_AVERAGE_RULE = "CASE WHEN m_change_30d IS NOT NULL AND m_sales_days_30 IS NOT NULL THEN m_change_30d<=-0.15 AND m_sales_days_30>=8 ELSE m_trend<=m_avg30*0.90 AND m_avg7<=m_avg30 END"
_FIELDS = ('low', 'trend', 'avg1', 'avg7', 'avg30')
_RAW = ', '.join(
    f"CASE WHEN {_GUIDE} THEN g.{field}{suffix} WHEN {_EUR} AND json_type({_DEX}, '$.{field}{'-holo' if suffix else ''}') IN ('integer', 'real') THEN json_extract({_DEX}, '$.{field}{'-holo' if suffix else ''}') END AS {field}{suffix}"
    for field in _FIELDS for suffix in ('', '_holo')
)


def _chosen(field: str) -> str:
    normal, holo = f"cards.{field}", f"cards.{field}_holo"
    return f"CASE WHEN {_HOLO} THEN COALESCE(CASE WHEN {holo}>0 THEN {holo} END, CASE WHEN {normal}>0 THEN {normal} END) ELSE COALESCE(CASE WHEN {normal}>0 THEN {normal} END, CASE WHEN {holo}>0 THEN {holo} END) END"


_MARKET_SELECT = ', '.join(f"{_chosen(field)} AS m_{field}" for field in _FIELDS)
_CTE = f"""WITH raw_prices AS (
    SELECT cards.*, set_releases.release_date,
      CASE WHEN {_GUIDE} THEN g.guide_date WHEN {_EUR} THEN COALESCE(json_extract({_DEX}, '$.updated'), t.fetched_at) END AS m_date,
      CASE WHEN {_GUIDE} THEN 'cardmarket_file' WHEN {_EUR} AND t.cardmarket_json IS NOT NULL THEN 'tcgdex' END AS m_source,
      {_RAW}
    FROM cards{_RELEASES}
    LEFT JOIN cardmarket_guide g ON g.id_product=cards.cardmarket_id
    LEFT JOIN tcgdex_prices t ON t.card_id=cards.id
), priced AS (
    SELECT cards.*,
      CASE WHEN {_HOLO} AND cards.trend_holo>0 OR NOT {_HOLO} AND NOT COALESCE(cards.trend>0, 0) AND cards.trend_holo>0 THEN 'holo' ELSE 'normal' END AS m_basis,
      {_MARKET_SELECT}, s.trend_7d_ago, s.trend_30d_ago,
      s.sales_days_30 AS m_sales_days_30, s.weekly_min_change
    FROM raw_prices cards LEFT JOIN card_market_stats s
      ON s.id_product=cards.cardmarket_id AND s.as_of=SUBSTR(cards.m_date, 1, 10)
      AND cards.m_source='cardmarket_file'
      AND s.basis=CASE WHEN {_HOLO} THEN 'holo' ELSE 'normal' END
), market_cards AS (
    SELECT *, m_avg7 / NULLIF(m_avg30, 0) - 1 AS m_momentum,
      m_trend / NULLIF(m_avg30, 0) - 1 AS m_discount,
      1 - m_low / NULLIF(m_trend, 0) AS m_under_trend,
      m_trend / NULLIF(trend_7d_ago, 0) - 1 AS m_change_7d,
      m_trend / NULLIF(trend_30d_ago, 0) - 1 AS m_change_30d
    FROM priced
), signals AS (
    SELECT *, CASE WHEN m_trend IS NULL OR m_avg7 IS NULL OR m_avg30 IS NULL THEN NULL
      ELSE m_trend>=2 AND ({_BELOW_AVERAGE_RULE}) END AS m_below_average
    FROM market_cards
) """

SEARCH_PRESETS = [
    {"id": "trending_up", "label": "Trending up", "icon": "trending_up", "params": {"preset": "trending_up", "sort": "momentum"}},
    {"id": "below_average", "label": "Below its average", "icon": "trending_down", "params": {"preset": "below_average", "sort": "discount"}},
    {"id": "under_trend", "label": "Listed under trend", "icon": "euro", "params": {"preset": "under_trend", "sort": "under_trend"}},
    {"id": "new_set", "label": "New set chase cards", "icon": "star", "params": {"preset": "new_set", "sort": "price_desc"}},
    {"id": "biggest_drops", "label": "Biggest drops", "icon": "trending_down", "params": {"preset": "biggest_drops", "sort": "momentum_asc"}},
]


def _market(row) -> CardMarket | None:
    if "m_date" not in row.keys() or row["m_date"] is None:
        return None
    return CardMarket(basis=row["m_basis"], source=row["m_source"], as_of=row["m_date"], below_average=row["m_below_average"], **{
        field: row[f"m_{field}"] for field in ("low", "trend", "avg1", "avg7", "avg30", "momentum", "discount", "under_trend", "change_7d", "change_30d", "sales_days_30")
    })


@router.get("/sets")
def search_sets(request: Request, language: str = "") -> list[dict]:
    catalog = request.app.state.dbs.catalog
    # Reloading a snapshot replaces the catalogue connection. In-place imports
    # change total_changes/data_version and invalidate this small metadata cache.
    state = request.app.state
    signature = (catalog, catalog.total_changes, catalog.execute("PRAGMA data_version").fetchone()[0])
    cached = getattr(state, "search_sets_cache", None)
    if cached is None or cached[0] != signature:
        rows = catalog.execute(f"""SELECT cards.language, cards.set_id, MAX(cards.set_name) AS set_name,
            set_releases.release_date, COUNT(*) AS cards FROM cards{_RELEASES}
            GROUP BY cards.language, cards.set_id
            ORDER BY release_date IS NULL, release_date DESC, set_name, cards.language, cards.set_id""").fetchall()
        cached = (signature, [dict(row) for row in rows])
        state.search_sets_cache = cached
    langs = expand_language(language) if language and language != "auto" else ()
    return [item for item in cached[1] if not langs or item["language"] in langs]


@router.get("/search-options")
def search_options(request: Request) -> dict:
    rows = request.app.state.dbs.catalog.execute("""SELECT LOWER(TRIM(rarity)) AS value, MIN(TRIM(rarity)) AS label
        FROM cards WHERE rarity IS NOT NULL AND LOWER(TRIM(rarity)) NOT IN ('', 'none', 'null')
        GROUP BY LOWER(TRIM(rarity)) ORDER BY value""").fetchall()
    return {"rarities": [dict(row) for row in rows], "history": capabilities(request.app.state.dbs.catalog)}



@router.get("/cards", response_model=CardSearchResponse)
def search_cards(
    request: Request,
    q: Annotated[str, Query(max_length=80)] = "",
    language: Annotated[str, Query(max_length=16)] = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
    sets: Annotated[list[str] | None, Query(alias="set")] = None,
    min_price: Annotated[float | None, Query(ge=0, allow_inf_nan=False)] = None,
    max_price: Annotated[float | None, Query(ge=0, allow_inf_nan=False)] = None,
    sort: str = "newest",
    preset: str = "",
    momentum_min: Annotated[float | None, Query(allow_inf_nan=False)] = None,
    momentum_max: Annotated[float | None, Query(allow_inf_nan=False)] = None,
    sold_recently: bool = False,
    rarity: Annotated[list[str] | None, Query()] = None,
    finish: str = "",
    category: str = "",
    released_after: date | None = None,
    released_before: date | None = None,
    ownership: str = 'any',
    owned_ids: Annotated[list[str] | None, Query()] = None,
    card_ids: Annotated[list[str] | None, Query()] = None,
) -> CardSearchResponse:
    """Filter before paging, with the identical predicates for the total."""
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(422, "Minimum price exceeds maximum price")
    if released_after and released_before and released_after > released_before:
        raise HTTPException(422, "Invalid release date range")
    catalog = request.app.state.dbs.catalog
    clauses, params = ["1=1"], []
    if ownership not in ('any', 'hide_owned', 'only_owned'):
        raise HTTPException(422, "Unknown ownership filter")
    if ownership != 'any':
        membership = "cards.id IN (SELECT value FROM json_each(?))"
        clauses.append(membership if ownership == 'only_owned' else 'NOT (' + membership + ')')
        params.append(json.dumps(owned_ids or []))
    if card_ids is not None:
        clauses.append("cards.id IN (SELECT value FROM json_each(?))")
        params.append(json.dumps(card_ids))
    query = q.strip()
    tokens = re.findall(r"[A-Za-z0-9/]+", query)
    if any(ord(char) > 0x2E80 for char in query):
        clauses.append("(cards.name LIKE ? OR cards.set_name LIKE ? OR cards.collector_number LIKE ?)")
        params.extend([f"%{query}%"] * 3)
    elif tokens:
        clauses.append("cards.id IN (SELECT id FROM cards_fts WHERE cards_fts MATCH ?)")
        params.append(" ".join(f"{token}*" for token in tokens))
    langs = expand_language(language) if language and language != "auto" else ()
    if langs:
        clauses.append(f"cards.language IN ({','.join('?' for _ in langs)})")
        params.extend(langs)
    if sets:
        options = []
        for value in sets:
            if ':' in value:
                lang, set_id = value.split(':', 1)
                options.append("(cards.language=? AND cards.set_id=?)")
                params.extend([lang, set_id])
            else:
                options.append("cards.set_id=?")
                params.append(value)
        clauses.append('(' + ' OR '.join(options) + ')')
    for value, expression in ((min_price, "m_trend>=?"), (max_price, "m_trend<=?"),
                              (momentum_min, "m_momentum>=?"), (momentum_max, "m_momentum<=?"),
                              (released_after, "release_date>=?"), (released_before, "release_date<=?")):
        if value is not None:
            clauses.append(expression)
            params.append(value.isoformat() if isinstance(value, date) else value)
    if sold_recently:
        clauses.append("m_avg1>0")
    if rarity:
        clauses.append(f"LOWER(TRIM(cards.rarity)) IN ({','.join('?' for _ in rarity)})")
        params.extend(value.strip().lower() for value in rarity)
    if finish:
        key = {"normal": "normal", "holo": "holo", "reverse": "reverse"}.get(finish)
        if key is None:
            raise HTTPException(422, "Unknown finish")
        clauses.append(f"json_extract(cards.variants_json, '$.{key}')=1")
    if category:
        clauses.append("LOWER(cards.category)=?")
        params.append(category.lower())
    rules = {
        "trending_up": ("CASE WHEN m_change_30d IS NOT NULL AND m_sales_days_30 IS NOT NULL THEN m_change_7d>0 AND m_change_30d>0 AND m_sales_days_30>=8 ELSE m_avg7>=m_avg30*1.10 AND m_trend>=m_avg30*1.05 END", "momentum"),
        "below_average": (_BELOW_AVERAGE_RULE, "discount"),
        "under_trend": ("m_low<=m_trend*0.80 AND m_trend>=5", "under_trend"),
        "new_set": ("release_date>=? AND release_date<=?", "price_desc"),
        "biggest_drops": ("CASE WHEN m_change_7d IS NOT NULL THEN m_change_7d<=-0.15 ELSE m_avg7<=m_avg30*0.85 END", "change_7d_asc" if capabilities(catalog)['change_7d'] else "momentum_asc"),
        "steady_climbers": ("m_change_30d>0 AND weekly_min_change>=-0.05 AND m_sales_days_30 IS NOT NULL", "change_30d"),
    }
    if preset in rules:
        rule, sort = rules[preset]
        clauses.extend(["m_trend>=2 AND m_avg7>0 AND m_avg30>0", rule])
        if preset == "new_set":
            today = date.today()
            params.extend([(today - timedelta(days=90)).isoformat(), today.isoformat()])
    orders = {
        "newest": "release_date IS NULL, release_date DESC, cards.set_name, CAST(cards.collector_number AS INTEGER), cards.collector_number",
        "price_desc": "m_trend IS NULL, m_trend DESC",
        "price_asc": "m_trend IS NULL, m_trend ASC",
        "momentum": ("COALESCE(m_change_7d, m_momentum) IS NULL, COALESCE(m_change_7d, m_momentum) DESC" if preset == 'trending_up' else "m_momentum IS NULL, m_momentum DESC"),
        "momentum_asc": "m_momentum IS NULL, m_momentum ASC",
        "discount": ("CASE WHEN m_sales_days_30 IS NOT NULL THEN COALESCE(m_change_30d, m_discount) ELSE m_discount END ASC" if preset == 'below_average' else "m_discount IS NULL, m_discount ASC"),
        "under_trend": "m_under_trend IS NULL, m_under_trend DESC",
        "change_7d": "m_change_7d IS NULL, m_change_7d DESC",
        "change_7d_asc": "m_change_7d IS NULL, m_change_7d ASC",
        "change_30d": "m_change_30d IS NULL, m_change_30d DESC",
        "change_30d_asc": "m_change_30d IS NULL, m_change_30d ASC",
        "number": "cards.language, cards.set_id, CAST(cards.collector_number AS INTEGER), cards.collector_number",
    }
    where = ' AND '.join(clauses)
    order = orders.get(sort, orders["newest"])
    rows = catalog.execute(_CTE + f"SELECT cards.* FROM signals cards WHERE {where} ORDER BY {order}, cards.id LIMIT ? OFFSET ?", (*params, limit, offset)).fetchall()
    total = catalog.execute(_CTE + f"SELECT COUNT(*) AS n FROM signals cards WHERE {where}", params).fetchone()["n"]
    return CardSearchResponse(items=[_summary(row, catalog) for row in rows], total=total)


class CardSearchBody(BaseModel):
    model_config = ConfigDict(extra='forbid', populate_by_name=True)
    q: str = Field(default='', max_length=80)
    language: str = Field(default='', max_length=16)
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=10000)
    sets: list[str] | None = Field(default=None, alias='set', max_length=1000)
    min_price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    max_price: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    sort: str = 'newest'
    preset: str = ''
    momentum_min: float | None = Field(default=None, allow_inf_nan=False)
    momentum_max: float | None = Field(default=None, allow_inf_nan=False)
    sold_recently: bool = False
    rarity: list[str] | None = None
    finish: str = ''
    category: str = ''
    released_after: date | None = None
    released_before: date | None = None
    ownership: Literal['any', 'hide_owned', 'only_owned'] = 'any'
    owned_ids: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(default_factory=list, max_length=50000)
    card_ids: list[Annotated[str, Field(min_length=1, max_length=200)]] | None = Field(default=None, max_length=1000)


@router.post('/cards/search', response_model=CardSearchResponse)
def search_cards_body(request: Request, body: CardSearchBody) -> CardSearchResponse:
    return search_cards(request, **body.model_dump())


@router.get("/cards/{card_id}", response_model=CardSummary)
def get_card(card_id: str, request: Request) -> CardSummary:
    row = request.app.state.dbs.catalog.execute(
        "SELECT * FROM cards WHERE id = ?", (card_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Card not found")
    summary = _summary(row, request.app.state.dbs.catalog)
    summary.cardmarket_variants = [
        CardmarketVariant.model_validate(variant)
        for variant in variants_for_row(request.app.state.dbs.catalog, row)
    ]
    return summary


@router.get("/cards/{card_id}/image")
def card_image(card_id: str, request: Request) -> FileResponse:
    row = request.app.state.dbs.catalog.execute(
        "SELECT * FROM cards WHERE id = ?", (card_id,)
    ).fetchone()
    if row is not None:
        row = visual_image_owner(row, request.app.state.dbs.catalog)
    if row is None or not row["has_image"] or not row["image_path"]:
        raise HTTPException(status_code=404, detail="Card image not found")
    path = Path(row["image_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Card image not found")
    media = "image/webp" if path.suffix.lower() == ".webp" else "image/jpeg"
    return FileResponse(path, media_type=media)
