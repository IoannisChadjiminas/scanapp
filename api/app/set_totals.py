"""The number printed after the slash on a card, e.g. 35/108.

TCGdex lists every set with its printed total. The nightly pass stores one row
per set in the local database, so a scan or a search can add the total to a card
without touching the card catalogue itself. It keeps each set's release date
the same way, so a search can list the newest expansions first.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from time import sleep
from typing import Any
from urllib.parse import quote

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


# Japanese sets sold as two halves: the catalogue keeps one set id per half, TCGdex lists the
# printed total under its own id. Both halves of every pair print the same total.
JA_TOTAL_ALIASES = {
    "BW1-Bb": "BW1a", "BW1-Bw": "BW1b",      # Black / White Collection, /053
    "BW3-Bh": "BW3a", "BW3-Bp": "BW3a",      # Hail Blizzard / Psycho Drive, /052
    "BW5-Brn": "BW5a", "BW5-Brz": "BW5b",    # Dragon Blade / Dragon Blast, /050
    "BW6-Bc": "BW6a", "BW6-Bf": "BW6b",      # Cold Flare / Freeze Bolt, /059
    "BW8-Brf": "BW8a", "BW8-Brn": "BW8a",    # Spiral Force / Thunder Knuckle, /051
    "L1HG": "L1a", "L1SS": "L1b",            # HeartGold / SoulSilver Collection, /070
    "XY1-Bx": "XY1a", "XY1-By": "XY1b",      # Collection X / Y, /060
    "XY5-Bg": "XY5a", "XY5-Bt": "XY5b",      # Gaia Volcano / Tidal Storm, /070
    "XY8-Br": "XY8a", "XY8-Bb": "XY8b",      # Red Flash / Blue Shock, /059
    "XY11-Bb": "XY11a", "XY11-Br": "XY11b",  # Fever-Burst Fighter / Cruel Traitor, /054
}
# Totals TCGdex has wrong. Thunderclap Spark prints /060 (its cards 51-60 are commons and
# uncommons); TCGdex lists 50.
TOTAL_CORRECTIONS = {("ja", "SM7a"): 60}


def _aliases_enabled() -> bool:
    try:
        from app.config import get_settings
        return bool(getattr(get_settings(), "set_total_aliases", False))
    except Exception:
        return False


def _stored_total(conn: sqlite3.Connection, language: str, set_id: str) -> int | None:
    row = conn.execute(
        "SELECT official_total FROM set_totals WHERE language = ? AND set_id = ?", (language, set_id)
    ).fetchone()
    return int(row[0]) if row else None


def set_total(conn: sqlite3.Connection, language: Any, set_id: Any) -> int | None:
    """Printed total of a set, or None when it is not known. Never raises."""
    language, set_id = str(language or "en").lower(), str(set_id or "")
    aliases = _aliases_enabled()
    if aliases and (language, set_id) in TOTAL_CORRECTIONS:
        return TOTAL_CORRECTIONS[(language, set_id)]
    try:
        total = _stored_total(conn, language, set_id)
        if total is None and aliases and language == "ja" and set_id in JA_TOTAL_ALIASES:
            total = _stored_total(conn, language, JA_TOTAL_ALIASES[set_id])
    except sqlite3.Error:
        return None
    return total


_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def refresh_set_releases(
    conn: sqlite3.Connection, settings: Settings, *, catalog: sqlite3.Connection | None = None
) -> int:
    """Store the release date of every set the catalogue holds, so a search can
    show the newest expansions first.

    A date never changes, so only sets without one are asked for: the first
    pass asks once per set, later passes only for new sets. A set TCGdex has no
    date for is asked again after a week.
    """
    source = catalog if catalog is not None else conn
    known = {
        (str(row[0]), str(row[1]))
        for row in conn.execute(
            "SELECT language, set_id FROM set_releases WHERE release_date IS NOT NULL OR fetched_at > ?",
            ((datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),),
        )
    }
    wanted = sorted(
        {(str(row[0] or "en").lower(), str(row[1])) for row in source.execute("SELECT DISTINCT language, set_id FROM cards")}
        - known
    )
    stored = 0
    with httpx.Client(timeout=30) as client:
        for language, set_id in wanted:
            try:
                response = client.get(f"{settings.tcgdex_base_url}/{language}/sets/{quote(set_id, safe='')}")
                response.raise_for_status()
                body = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                log.info("set release failed language=%s set=%s error=%s", language, set_id, type(exc).__name__)
                continue
            value = str(body.get("releaseDate") or "") if isinstance(body, dict) else ""
            date = value[:10] if _DATE.match(value) else None
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO set_releases (language, set_id, release_date, fetched_at) VALUES (?, ?, ?, ?)",
                    (language, set_id, date, now),
                )
            stored += date is not None
            sleep(max(0.0, float(settings.tcgdex_prices_gap_s)))
    log.info("set releases refreshed sets=%s asked=%s", stored, len(wanted))
    return stored
