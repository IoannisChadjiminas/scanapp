"""Local search statistics, rebuilt after a successful nightly guide import.

History can live in Postgres; searches only join these small SQLite rows.
Daily import receipts distinguish fill-forward days from missing observations.
"""
from __future__ import annotations

from bisect import bisect_right
from datetime import date, timedelta
from math import isfinite

FIELDS = ('trend_7d_ago', 'trend_30d_ago', 'sales_days_30', 'weekly_min_change')


def ensure_schema(conn) -> None:
    conn.execute('''CREATE TABLE IF NOT EXISTS card_market_stats (
        id_product INTEGER NOT NULL, basis TEXT NOT NULL, as_of TEXT NOT NULL,
        trend_7d_ago REAL, trend_30d_ago REAL, sales_days_30 INTEGER,
        weekly_min_change REAL, PRIMARY KEY (id_product, basis))''')
    conn.execute('CREATE INDEX IF NOT EXISTS card_market_stats_date ON card_market_stats(as_of)')


def positive(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) and value > 0 else None


def rebuild(catalog, history, as_of: str) -> int:
    """Read once in bulk, then atomically replace local stats. Never invent
    earlier prices or sales on a day whose import did not finish."""
    from app.portfolio_db import statement

    today = date.fromisoformat(as_of[:10])
    cutoff = (today - timedelta(days=30)).isoformat()
    # One seed on/before the boundary, plus changed rows inside the window.
    rows = history.execute(statement(history, """SELECT h.* FROM price_history_daily h
        JOIN (SELECT id_product, MAX(day) AS day FROM price_history_daily
              WHERE day<=? GROUP BY id_product) seed
        ON h.id_product=seed.id_product AND h.day=seed.day
        UNION ALL SELECT * FROM price_history_daily WHERE day>? AND day<=?
        ORDER BY id_product, day"""), (cutoff, cutoff, today.isoformat())).fetchall()
    receipts = {str(row['day']) for row in history.execute(statement(history,
        'SELECT day FROM price_guide_import_days WHERE day>=? AND day<=?'),
        (cutoff, today.isoformat())).fetchall()}
    products = {row['id_product'] for row in catalog.execute('SELECT id_product FROM cardmarket_guide')}
    grouped = {}
    for row in rows:
        if row['id_product'] in products:
            grouped.setdefault(row['id_product'], []).append(dict(row))
    pending = []
    for product, points in grouped.items():
        days = [row['day'] for row in points]
        def at(day):
            index = bisect_right(days, day.isoformat()) - 1
            return points[index] if index >= 0 else None
        for basis in ('normal', 'holo'):
            def value(day, field):
                row = at(day)
                if row is None:
                    return None
                first, second = (field, field + '_holo') if basis == 'normal' else (field + '_holo', field)
                return positive(row[first]) or positive(row[second])
            seven = value(today - timedelta(days=7), 'trend')
            thirty = value(today - timedelta(days=30), 'trend')
            window = [today - timedelta(days=offset) for offset in range(30)]
            complete = all(day.isoformat() in receipts and value(day, 'trend') is not None for day in window)
            sales = sum(value(day, 'avg1') is not None for day in window) if complete else None
            weekly = [value(today - timedelta(days=offset), 'trend') for offset in (30, 28, 21, 14, 7, 0)]
            min_change = min(b / a - 1 for a, b in zip(weekly, weekly[1:])) if all(weekly) else None
            pending.append((product, basis, today.isoformat(), seven, thirty, sales, min_change))
    ensure_schema(catalog)
    with catalog:
        catalog.execute('DELETE FROM card_market_stats')
        catalog.executemany('INSERT INTO card_market_stats VALUES (?, ?, ?, ?, ?, ?, ?)', pending)
    return len(pending)


def capabilities(catalog) -> dict[str, bool]:
    row = catalog.execute('''SELECT MAX(s.trend_7d_ago IS NOT NULL) AS seven,
        MAX(s.trend_30d_ago IS NOT NULL) AS thirty, MAX(s.sales_days_30 IS NOT NULL) AS liquidity
        FROM card_market_stats s JOIN cardmarket_guide g ON g.id_product=s.id_product
        WHERE s.as_of=SUBSTR(g.guide_date, 1, 10)''').fetchone()
    return {'change_7d': bool(row['seven']), 'change_30d': bool(row['thirty']), 'liquidity_30d': bool(row['liquidity'])}
