"""The Cardmarket product a card's price-file row is read from.

The catalogue gives each card a product number. For about 1,800 cards that
number is another card's: two cards with different Cardmarket pages (the
holo and the non-holo of a name, two promos) share one number, so one of
them shows the other's price. The catalogue is published separately and is
not changed here; this local table says what the price file may be read with.

- A reviewed correction, or a number a phone read off the card's own page,
  is the card's product.
- A number shared by cards with different pages is nobody's until one of
  those says whose it is: no daily price is better than another card's.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS cardmarket_card_products (
    card_id TEXT PRIMARY KEY,
    product_id INTEGER,
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cardmarket_page_products (
    url TEXT PRIMARY KEY,
    product_id INTEGER NOT NULL,
    seen_at TEXT NOT NULL
);
"""

# The number to read the price file with, for a `cards` row joined to
# `cardmarket_card_products ov` on the card's id.
SQL_PRODUCT = "CASE WHEN ov.card_id IS NOT NULL THEN ov.product_id ELSE cards.cardmarket_id END"
SQL_JOIN = "LEFT JOIN cardmarket_card_products ov ON ov.card_id=cards.id"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_schema(conn: sqlite3.Connection) -> None:
    for statement in SCHEMA.split(";"):
        if statement.strip():
            conn.execute(statement)


def product_for(conn: sqlite3.Connection, card_id: Any, catalogue_id: Any) -> int | None:
    """The card's product: the local answer when there is one (which may be
    "not known"), else the catalogue's number."""
    try:
        row = conn.execute(
            "SELECT product_id FROM cardmarket_card_products WHERE card_id = ?", (str(card_id),)
        ).fetchone()
    except sqlite3.Error:  # a database from before the table
        row = None
    value = row[0] if row is not None else catalogue_id
    return int(value) if value is not None else None


def all_products(conn: sqlite3.Connection) -> dict[str, int | None]:
    """Every local answer, by card id."""
    try:
        return {str(row[0]): row[1] for row in conn.execute(
            "SELECT card_id, product_id FROM cardmarket_card_products")}
    except sqlite3.Error:
        return {}


def withhold_shared(conn: sqlite3.Connection) -> int:
    """Mark every card whose catalogue number is shared with a card on another
    Cardmarket page as not known, unless something already says. A page a
    phone read earlier names its card's product. Returns the cards withheld.
    Run after the catalogue is loaded."""
    ensure_schema(conn)
    now = _now()
    with conn:
        conn.execute("DELETE FROM cardmarket_card_products WHERE source = 'shared'")
        conn.execute(
            "INSERT OR IGNORE INTO cardmarket_card_products (card_id, product_id, source, updated_at) "
            "SELECT cards.id, NULL, 'shared', ? FROM cards WHERE cards.cardmarket_id IN ("
            "SELECT cardmarket_id FROM cards WHERE cardmarket_id IS NOT NULL AND cardmarket_url IS NOT NULL "
            "GROUP BY cardmarket_id HAVING COUNT(DISTINCT cardmarket_url) > 1)",
            (now,),
        )
        conn.execute(
            "UPDATE cardmarket_card_products SET product_id = ("
            "SELECT p.product_id FROM cards JOIN cardmarket_page_products p ON p.url = cards.cardmarket_url "
            "WHERE cards.id = cardmarket_card_products.card_id), source = 'page' "
            "WHERE source = 'shared' AND card_id IN ("
            "SELECT cards.id FROM cards JOIN cardmarket_page_products p ON p.url = cards.cardmarket_url)"
        )
    return conn.execute(
        "SELECT COUNT(*) FROM cardmarket_card_products WHERE source = 'shared'").fetchone()[0]


def remember_page(conn: sqlite3.Connection, url: str, product_id: int) -> None:
    """A phone read this Cardmarket page and it named its own product. Kept
    by page; a card whose main page it is, and whose number was withheld or
    read from a page before, now has it."""
    ensure_schema(conn)
    now = _now()
    with conn:
        conn.execute(
            "INSERT INTO cardmarket_page_products (url, product_id, seen_at) VALUES (?, ?, ?) "
            "ON CONFLICT (url) DO UPDATE SET product_id = excluded.product_id, seen_at = excluded.seen_at",
            (url, int(product_id), now),
        )
        conn.execute(
            "UPDATE cardmarket_card_products SET product_id = ?, source = 'page', updated_at = ? "
            "WHERE source IN ('shared', 'page') AND card_id IN ("
            "SELECT id FROM cards WHERE cardmarket_url = ?)",
            (int(product_id), now, url),
        )


def apply_review(conn: sqlite3.Connection, corrections: dict[str, int | None]) -> int:
    """Reviewed corrections, by card id. They outrank everything else."""
    ensure_schema(conn)
    now = _now()
    with conn:
        conn.executemany(
            "INSERT INTO cardmarket_card_products (card_id, product_id, source, updated_at) "
            "VALUES (?, ?, 'review', ?) ON CONFLICT (card_id) DO UPDATE SET "
            "product_id = excluded.product_id, source = 'review', updated_at = excluded.updated_at",
            [(card, product, now) for card, product in corrections.items()],
        )
    return len(corrections)
