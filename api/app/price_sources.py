"""Prices that need no browser: Cardmarket's nightly file and TCGdex.

A scan gets the best price already on file for each candidate, in this order:
a listing sample still inside its fresh window (live), Cardmarket's price
file, TCGdex (its Cardmarket part first, then TCGplayer), and last of all an
older listing sample. Every price carries the source it came from.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.cardmarket import prices_from_market, snapshot_record
from app.config import Settings

log = logging.getLogger("price.sources")

GUIDE_COLUMNS = (
    "avg", "low", "trend", "avg1", "avg7", "avg30",
    "avg-holo", "low-holo", "trend-holo", "avg1-holo", "avg7-holo", "avg30-holo",
)
# A file that shrinks by more than this against the last import is treated as
# damaged and kept out.
MIN_KEEP_RATIO = 0.5


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def parse_guide(payload: Any) -> tuple[str, list[dict[str, Any]]]:
    """Return (guide date, entries) from Cardmarket's price guide JSON."""
    if not isinstance(payload, dict) or not isinstance(payload.get("priceGuides"), list):
        raise ValueError("Not a Cardmarket price guide")
    created = str(payload.get("createdAt") or "")
    try:
        stamp = datetime.strptime(created, "%Y-%m-%dT%H:%M:%S%z")
        date = stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        date = _now()
    rows = [
        entry for entry in payload["priceGuides"]
        if isinstance(entry, dict) and isinstance(entry.get("idProduct"), int)
    ]
    return date, rows


def import_guide(conn: sqlite3.Connection, payload: Any) -> int:
    """Replace the stored guide with this file. Returns the rows stored."""
    date, rows = parse_guide(payload)
    previous = conn.execute("SELECT row_count FROM cardmarket_guide_meta WHERE id = 1").fetchone()
    if not rows:
        raise ValueError("Price guide has no products")
    if previous and len(rows) < previous["row_count"] * MIN_KEEP_RATIO:
        raise ValueError("Price guide is much smaller than the last import")
    columns = [name.replace("-", "_") for name in GUIDE_COLUMNS]
    sql = (
        f"INSERT OR REPLACE INTO cardmarket_guide (id_product, {', '.join(columns)}, guide_date) "
        f"VALUES (?, {', '.join('?' for _ in columns)}, ?)"
    )
    with conn:
        conn.executemany(
            sql,
            [
                (entry["idProduct"], *(_number(entry.get(name)) for name in GUIDE_COLUMNS), date)
                for entry in rows
            ],
        )
        conn.execute("DELETE FROM cardmarket_guide WHERE guide_date != ?", (date,))
        conn.execute(
            "INSERT OR REPLACE INTO cardmarket_guide_meta (id, guide_date, row_count, imported_at) "
            "VALUES (1, ?, ?, ?)",
            (date, len(rows), _now()),
        )
    return len(rows)


def guide_market(conn: sqlite3.Connection, product_id: int | None) -> dict[str, Any] | None:
    if not product_id:
        return None
    row = conn.execute("SELECT * FROM cardmarket_guide WHERE id_product = ?", (product_id,)).fetchone()
    if row is None:
        return None
    market: dict[str, Any] = {"unit": "EUR", "updated": row["guide_date"]}
    for name in GUIDE_COLUMNS:
        market[name] = row[name.replace("-", "_")]
    return market


def refresh_guide(conn: sqlite3.Connection, settings: Settings) -> int:
    response = httpx.get(settings.price_guide_url, timeout=60, follow_redirects=True)
    response.raise_for_status()
    count = import_guide(conn, response.json())
    log.info("price guide imported rows=%s", count)
    return count


def _holo_first(variants: dict[str, Any]) -> bool:
    """A printing that only exists as a foil or reverse holo."""
    return (
        not variants.get("normal")
        and bool(variants.get("holo") or variants.get("reverse"))
    )


def _swap_holo(market: dict[str, Any]) -> dict[str, Any]:
    swapped = dict(market)
    for name in ("low", "trend", "avg7"):
        holo = market.get(f"{name}-holo")
        if holo:
            swapped[name] = holo
            swapped[f"{name}-holo"] = market.get(name)
    return swapped


def _tag(prices: list[dict[str, Any]], source: str, as_of: str | None) -> list[dict[str, Any]]:
    return [{**price, "source": source, "as_of": as_of, "stale": False} for price in prices]


