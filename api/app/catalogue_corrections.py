"""Reviewed catalogue corrections, re-applied on every catalogue load.

The served catalogue snapshot was corrected in place on 25 November 2026
(foreign-language prints unlinked from English cards, a dead Cardmarket
address replaced). A release built by cloning that snapshot keeps the fixes;
a release built from an older snapshot or from scratch would not. This file
is the safety net: the server applies it to whatever catalogue it loads,
before the catalogue is made read-only. On a catalogue that already has the
fixes, nothing changes.

Each row only acts while the catalogue still holds the exact wrong value, so
a later catalogue that fixed the row differently is left alone.

- ``unlink``: the listing ``url`` stops being a listing of ``card_id``.
- ``replace_url``: the card's address ``url`` becomes ``new_url``. Its listing
  row moves too (with ``new_image``), unless a ``new_url`` row already exists.

See docs/planetscale-staging.md.
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

CORRECTIONS = Path(__file__).with_name("catalogue_corrections.csv")
ACTIONS = {"unlink", "replace_url"}


def load(path: Path = CORRECTIONS) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row["action"] not in ACTIONS or not row["url"] or not row["card_id"]:
            raise ValueError(f"bad catalogue correction: {row['url']}")
        if row["action"] == "replace_url" and not row["new_url"]:
            raise ValueError(f"replace_url without new_url: {row['url']}")
    return rows


def apply(conn: sqlite3.Connection, schema: str = "main", path: Path = CORRECTIONS) -> int:
    """Apply the corrections to ``schema``'s catalogue tables; returns rows changed."""
    cards, products = f"{schema}.cards", f"{schema}.cardmarket_expansion_products"
    has_image = "listing_image_url" in {r[1] for r in conn.execute(f"PRAGMA {schema}.table_info(cardmarket_expansion_products)")}
    changed = 0
    for row in load(path):
        url, card = row["url"], row["card_id"]
        if row["action"] == "unlink":
            changed += conn.execute(
                f"UPDATE {products} SET matched=0, card_id=NULL WHERE url=? AND card_id=?", (url, card)).rowcount
            continue
        new = row["new_url"]
        changed += conn.execute(
            f"UPDATE {cards} SET cardmarket_url=? WHERE id=? AND cardmarket_url=?", (new, card, url)).rowcount
        if conn.execute(f"SELECT 1 FROM {products} WHERE url=?", (new,)).fetchone():
            continue
        image = ", listing_image_url=?" if has_image and row["new_image"] else ""
        params = (new, row["new_image"], url, card) if image else (new, url, card)
        changed += conn.execute(
            f"UPDATE {products} SET url=?{image} WHERE url=? AND card_id=?", params).rowcount
    return changed
