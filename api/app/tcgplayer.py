"""TCGplayer's daily prices for a catalogue card.

TCGplayer gives no access to its sellers, so this is not a listing read: it is
the market price (what copies recently sold for) with the lowest and middle
listing, in dollars, from TCGCSV's public daily copy of TCGplayer's price
data. A card is found through CardTrader's card list, which carries the
TCGplayer product id beside the Cardmarket one (app/cardtrader.py).
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("tcgplayer")

SOURCE = "https://tcgcsv.com"
# TCGplayer's categories: Pokémon, and Pokémon Japan.
CATEGORIES = (3, 85)
USER_AGENT = "scanapp-prices/1.0"

# Which printing's price a copy takes, most wanted first.
_PLAIN = ("Normal", "Holofoil", "Unlimited", "Unlimited Holofoil")
_FIRST = ("1st Edition", "1st Edition Holofoil")
_REVERSE = ("Reverse Holofoil",)


def pick_printing(
    rows: dict[str, dict[str, Any]], *, reverse: bool, first_edition: bool | None
) -> dict[str, Any] | None:
    """The price row for the copy, or None when TCGplayer has no such printing."""
    if reverse:
        order = _REVERSE
    elif first_edition:
        order = _FIRST
    else:
        order = _PLAIN
    return next((rows[name] for name in order if name in rows), None)


def price_rows(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Market first; nothing at all without a market price."""
    found = []
    for label, field in (("Market", "market"), ("Low", "low"), ("Mid", "mid")):
        amount = row.get(field)
        if isinstance(amount, (int, float)) and amount > 0:
            found.append({
                "label": label,
                "amount": round(float(amount), 2),
                "currency": "USD",
                "source": "tcgplayer",
            })
    return found if found and found[0]["label"] == "Market" else []


class TcgplayerPrices:
    """The day's prices by product, imported again once a day old."""

    def __init__(
        self,
        path: Path,
        *,
        max_age_s: int = 86400,
        client: httpx.Client | None = None,
    ) -> None:
        self.max_age_s = max_age_s
        self._client = client or httpx.Client(
            base_url=SOURCE, timeout=30, headers={"User-Agent": USER_AGENT}
        )
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS prices (
                product_id INTEGER NOT NULL,
                printing TEXT NOT NULL,
                market REAL, low REAL, mid REAL,
                PRIMARY KEY (product_id, printing)
            );
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            """
        )
        self._importing = False

    def close(self) -> None:
        self._client.close()
        with self._lock:
            self._conn.close()

    def _meta(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def refresh_if_stale(self) -> None:
        imported = self._meta("imported_at")
        if imported is not None and time.time() - float(imported) < self.max_age_s:
            return
        with self._lock:
            if self._importing:
                return
            self._importing = True
        threading.Thread(target=self._import_guarded, name="tcgplayer-prices", daemon=True).start()

    def _import_guarded(self) -> None:
        try:
            log.info("tcgplayer prices imported rows=%s", self.import_prices())
        except Exception as exc:  # yesterday's prices stay in use
            log.warning("tcgplayer price import failed error_type=%s", type(exc).__name__)
        finally:
            with self._lock:
                self._importing = False

    def import_prices(self, *, pause_s: float = 0.1) -> int:
        stamp = self._client.get("/last-updated.txt")
        stamp.raise_for_status()
        rows: list[tuple[int, str, Any, Any, Any]] = []
        for category in CATEGORIES:
            groups = self._client.get(f"/tcgplayer/{category}/groups")
            groups.raise_for_status()
            for group in groups.json().get("results") or []:
                reply = self._client.get(f"/tcgplayer/{category}/{group['groupId']}/prices")
                reply.raise_for_status()
                for item in reply.json().get("results") or []:
                    if item.get("marketPrice") is None and item.get("lowPrice") is None:
                        continue
                    rows.append((
                        int(item["productId"]),
                        str(item.get("subTypeName") or "Normal"),
                        item.get("marketPrice"),
                        item.get("lowPrice"),
                        item.get("midPrice"),
                    ))
                time.sleep(pause_s)
        if not rows:
            raise ValueError("no prices")
        with self._lock:
            with self._conn:
                self._conn.execute("DELETE FROM prices")
                self._conn.executemany("INSERT OR REPLACE INTO prices VALUES (?, ?, ?, ?, ?)", rows)
                self._conn.executemany(
                    "INSERT OR REPLACE INTO meta VALUES (?, ?)",
                    [("imported_at", str(time.time())), ("priced_at", stamp.text.strip())],
                )
        return len(rows)

    def prices(
        self, product_id: int | None, *, reverse: bool = False, first_edition: bool | None = None
    ) -> dict[str, Any]:
        self.refresh_if_stale()
        found: list[dict[str, Any]] = []
        if product_id is not None:
            with self._lock:
                stored = self._conn.execute(
                    "SELECT printing, market, low, mid FROM prices WHERE product_id = ?",
                    (product_id,),
                ).fetchall()
            rows = {r[0]: {"market": r[1], "low": r[2], "mid": r[3]} for r in stored}
            chosen = pick_printing(rows, reverse=reverse, first_edition=first_edition)
            found = price_rows(chosen) if chosen else []
        return {
            "enabled": True,
            "prices": found,
            "observed_at": _utc(self._meta("priced_at")) if found else None,
        }


def _utc(stamp: str | None) -> str | None:
    """TCGCSV's "2026-11-20T20:06:21+0000" as the app's UTC stamp."""
    try:
        at = datetime.strptime(stamp or "", "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None
    return at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