def _tcgplayer_prices(block: dict[str, Any], variants: dict[str, Any]) -> list[dict[str, Any]]:
    currency = str(block.get("unit") or "USD")
    finishes = {
        key: value for key, value in block.items()
        if isinstance(value, dict) and _number(value.get("marketPrice"))
    }
    if not finishes:
        return []
    order = [key for key in ("normal", "holo", "reverse") if variants.get(key)]
    key = next((item for item in order if item in finishes), next(iter(finishes)))
    chosen = finishes[key]
    prices = []
    for label, field in (("Market", "marketPrice"), ("Low", "lowPrice")):
        amount = _number(chosen.get(field))
        if amount and amount > 0:
            prices.append({"label": label, "amount": round(amount, 2), "currency": currency})
    return prices


def _json(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def parse_tiers(text: str) -> list[tuple[float | None, int]]:
    """"2:604800,20:86400,*:3600" -> [(2.0, 604800), (20.0, 86400), (None, 3600)]."""
    tiers: list[tuple[float | None, int]] = []
    for part in (text or "").split(","):
        limit, _, seconds = part.strip().partition(":")
        try:
            window = int(seconds)
            bound = None if limit.strip() == "*" else float(limit)
        except ValueError:
            continue
        if window > 0:
            tiers.append((bound, window))
    tiers.sort(key=lambda tier: float("inf") if tier[0] is None else tier[0])
    return tiers


def tier_window(settings: Settings, trend: float | None) -> int | None:
    """Seconds a listing sample stays fresh for a card worth `trend` EUR."""
    if not settings.cardmarket_fresh_by_value or trend is None or trend <= 0:
        return None
    for bound, window in parse_tiers(settings.cardmarket_fresh_tiers):
        if bound is None or trend < bound:
            return window
    return None


def market_trend(market: dict[str, Any] | None) -> float | None:
    if not market:
        return None
    for key in ("trend", "trend-holo"):
        value = _number(market.get(key))
        if value and value > 0:
            return value
    return None


def trend_for_url(conn: sqlite3.Connection, url: str | None) -> float | None:
    """The Cardmarket trend of the product behind a listing URL, if on file."""
    from app.cardmarket import normalize_product_url

    if not url:
        return None
    row = conn.execute(
        "SELECT cardmarket_id FROM cards WHERE cardmarket_url = ? AND cardmarket_id IS NOT NULL LIMIT 1",
        (normalize_product_url(url) or url,),
    ).fetchone()
    return market_trend(guide_market(conn, row["cardmarket_id"])) if row else None


def fresh_window(conn: sqlite3.Connection, url: str | None, *, trend: float | None = None) -> int:
    """How long a listing sample for this product stays fresh, in seconds."""
    from app.cardmarket_queue import fresh_seconds
    from app.config import get_settings

    settings = get_settings()
    if not settings.cardmarket_fresh_by_value:
        return fresh_seconds()
    try:
        value = trend if trend is not None else trend_for_url(conn, url)
        return tier_window(settings, value) or fresh_seconds()
    except sqlite3.Error:
        return fresh_seconds()


def best_prices(conn: sqlite3.Connection, card_id: str, url: str | None) -> list[dict[str, Any]]:
    """The prices to show with one card, each tagged with its source."""
    from app.cardmarket_queue import _age_seconds

    card = conn.execute(
        "SELECT cardmarket_id, variants_json FROM cards WHERE id = ?", (card_id,)
    ).fetchone()
    variants = _json(card["variants_json"]) if card else {}
    market = guide_market(conn, card["cardmarket_id"] if card else None)
    record = snapshot_record(conn, url) if url else None
    live = list((record or {}).get("prices") or [])
    observed = (record or {}).get("observed_at") or (record or {}).get("fetched_at")
    stale_live: list[dict[str, Any]] = []
    if live:
        age = _age_seconds(str(observed or ""))
        is_fresh = age is None or age <= fresh_window(conn, url, trend=market_trend(market))
        tagged = [
            {**price, "source": "live", "as_of": observed, "stale": not is_fresh} for price in live
        ]
        if is_fresh:
            return tagged
        stale_live = tagged

    if market:
        prices = prices_from_market(_swap_holo(market) if _holo_first(variants) else market)
        if prices:
            return _tag(prices, "cardmarket_file", market["updated"])

    stored = conn.execute(
        "SELECT cardmarket_json, tcgplayer_json, fetched_at FROM tcgdex_prices WHERE card_id = ?",
        (card_id,),
    ).fetchone()
    if stored:
        market = _json(stored["cardmarket_json"])
        if market:
            prices = prices_from_market(_swap_holo(market) if _holo_first(variants) else market)
            if prices:
                return _tag(prices, "tcgdex", market.get("updated") or stored["fetched_at"])
        block = _json(stored["tcgplayer_json"])
        if block:
            prices = _tcgplayer_prices(block, variants)
            if prices:
                return _tag(prices, "tcgplayer", block.get("updated") or stored["fetched_at"])
    return stale_live


def scan_prices(conn: sqlite3.Connection, card_id: str, url: str | None) -> list[dict[str, Any]]:
    """best_prices for the scan path, which must never fail because of a price."""
    try:
        return best_prices(conn, card_id, url)
    except Exception:
        log.exception("scan prices failed card=%s", card_id)
        return []


def tcgdex_ids(row: sqlite3.Row) -> tuple[str, str]:
    """(language, TCGdex card id) for a catalogue row."""
    language = str(row["language"] or "en").lower()
    return language, str(row["provider_id"] or row["id"]).split(":")[-1]


def refresh_tcgdex(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    catalog: sqlite3.Connection | None = None,
    sleep=time.sleep,
) -> int:
    """Fetch TCGdex pricing for cards the Cardmarket file does not cover.

    Cards never fetched go first, then the oldest fetch. The batch size keeps
    the job polite; it works through the catalogue over several nights.

    `catalog` is the connection scans read cards from. With the PlanetScale
    catalogue the cards live in an in-memory snapshot attached to that one
    connection, so a separate connection to the file sees only a few old rows.
    Candidates come from it; results are written on `conn`.
    """
    batch = max(0, int(settings.tcgdex_prices_batch))
    if batch == 0:
        return 0
    source = catalog if catalog is not None else conn
    cards = source.execute(
        "SELECT id, provider_id, language, cardmarket_id FROM cards WHERE id NOT LIKE 'extra-%'"
    ).fetchall()
    covered = {row[0] for row in conn.execute("SELECT id_product FROM cardmarket_guide")}
    fetched = {row[0]: row[1] for row in conn.execute("SELECT card_id, fetched_at FROM tcgdex_prices")}
    missing = [row for row in cards if row["cardmarket_id"] is None or int(row["cardmarket_id"]) not in covered]
    missing.sort(key=lambda row: (row["id"] in fetched, fetched.get(row["id"]) or ""))
    rows = missing[:batch]
    done = 0
    with httpx.Client(timeout=15) as client:
        for row in rows:
            language, tcgdex_id = tcgdex_ids(row)
            try:
                response = client.get(f"{settings.tcgdex_base_url}/{language}/cards/{tcgdex_id}")
                if response.status_code == 404:
                    pricing: dict[str, Any] = {}
                else:
                    response.raise_for_status()
                    body = response.json()
                    pricing = body.get("pricing") if isinstance(body, dict) else {}
            except (httpx.HTTPError, ValueError) as exc:
                log.info("tcgdex price failed card=%s error=%s", row["id"], type(exc).__name__)
                continue
            pricing = pricing if isinstance(pricing, dict) else {}
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO tcgdex_prices (card_id, cardmarket_json, tcgplayer_json, fetched_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        row["id"],
                        json.dumps(pricing.get("cardmarket") or {}),
                        json.dumps(pricing.get("tcgplayer") or {}),
                        _now(),
                    ),
                )
            done += 1
            sleep(max(0.0, float(settings.tcgdex_prices_gap_s)))
    log.info("tcgdex prices refreshed cards=%s", done)
    return done


