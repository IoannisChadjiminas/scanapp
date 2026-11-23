"""Once: apply the import's broken-trend rule to rows already stored.

The nightly import replaces a trend Cardmarket published broken (far below
both the lowest listing and the 7-day average) with the 7-day average. This
does the same for the stored guide and the daily history, in a SQLite file:

    python scripts/repair_broken_trends.py /data/catalog.sqlite
"""
from __future__ import annotations

import sqlite3
import sys

RULE = "{t}>0 AND {l}>0 AND {a}>0 AND {t}<{l}*0.5 AND {t}<{a}*0.25"
PLAIN = RULE.format(t="trend", l="low", a="avg7")
HOLO = RULE.format(t="trend_holo", l="low_holo", a="avg7_holo")


def tables(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def main(path: str) -> None:
    conn = sqlite3.connect(path, timeout=60)
    have = tables(conn)
    with conn:
        if "cardmarket_guide" in have:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS cardmarket_trend_repairs ("
                "id_product INTEGER PRIMARY KEY, plain INTEGER NOT NULL, holo INTEGER NOT NULL)"
            )
            conn.execute(
                "INSERT INTO cardmarket_trend_repairs (id_product, plain, holo) "
                f"SELECT id_product, COALESCE({PLAIN}, 0), COALESCE({HOLO}, 0) FROM cardmarket_guide "
                f"WHERE COALESCE({PLAIN}, 0) OR COALESCE({HOLO}, 0) "
                "ON CONFLICT (id_product) DO UPDATE SET "
                "plain=MAX(plain, excluded.plain), holo=MAX(holo, excluded.holo)"
            )
            # Both columns in one statement: each test reads the stored row.
            guide = conn.execute(
                f"UPDATE cardmarket_guide SET "
                f"trend=CASE WHEN COALESCE({PLAIN}, 0) THEN avg7 ELSE trend END, "
                f"trend_holo=CASE WHEN COALESCE({HOLO}, 0) THEN avg7_holo ELSE trend_holo END "
                f"WHERE COALESCE({PLAIN}, 0) OR COALESCE({HOLO}, 0)"
            ).rowcount
            print(f"guide rows repaired: {guide}")
        if "price_history_daily" in have:
            history = conn.execute(
                f"UPDATE price_history_daily SET "
                f"trend=CASE WHEN COALESCE({PLAIN}, 0) THEN avg7 ELSE trend END, "
                f"trend_holo=CASE WHEN COALESCE({HOLO}, 0) THEN avg7_holo ELSE trend_holo END "
                f"WHERE COALESCE({PLAIN}, 0) OR COALESCE({HOLO}, 0)"
            ).rowcount
            print(f"history rows repaired: {history}")


if __name__ == "__main__":
    main(sys.argv[1])
