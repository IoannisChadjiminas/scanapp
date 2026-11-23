"""Load corrections of cards' Cardmarket product numbers into the server's
own table (`app/card_products.py`). The catalogue itself is not changed.

    python scripts/apply_card_products.py corrections.csv /data/catalog.sqlite

The CSV has a header with `card_id` and `proposed_product`; rows with no
proposed product are skipped. Loading the same file again changes nothing.
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from datetime import datetime, timezone


def main(source: str, path: str) -> None:
    with open(source, newline="", encoding="utf-8") as handle:
        rows = [
            (row["card_id"], int(row["proposed_product"]))
            for row in csv.DictReader(handle)
            if (row.get("proposed_product") or "").strip().isdigit()
        ]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = sqlite3.connect(path, timeout=60)
    with conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS cardmarket_card_products (card_id TEXT PRIMARY KEY, "
            "product_id INTEGER, source TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.executemany(
            "INSERT INTO cardmarket_card_products (card_id, product_id, source, updated_at) "
            "VALUES (?, ?, 'review', ?) ON CONFLICT (card_id) DO UPDATE SET "
            "product_id = excluded.product_id, source = 'review', updated_at = excluded.updated_at",
            [(card, product, now) for card, product in rows],
        )
    print(f"corrections loaded: {len(rows)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