def refresh_all(
    conn: sqlite3.Connection, settings: Settings, *, catalog: sqlite3.Connection | None = None
) -> None:
    """One nightly pass. A failed source leaves the older data in place.

    The pass also runs once at every server start. The set totals come first:
    they are one quick request per language, and cards show them at once.
    """
    try:
        from app.set_totals import refresh_set_totals

        refresh_set_totals(conn, settings, catalog=catalog)
    except Exception as exc:
        log.info("set totals failed error=%s", type(exc).__name__)
    if settings.price_guide_enabled:
        try:
            refresh_guide(conn, settings)
        except Exception as exc:
            log.info("price guide failed error=%s", type(exc).__name__)
    if settings.tcgdex_prices_enabled:
        try:
            refresh_tcgdex(conn, settings, catalog=catalog)
        except Exception as exc:
            log.info("tcgdex prices failed error=%s", type(exc).__name__)


def refresh_all_on_own_connection(settings: Settings, catalog: sqlite3.Connection | None = None) -> None:
    """Run the pass on a connection of its own, so a large import never shares
    a transaction with the requests that read prices. `catalog` is only read,
    to choose which cards need TCGdex prices."""
    from app.db import connect

    conn = connect(settings.catalog_sqlite)
    try:
        refresh_all(conn, settings, catalog=catalog)
    finally:
        conn.close()
