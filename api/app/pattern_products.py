"""Reverse holo patterns Cardmarket sells as their own products.

Poké Ball, Master Ball, Energy and the other patterns of sets such as
Prismatic Evolutions or JP 151 are separate Cardmarket products, kept in the
"Additionals" expansions. `cardmarket_pattern_products.csv` ships the reviewed
list (see docs/cardmarket-pattern-products.md). At start it is copied into a
local table, and each listing's product number is remembered by URL, so a
pattern a collector picks is priced from its own row in the price file.

The catalogue's `cardmarket_expansion_products` is read-only on the cloud
catalogue, so the patterns live beside it rather than in it.
"""
from __future__ import annotations

import csv
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("cardmarket.patterns")

REVIEWED = Path(__file__).with_name("cardmarket_pattern_products.csv")

SCHEMA = """
CREATE TABLE IF NOT EXISTS cardmarket_pattern_products (
    product_id INTEGER PRIMARY KEY,
    card_id TEXT NOT NULL,
    pattern TEXT NOT NULL,
    url TEXT NOT NULL,
    image TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pattern_products_card ON cardmarket_pattern_products(card_id);
"""

LABELS = {
    "pokeball": "Poké Ball",
    "masterball": "Master Ball",
    "energy": "Energy",
    "loveball": "Love Ball",
    "duskball": "Dusk Ball",
    "quickball": "Quick Ball",
    "friendball": "Friend Ball",
    "team-rocket": "Team Rocket",
}

_IMAGE_HOST = "https://product-images.s3.cardmarket.com/"


def read_reviewed(path: Path = REVIEWED) -> list[dict[str, Any]]:
    """The listings in a reviewed file; rows without a product or link are skipped."""
    with open(path, newline="", encoding="utf-8") as handle:
        rows = []
        for row in csv.DictReader(handle):
            product = (row.get("product_id") or "").strip()
            url = (row.get("url") or "").strip()
            if row.get("card_id") and product.isdigit() and url.startswith("https://www.cardmarket.com/"):
                rows.append({
                    "product_id": int(product),
                    "card_id": row["card_id"].strip(),
                    "pattern": (row.get("pattern") or "").strip(),
                    "url": url,
                    "image": (row.get("image") or "").strip(),
                })
        return rows


def apply_reviewed_file(conn: sqlite3.Connection, path: Path = REVIEWED) -> int:
    """Load the shipped list at start, replacing the previous one, and
    remember each listing's product by URL for pricing. Returns the rows
    loaded; a missing file loads none."""
    if not path.exists():
        return 0
    from app.card_products import ensure_schema

    rows = read_reviewed(path)
    ensure_schema(conn)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with conn:
        conn.executescript(SCHEMA)
        conn.execute("DELETE FROM cardmarket_pattern_products")
        conn.executemany(
            "INSERT INTO cardmarket_pattern_products (product_id, card_id, pattern, url, image) "
            "VALUES (:product_id, :card_id, :pattern, :url, :image)",
            rows,
        )
        conn.executemany(
            "INSERT INTO cardmarket_page_products (url, product_id, seen_at) VALUES (?, ?, ?) "
            "ON CONFLICT (url) DO UPDATE SET product_id = excluded.product_id",
            [(row["url"], row["product_id"], now) for row in rows],
        )
    return len(rows)


def label(pattern: str, url: str) -> str:
    """"Master Ball" for a known pattern, else the listing's version ("V2")."""
    if pattern in LABELS:
        return LABELS[pattern]
    match = re.search(r"-(V\d+)-x[^/]*$", url)
    return match.group(1) if match else ""


def variants(conn: sqlite3.Connection, card_id: str) -> list[dict[str, Any]]:
    """The card's pattern listings as version records, V1 first."""
    try:
        rows = conn.execute(
            "SELECT product_id, pattern, url FROM cardmarket_pattern_products WHERE card_id = ? "
            "ORDER BY url", (card_id,),
        ).fetchall()
    except sqlite3.OperationalError:  # not loaded yet
        return []
    from app.cardmarket import product_slug

    return [{
        "url": row["url"],
        "slug": product_slug(row["url"]),
        "label": label(row["pattern"], row["url"]),
        "card_id": card_id,
        "image": f"/api/v1/cardmarket/listing-images/{row['product_id']}.jpg",
    } for row in rows]


def image_source(conn: sqlite3.Connection, product_id: int) -> str | None:
    """Cardmarket's photo of a pattern product, if it is one."""
    try:
        row = conn.execute(
            "SELECT image FROM cardmarket_pattern_products WHERE product_id = ?", (product_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    image = str(row["image"]) if row else ""
    return image if image.startswith(_IMAGE_HOST) else None


def fetch_image(source: str, target: Path) -> bool:
    """Save a Cardmarket product photo. Its host answers only requests that
    come from Cardmarket's own pages, hence the referrer."""
    import httpx

    try:
        response = httpx.get(
            source,
            headers={
                "Referer": "https://www.cardmarket.com/",
                "User-Agent": "Mozilla/5.0 (compatible; PokeSingle image cache)",
            },
            timeout=15,
        )
    except httpx.HTTPError as exc:
        log.info("pattern image fetch failed error=%s", type(exc).__name__)
        return False
    if response.status_code != 200 or not response.headers.get("content-type", "").startswith("image/"):
        log.info("pattern image fetch refused status=%s", response.status_code)
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".part")
    partial.write_bytes(response.content)
    partial.replace(target)
    return True
