"""When a held card's listing is read before its tier says so.

Two signals let a key be read early. A trend move: the price file's trend is at
least 10% and EUR 0.50 away from the trend on the key's last listing read. A
spike: yesterday's average is at least 1.5 times the 7-day average and EUR 1
higher. A spike is an episode per product and finish. Each listing key is read
once for it, by any accepted read after the episode began, and then goes back
to its normal tier until the spike clears and a new one starts.

First edition keys never use the price file: its numbers are the unlimited
printing's.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

from app.config import Settings

SPIKE_SCHEMA = """
CREATE TABLE IF NOT EXISTS price_spike_episodes (
    series TEXT PRIMARY KEY,
    active INTEGER NOT NULL,
    started_at TEXT,
    guide_date TEXT NOT NULL
)
"""


def _query(url: str | None) -> dict[str, list[str]]:
    return parse_qs(urlparse(url or "").query)


def condition_rank(url: str | None) -> int | None:
    """Cardmarket's minCondition on a listing key: MT 1, NM 2, ... PO 7."""
    try:
        return int((_query(url).get("minCondition") or [""])[0])
    except ValueError:
        return None


def is_condition_key(url: str | None) -> bool:
    """A listing read at a condition worse than Near Mint."""
    rank = condition_rank(url)
    return rank is not None and rank > 2


def is_first_edition(url: str | None) -> bool:
    return any(value.upper() == "Y" for value in _query(url).get("isFirstEd") or [])


def trend_moved(file_trend: float | None, read_trend: float | None, pct: float, floor: float) -> bool:
    """At least `pct` percent and `floor` EUR since the last listing read."""
    if not file_trend or not read_trend or pct <= 0:
        return False
    change = abs(file_trend - read_trend)
    return change >= floor and change / read_trend * 100 >= pct


def spike_predicate(avg1: Any, avg7: Any, ratio: float, floor: float) -> bool | None:
    """True or False for a valid pair of averages; None when either is missing."""
    if not isinstance(avg1, (int, float)) or not isinstance(avg7, (int, float)) or avg1 <= 0 or avg7 <= 0:
        return None
    return avg1 >= ratio * avg7 and avg1 - avg7 >= floor


def _series(product_id: int, reverse: bool) -> str:
    return f"{product_id}:{'reverse' if reverse else 'plain'}"


def _averages(market: dict[str, Any], reverse: bool) -> tuple[Any, Any]:
    suffix = "-holo" if reverse else ""
    return market.get(f"avg1{suffix}"), market.get(f"avg7{suffix}")


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(SPIKE_SCHEMA)


def _advance(conn: sqlite3.Connection, series: str, guide_date: str, spiking: bool | None, now: str) -> None:
    """Apply one guide revision to one series. Older or repeated revisions change nothing."""
    row = conn.execute(
        "SELECT active, guide_date FROM price_spike_episodes WHERE series = ?", (series,)
    ).fetchone()
    if row is not None and str(row["guide_date"]) >= guide_date:
        return
    if row is None:
        if spiking:
            conn.execute(
                "INSERT OR IGNORE INTO price_spike_episodes (series, active, started_at, guide_date) VALUES (?, 1, ?, ?)",
                (series, now, guide_date),
            )
        return
    if spiking is None:
        # Missing averages neither clear nor rearm the episode.
        conn.execute(
            "UPDATE price_spike_episodes SET guide_date = ? WHERE series = ? AND guide_date < ?",
            (guide_date, series, guide_date),
        )
    elif spiking and not row["active"]:
        conn.execute(
            "UPDATE price_spike_episodes SET active = 1, started_at = ?, guide_date = ? WHERE series = ? AND guide_date < ?",
            (now, guide_date, series, guide_date),
        )
    else:
        conn.execute(
            "UPDATE price_spike_episodes SET active = ?, guide_date = ? WHERE series = ? AND guide_date < ?",
            (1 if spiking else 0, guide_date, series, guide_date),
        )


