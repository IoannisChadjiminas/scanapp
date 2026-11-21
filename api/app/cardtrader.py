"""CardTrader seller listings for a catalogue card, read from CardTrader's API.

The server asks, never the phone: one authorised request per card, reused for
an hour. A card is found by its Cardmarket product id, which every CardTrader
blueprint carries; that list is imported in the background and kept in its own
sqlite file, apart from the catalogue.
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

log = logging.getLogger("cardtrader")

API = "https://api.cardtrader.com/api/v2"
POKEMON_GAME_ID = 5
MAX_ROWS = 20
MAX_BLUEPRINTS = 3
USER_AGENT = "scanapp-cardtrader/1.0"

# CardTrader's condition names, best first, with the short codes the app and
# Cardmarket use.
CONDITIONS = {
    "Mint": "MT",
    "Near Mint": "NM",
    "Slightly Played": "EX",
    "Moderately Played": "GD",
    "Played": "LP",
    "Heavily Played": "PL",
    "Poor": "PO",
}
_RANK = {code: rank for rank, code in enumerate(CONDITIONS.values())}

# Catalogue language code -> CardTrader's `pokemon_language`.
LANGUAGE_CODES = {
    "en": "en", "ja": "jp", "jp": "jp", "fr": "fr", "de": "de", "it": "it",
    "es": "es", "pt": "pt", "nl": "nl", "ko": "kr", "kr": "kr", "ru": "ru",
    "zh-cn": "zh-CN", "zh-tw": "zh-TW",
}
# The names the app's offer rows know (a flag each).
LANGUAGE_NAMES = {
    "en": "English", "jp": "Japanese", "fr": "French", "de": "German",
    "it": "Italian", "es": "Spanish", "pt": "Portuguese", "nl": "Dutch",
    "kr": "Korean", "ru": "Russian", "zh-CN": "Simplified Chinese",
    "zh-TW": "Traditional Chinese",
}
COUNTRY_NAMES = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "CA": "Canada",
    "HR": "Croatia", "CY": "Cyprus", "CZ": "Czechia", "DK": "Denmark",
    "EE": "Estonia", "FI": "Finland", "FR": "France", "DE": "Germany",
    "GR": "Greece", "HK": "Hong Kong", "HU": "Hungary", "IS": "Iceland",
    "IE": "Ireland", "IT": "Italy", "JP": "Japan", "LV": "Latvia",
    "LI": "Liechtenstein", "LT": "Lithuania", "LU": "Luxembourg",
    "MT": "Malta", "NL": "Netherlands", "NO": "Norway", "PL": "Poland",
    "PT": "Portugal", "RO": "Romania", "SG": "Singapore", "SK": "Slovakia",
    "SI": "Slovenia", "ES": "Spain", "SE": "Sweden", "CH": "Switzerland",
    "GB": "United Kingdom", "US": "United States",
}


def offers_from_products(
    products: list[dict[str, Any]],
    *,
    language: str,
    condition: str = "NM",
    reverse: bool = False,
    first_edition: bool | None = None,
) -> list[dict[str, Any]]:
    """Listings of the wanted copy as the app's price rows, cheapest first.

    [language] is CardTrader's code. A copy counts in [condition] or better,
    as on Cardmarket. Graded, signed and altered copies and sellers on
    holiday are left out.
    """
    floor = _RANK.get(condition, _RANK["NM"])
    rows: list[dict[str, Any]] = []
    for product in products:
        props = product.get("properties_hash") or {}
        code = CONDITIONS.get(props.get("condition") or "")
        if code is None or _RANK[code] > floor:
            continue
        if props.get("pokemon_language") != language:
            continue
        if bool(props.get("pokemon_reverse")) != reverse:
            continue
        if first_edition is not None and bool(props.get("first_edition")) != first_edition:
            continue
        if product.get("graded") or product.get("on_vacation"):
            continue
        if props.get("signed") or props.get("altered"):
            continue
        if int(product.get("quantity") or 0) < 1:
            continue
        price = product.get("price") or {}
        cents = price.get("cents", product.get("price_cents"))
        currency = price.get("currency") or product.get("price_currency")
        if not isinstance(cents, int) or cents <= 0 or not currency:
            continue
        user = product.get("user") or {}
        parts = [
            code,
            LANGUAGE_NAMES.get(language, ""),
            COUNTRY_NAMES.get(str(user.get("country_code") or "").upper(), ""),
            "Professional" if user.get("user_type") == "pro" else "",
        ]
        rows.append({
            "label": " · ".join(part for part in parts if part),
            "amount": cents / 100,
            "currency": str(currency),
            "source": "cardtrader",
        })
    rows.sort(key=lambda row: row["amount"])
    return rows


class CardTrader:
    """The blueprint list and an hour's listings per card."""

    def __init__(
        self,
        token: str,
        path: Path,
        *,
        reuse_s: int = 3600,
        map_max_age_s: int = 7 * 86400,
        client: httpx.Client | None = None,
    ) -> None:
        self.reuse_s = reuse_s
        self.map_max_age_s = map_max_age_s
        self._client = client or httpx.Client(
            base_url=API,
            timeout=20,
            headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT},
        )
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS blueprints (
                cardmarket_id INTEGER NOT NULL,
                blueprint_id INTEGER NOT NULL,
                PRIMARY KEY (cardmarket_id, blueprint_id)
            );
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            """
        )
        self._listings: dict[tuple[int, str], tuple[float, list[dict[str, Any]]]] = {}
        self._importing = False

    def close(self) -> None:
        self._client.close()
        with self._lock:
            self._conn.close()

    # -- blueprint list ----------------------------------------------------

    def map_age_s(self) -> float | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key = 'imported_at'"
            ).fetchone()
        return None if row is None else time.time() - float(row[0])

    def refresh_map_if_stale(self) -> None:
        """Starts the import in the background; lookups meanwhile use the old list."""
        age = self.map_age_s()
        if age is not None and age < self.map_max_age_s:
            return
        with self._lock:
            if self._importing:
                return
            self._importing = True
        threading.Thread(target=self._import_guarded, name="cardtrader-map", daemon=True).start()

    def _import_guarded(self) -> None:
        try:
            count = self.import_map()
            log.info("cardtrader map imported pairs=%s", count)
        except Exception as exc:  # the old list stays in use
            log.warning("cardtrader map import failed error_type=%s", type(exc).__name__)
        finally:
            with self._lock:
                self._importing = False

    def import_map(self, *, pause_s: float = 0.15) -> int:
        """Every Pokémon blueprint's Cardmarket ids, replacing the stored list."""
        response = self._client.get("/expansions")
        response.raise_for_status()
        pairs: set[tuple[int, int]] = set()
        for expansion in response.json():
            if expansion.get("game_id") != POKEMON_GAME_ID:
                continue
            reply = self._client.get(
                "/blueprints/export", params={"expansion_id": expansion["id"]}
            )
            reply.raise_for_status()
            for blueprint in reply.json():
                for market_id in blueprint.get("card_market_ids") or []:
                    if isinstance(market_id, int):
                        pairs.add((market_id, int(blueprint["id"])))
            time.sleep(pause_s)
        if not pairs:
            raise ValueError("no blueprints")
        with self._lock:
            with self._conn:
                self._conn.execute("DELETE FROM blueprints")
                self._conn.executemany("INSERT INTO blueprints VALUES (?, ?)", pairs)
                self._conn.execute(
                    "INSERT OR REPLACE INTO meta VALUES ('imported_at', ?)",
                    (str(time.time()),),
                )
        return len(pairs)

    def blueprints(self, cardmarket_id: int) -> list[int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT blueprint_id FROM blueprints WHERE cardmarket_id = ? "
                "ORDER BY blueprint_id LIMIT ?",
                (cardmarket_id, MAX_BLUEPRINTS),
            ).fetchall()
        return [int(row[0]) for row in rows]

    # -- listings ----------------------------------------------------------

    def _products(self, blueprint_id: int, language: str) -> tuple[float, list[dict[str, Any]]]:
        key = (blueprint_id, language)
        kept = self._listings.get(key)
        if kept is not None and time.time() - kept[0] < self.reuse_s:
            return kept
        response = self._client.get(
            "/marketplace/products",
            params={"blueprint_id": blueprint_id, "language": language},
        )
        response.raise_for_status()
        body = response.json()
        products = body.get(str(blueprint_id), []) if isinstance(body, dict) else []
        fresh = (time.time(), products)
        self._listings[key] = fresh
        if len(self._listings) > 5000:
            cutoff = time.time() - self.reuse_s
            self._listings = {k: v for k, v in self._listings.items() if v[0] >= cutoff}
        return fresh

    def prices(
        self,
        cardmarket_id: int,
        catalogue_language: str,
        *,
        condition: str = "NM",
        reverse: bool = False,
        first_edition: bool | None = None,
    ) -> dict[str, Any]:
        """The app's payload: seller rows, how many matched, and when read."""
        self.refresh_map_if_stale()
        language = LANGUAGE_CODES.get(catalogue_language.lower())
        blueprints = self.blueprints(cardmarket_id) if language else []
        rows: list[dict[str, Any]] = []
        observed: float | None = None
        for blueprint_id in blueprints:
            at, products = self._products(blueprint_id, language)
            observed = at if observed is None else min(observed, at)
            rows.extend(
                offers_from_products(
                    products,
                    language=language,
                    condition=condition,
                    reverse=reverse,
                    first_edition=first_edition,
                )
            )
        rows.sort(key=lambda row: row["amount"])
        return {
            "enabled": True,
            "matched": bool(blueprints),
            "count": len(rows),
            "prices": rows[:MAX_ROWS],
            "observed_at": None
            if observed is None
            else datetime.fromtimestamp(observed, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }


def from_settings(settings) -> CardTrader | None:
    """None without a token: the app then shows no CardTrader box."""
    token = (settings.cardtrader_api_token or "").strip()
    if not token:
        return None
    return CardTrader(
        token,
        settings.data_dir / "cardtrader.sqlite",
        reuse_s=max(60, int(settings.cardtrader_reuse_minutes) * 60),
        map_max_age_s=max(3600, int(settings.cardtrader_map_max_age_h) * 3600),
    )
