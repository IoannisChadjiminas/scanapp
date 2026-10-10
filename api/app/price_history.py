"""Price history, kept so a chart can be drawn later.

Two tables, written to the portfolio database (PlanetScale) when it is
configured and to the local SQLite file otherwise. The DDL runs on both.

``price_history_daily``: Cardmarket's nightly price file, one row per product
per day. A product whose figures did not change since its last stored row is
skipped, so a reader fills forward from the latest row on or before a day.

``price_sales_daily``: the "Avg. Sell Price" chart on a Cardmarket product page,
one row per product per day that had sales. Cardmarket only shows a few
months, so these rows are the only copy of older days.
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any, Iterable

log = logging.getLogger("price.history")

HISTORY_FIELDS = (
    "avg", "low", "trend", "avg1", "avg7", "avg30",
    "avg_holo", "low_holo", "trend_holo", "avg1_holo", "avg7_holo", "avg30_holo",
)
CHUNK = 2000

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS price_history_daily (
        id_product INTEGER NOT NULL,
        day TEXT NOT NULL,
        avg DOUBLE PRECISION, low DOUBLE PRECISION, trend DOUBLE PRECISION,
        avg1 DOUBLE PRECISION, avg7 DOUBLE PRECISION, avg30 DOUBLE PRECISION,
        avg_holo DOUBLE PRECISION, low_holo DOUBLE PRECISION, trend_holo DOUBLE PRECISION,
        avg1_holo DOUBLE PRECISION, avg7_holo DOUBLE PRECISION, avg30_holo DOUBLE PRECISION,
        PRIMARY KEY (id_product, day)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS price_sales_daily (
        product_url TEXT NOT NULL,
        day TEXT NOT NULL,
        price DOUBLE PRECISION NOT NULL,
        PRIMARY KEY (product_url, day)
    )
    """,
)

_AVG_LABEL = re.compile(r"Avg (\d{2})\.(\d{2})\.(\d{4})")
_lock = threading.Lock()
_sink: Any = None


def ensure_schema(conn) -> None:
    for ddl in SCHEMA:
        conn.execute(ddl)
    conn.commit()


def bind(conn) -> None:
    """Connection that product reads write sales history to. None turns it off."""
    global _sink
    if conn is not None:
        try:
            ensure_schema(conn)
        except Exception as exc:
            log.info("sales history schema failed error=%s", type(exc).__name__)
            conn = None
    _sink = conn


def _sql(conn, sql: str) -> str:
    from app.portfolio_db import statement

    return statement(conn, sql)


def _value(row: Any, name: str) -> Any:
    return row[name]


def record_guide(conn, date: str, entries: Iterable[dict[str, Any]]) -> int:
    """Store one day of the price file. Returns the rows written."""
    day = date[:10]
    ensure_schema(conn)
    latest = {
        _value(row, "id_product"): tuple(_value(row, name) for name in HISTORY_FIELDS)
        for row in conn.execute(
            _sql(
                conn,
                "SELECT h.id_product, "
                + ", ".join(f"h.{name}" for name in HISTORY_FIELDS)
                + " FROM price_history_daily h JOIN ("
                "SELECT id_product, MAX(day) AS day FROM price_history_daily "
                "WHERE day <= ? GROUP BY id_product) m "
                "ON m.id_product = h.id_product AND m.day = h.day",
            ),
            (day,),
        ).fetchall()
    }
    pending = []
    for entry in entries:
        values = tuple(entry.get(name) for name in HISTORY_FIELDS)
        if all(value is None for value in values):
            continue
        if latest.get(entry["id_product"]) == values:
            continue
        pending.append((entry["id_product"], day, *values))
    sql = _sql(
        conn,
        f"INSERT INTO price_history_daily (id_product, day, {', '.join(HISTORY_FIELDS)}) "
        f"VALUES (?, ?, {', '.join('?' for _ in HISTORY_FIELDS)}) "
        "ON CONFLICT (id_product, day) DO UPDATE SET "
        + ", ".join(f"{name} = excluded.{name}" for name in HISTORY_FIELDS),
    )
    for start in range(0, len(pending), CHUNK):
        conn.executemany(sql, pending[start : start + CHUNK])
        conn.commit()
    return len(pending)


def guide_history(conn, id_product: int, since: str | None = None) -> list[dict[str, Any]]:
    """Stored rows for a product, oldest first. Days between rows had no change."""
    rows = conn.execute(
        _sql(
            conn,
            "SELECT * FROM price_history_daily WHERE id_product = ? AND day >= ? ORDER BY day",
        ),
        (id_product, since or ""),
    ).fetchall()
    return [{name: _value(row, name) for name in ("day", *HISTORY_FIELDS)} for row in rows]


def sales_from_prices(prices: Iterable[dict[str, Any]]) -> list[tuple[str, float]]:
    """(ISO day, price) for the "Avg dd.mm.yyyy" quotes a read stores."""
    points = []
    for price in prices:
        match = _AVG_LABEL.fullmatch(str(price.get("label") or ""))
        amount = price.get("amount")
        if not match or isinstance(amount, bool) or not isinstance(amount, (int, float)):
            continue
        if not 0 < float(amount) <= 1_000_000:
            continue
        day, month, year = match.groups()
        points.append((f"{year}-{month}-{day}", float(amount)))
    return points


def record_sales(url: str, prices: Iterable[dict[str, Any]], *, own: Any = None) -> int:
    """Store the sold-price chart of a read. Never raises: history must not
    break the snapshot write that called it.

    ``own`` is the connection the caller is writing on. When the history sink
    is that same connection the rows join the caller's transaction and the
    caller commits.
    """
    conn = _sink
    if conn is None:
        return 0
    try:
        from app.cardmarket import normalize_product_url

        product = normalize_product_url(url)
        points = sales_from_prices(prices)
        if not product or not points:
            return 0
        sql = _sql(
            conn,
            "INSERT INTO price_sales_daily (product_url, day, price) VALUES (?, ?, ?) "
            "ON CONFLICT (product_url, day) DO UPDATE SET price = excluded.price",
        )
        with _lock:
            conn.executemany(sql, [(product, day, price) for day, price in points])
            if conn is not own:
                conn.commit()
        return len(points)
    except Exception as exc:
        log.info("sales history failed error=%s", type(exc).__name__)
        try:
            if conn is not own:
                conn.rollback()
        except Exception:
            pass
        return 0