def record_guide_spikes(conn: sqlite3.Connection, guide_date: str, rows: Iterable[dict[str, Any]],
                        settings: Settings, now: str) -> None:
    """Open or close spike episodes for a newly imported price file."""
    ensure_schema(conn)
    for row in rows:
        product = row.get("idProduct")
        if not isinstance(product, int):
            continue
        for reverse in (False, True):
            avg1, avg7 = _averages(row, reverse)
            spiking = spike_predicate(avg1, avg7, settings.daily_spike_ratio, settings.daily_spike_floor_eur)
            _advance(conn, _series(product, reverse), guide_date, spiking, now)


def _guide(conn: sqlite3.Connection, url: str) -> tuple[int, bool, dict[str, Any]] | None:
    from app.cardmarket import normalize_product_url
    from app.price_sources import guide_market, is_reverse_holo_url

    row = conn.execute(
        "SELECT cardmarket_id FROM cards WHERE cardmarket_url = ? AND cardmarket_id IS NOT NULL LIMIT 1",
        (normalize_product_url(url) or url,),
    ).fetchone()
    market = guide_market(conn, row["cardmarket_id"]) if row else None
    if not market:
        return None
    return int(row["cardmarket_id"]), is_reverse_holo_url(url), market


def spike_started(conn: sqlite3.Connection, url: str | None, settings: Settings, now: str) -> str | None:
    """When the open spike episode for this key's product and finish began, if one is open."""
    if conn is None or not url or is_first_edition(url):
        return None
    try:
        found = _guide(conn, url)
        if found is None:
            return None
        product, reverse, market = found
        ensure_schema(conn)
        guide_date = str(market.get("updated") or "")
        if guide_date:
            avg1, avg7 = _averages(market, reverse)
            # A guide imported before episodes existed is processed here, once.
            _advance(conn, _series(product, reverse), guide_date,
                     spike_predicate(avg1, avg7, settings.daily_spike_ratio, settings.daily_spike_floor_eur), now)
            conn.commit()
        row = conn.execute(
            "SELECT active, started_at FROM price_spike_episodes WHERE series = ?", (_series(product, reverse),)
        ).fetchone()
    except sqlite3.Error:
        return None
    return str(row["started_at"]) if row is not None and row["active"] and row["started_at"] else None


def last_accepted_read(record: dict[str, Any] | None) -> str | None:
    """The newest accepted observation of this key: offers or an explicit empty listing."""
    stamps = []
    if (record or {}).get("prices"):
        stamps.append(str(record.get("observed_at") or record.get("fetched_at") or ""))
    if (record or {}).get("empty_observed_at"):
        stamps.append(str(record["empty_observed_at"]))
    stamps = [stamp for stamp in stamps if stamp]
    return max(stamps) if stamps else None


def spike_unconsumed(conn: sqlite3.Connection, url: str | None, record: dict[str, Any] | None,
                     settings: Settings, now: str) -> bool:
    started = spike_started(conn, url, settings, now)
    if started is None:
        return False
    read = last_accepted_read(record)
    return read is None or read < started


def listing_trend(record: dict[str, Any] | None) -> float | None:
    """The trend Cardmarket's own page showed on the last listing read."""
    for quote in (record or {}).get("prices") or []:
        if quote.get("label") == "Trend":
            amount = quote.get("amount")
            if isinstance(amount, (int, float)) and amount > 0:
                return float(amount)
    return None


def moving(conn: sqlite3.Connection, url: str | None, record: dict[str, Any] | None, settings: Settings,
           now: str, *, trend: float | None = None, pct: float | None = None) -> bool:
    """Whether this key may be read early: an unconsumed spike or a trend move."""
    if not url or is_first_edition(url):
        return False
    if trend is None:
        from app.price_sources import trend_for_url

        try:
            trend = trend_for_url(conn, url)
        except sqlite3.Error:
            trend = None
    move = settings.daily_move_pct if pct is None else pct
    if trend_moved(trend, listing_trend(record), move, settings.daily_move_floor_eur):
        return True
    return spike_unconsumed(conn, url, record, settings, now)
