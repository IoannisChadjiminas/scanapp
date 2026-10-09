"""The number printed after the slash on a card, e.g. 35/108.

TCGdex lists every set with its printed total. The nightly pass stores one row
per set in the local database, so a scan or a search can add the total to a card
without touching the card catalogue itself.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings

log = logging.getLogger("set.totals")


def official_total(set_info: dict[str, Any]) -> int | None:
    counts = set_info.get("cardCount") if isinstance(set_info, dict) else None
    if not isinstance(counts, dict):
        return None
    for key in ("official", "total"):
        try:
            value = int(counts.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def refresh_set_totals(
    conn: sqlite3.Connection, settings: Settings, *, catalog: sqlite3.Connection | None = None
) -> int:
    """Store the printed total of every set in the languages the catalogue holds.

    One request per language. A failed language keeps its older rows.
    """
    source = catalog if catalog is not None else conn
    languages = sorted({str(row[0] or "en").lower() for row in source.execute("SELECT DISTINCT language FROM cards")})
    stored = 0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with httpx.Client(timeout=30) as client:
        for language in languages:
            try:
                response = client.get(f"{settings.tcgdex_base_url}/{language}/sets")
                response.raise_for_status()
                body = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                log.info("set totals failed language=%s error=%s", language, type(exc).__name__)
                continue
            rows = [
                (language, str(item.get("id")), total, now)
                for item in (body if isinstance(body, list) else [])
                if isinstance(item, dict) and item.get("id") and (total := official_total(item))
            ]
            if not rows:
                continue
            with conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO set_totals (language, set_id, official_total, fetched_at) VALUES (?, ?, ?, ?)",
                    rows,
                )
            stored += len(rows)
    log.info("set totals refreshed sets=%s", stored)
    return stored


def set_total(conn: sqlite3.Connection, language: Any, set_id: Any) -> int | None:
    """Printed total of a set, or None when it is not known. Never raises."""
    try:
        row = conn.execute(
            "SELECT official_total FROM set_totals WHERE language = ? AND set_id = ?",
            (str(language or "en").lower(), str(set_id or "")),
        ).fetchone()
    except sqlite3.Error:
        return None
    return int(row[0]) if row else None
