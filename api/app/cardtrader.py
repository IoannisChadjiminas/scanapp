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
from collections import Counter
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.market_match import close_names, pick, plain, plain_number, voted

log = logging.getLogger("cardtrader")

API = "https://api.cardtrader.com/api/v2"
POKEMON_GAME_ID = 5
MAX_ROWS = 20
MAX_BLUEPRINTS = 3
USER_AGENT = "scanapp-cardtrader/1.0"
# Raised when the stored list gains something: an older list is imported again.
MAP_VERSION = "5"
# First edition copies of these expansions are kept in another one, as its
# own cards with their own Cardmarket and TCGplayer products: "Base Set"
# (1472) first editions are in "Base Set Shadowless" (1969).
FIRST_EDITION_EXPANSIONS = {1472: 1969}

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
            CREATE TABLE IF NOT EXISTS tcgplayer_ids (
                cardmarket_id INTEGER PRIMARY KEY,
                product_id INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS listed (
                expansion_id INTEGER NOT NULL,
                expansion TEXT NOT NULL,
                code TEXT NOT NULL,
                number TEXT NOT NULL,
                name TEXT NOT NULL,
                languages TEXT NOT NULL,
                blueprint_id INTEGER PRIMARY KEY,
                tcgplayer_id INTEGER
            );
            CREATE INDEX IF NOT EXISTS listed_expansion ON listed (expansion_id, number);
            CREATE TABLE IF NOT EXISTS first_editions (
                cardmarket_id INTEGER PRIMARY KEY,
                first_edition_id INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            """
        )
        self._listings: dict[tuple[int, str], tuple[float, list[dict[str, Any]]]] = {}
        self._importing = False
        # (catalogue language, set id) -> its expansions here, until the next import.
        self.set_expansions: dict[tuple[str, str], set[int]] = {}

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
            # A list from before TCGplayer ids were kept is imported again.
            version = self._conn.execute(
                "SELECT value FROM meta WHERE key = 'version'"
            ).fetchone()
        if row is None or version is None or version[0] != MAP_VERSION:
            return None
        return time.time() - float(row[0])

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
        tcgplayer: dict[int, int] = {}
        # (expansion, card name, collector number) -> its Cardmarket ids.
        named: dict[tuple[int, str, str], list[int]] = {}
        paired = set(FIRST_EDITION_EXPANSIONS) | set(FIRST_EDITION_EXPANSIONS.values())
        # Every card with its set, number and name, for cards listed here
        # without a Cardmarket id (many Japanese sets).
        listed: list[tuple[int, str, str, str, str, str, int, int | None]] = []
        for expansion in response.json():
            if expansion.get("game_id") != POKEMON_GAME_ID:
                continue
            reply = self._client.get(
                "/blueprints/export", params={"expansion_id": expansion["id"]}
            )
            reply.raise_for_status()
            for blueprint in reply.json():
                languages = next(
                    (
                        prop.get("possible_values") or []
                        for prop in blueprint.get("editable_properties") or []
                        if prop.get("name") == "pokemon_language"
                    ),
                    [],
                )
                tcg_id = blueprint.get("tcg_player_id")
                listed.append((
                    int(expansion["id"]),
                    plain(expansion.get("name")),
                    plain(expansion.get("code")),
                    plain_number((blueprint.get("fixed_properties") or {}).get("collector_number")),
                    plain(blueprint.get("name")),
                    "," + ",".join(str(code) for code in languages) + ",",
                    int(blueprint["id"]),
                    tcg_id if isinstance(tcg_id, int) else None,
                ))
                if expansion["id"] in paired:
                    number = (blueprint.get("fixed_properties") or {}).get("collector_number")
                    if number:
                        named[(expansion["id"], str(blueprint.get("name")), str(number))] = [
                            market_id
                            for market_id in blueprint.get("card_market_ids") or []
                            if isinstance(market_id, int)
                        ]
                for market_id in blueprint.get("card_market_ids") or []:
                    if isinstance(market_id, int):
                        pairs.add((market_id, int(blueprint["id"])))
                        if isinstance(blueprint.get("tcg_player_id"), int):
                            tcgplayer.setdefault(market_id, blueprint["tcg_player_id"])
            time.sleep(pause_s)
        if not pairs:
            raise ValueError("no blueprints")
        with self._lock:
            with self._conn:
                self._conn.execute("DELETE FROM blueprints")
                self._conn.executemany("INSERT INTO blueprints VALUES (?, ?)", pairs)
                self._conn.execute("DELETE FROM listed")
                self._conn.executemany(
                    "INSERT OR REPLACE INTO listed VALUES (?, ?, ?, ?, ?, ?, ?, ?)", listed
                )
                self._conn.execute("DELETE FROM first_editions")
                self._conn.executemany(
                    "INSERT OR REPLACE INTO first_editions VALUES (?, ?)",
                    [
                        (market_id, first[0])
                        for (expansion_id, name, number), ids in named.items()
                        if expansion_id in FIRST_EDITION_EXPANSIONS
                        and (first := named.get(
                            (FIRST_EDITION_EXPANSIONS[expansion_id], name, number)
                        ))
                        for market_id in ids
                    ],
                )
                self._conn.execute("DELETE FROM tcgplayer_ids")
                self._conn.executemany(
                    "INSERT INTO tcgplayer_ids VALUES (?, ?)", tcgplayer.items()
                )
                self._conn.executemany(
                    "INSERT OR REPLACE INTO meta VALUES (?, ?)",
                    [("imported_at", str(time.time())), ("version", MAP_VERSION)],
                )
        self.set_expansions.clear()
        return len(pairs)

    def blueprints(self, cardmarket_id: int) -> list[int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT blueprint_id FROM blueprints WHERE cardmarket_id = ? "
                "ORDER BY blueprint_id LIMIT ?",
                (cardmarket_id, MAX_BLUEPRINTS),
            ).fetchall()
        return [int(row[0]) for row in rows]

    def expansions_for(
        self, cardmarket_ids: list[int], names: set[str], code: str, catalogue_language: str
    ) -> set[int]:
        """The expansions here that hold a catalogue set's cards.

        [cardmarket_ids] are the set's cards: the expansions most of those
        that match are filed under count first. [names] are the plain names
        the set may go by and [code] its plain code; a name spelt almost the
        same counts too. Only expansions with cards in the set's language.
        """
        language = LANGUAGE_CODES.get(str(catalogue_language or "").lower())
        if not language:
            return set()
        self.refresh_map_if_stale()
        votes: Counter[int] = Counter()
        with self._lock:
            for start in range(0, len(cardmarket_ids), 500):
                part = cardmarket_ids[start:start + 500]
                for expansion_id, count in self._conn.execute(
                    f"SELECT l.expansion_id, COUNT(*) FROM blueprints b "
                    f"JOIN listed l ON l.blueprint_id = b.blueprint_id "
                    f"WHERE b.cardmarket_id IN ({','.join('?' for _ in part)}) GROUP BY 1",
                    part,
                ):
                    votes[int(expansion_id)] += int(count)
            # Expansions with a card in the language, or that say no language.
            known = self._conn.execute(
                "SELECT DISTINCT expansion_id, expansion, code FROM listed "
                "WHERE languages LIKE ? OR languages = ',,'",
                (f"%,{language},%",),
            ).fetchall()
        by_name: dict[str, set[int]] = {}
        found = voted(votes)
        for expansion_id, name, expansion_code in known:
            by_name.setdefault(name, set()).add(int(expansion_id))
            if code and expansion_code == code:
                found.add(int(expansion_id))
        for name in names | close_names(names, list(by_name)):
            found |= by_name.get(name, set())
        return found

    def find(
        self,
        expansions: set[int],
        collector_number: object,
        names: list[str],
        catalogue_language: str,
    ) -> tuple[int, int | None] | None:
        """A card inside [expansions]: (blueprint, TCGplayer product or None).

        By collector number where the name agrees; else, for a card listed
        here without a usable number, by its name alone. The card must exist
        in the catalogue card's language, and [names] must not be empty: a
        number alone is not enough here, where stamped and jumbo copies share
        it. Anything but exactly one card gives None.
        """
        language = LANGUAGE_CODES.get(str(catalogue_language or "").lower())
        if not (language and expansions and names):
            return None
        marks = ",".join("?" for _ in expansions)
        with self._lock:
            every = self._conn.execute(
                f"SELECT name, number, blueprint_id, tcgplayer_id, languages FROM listed "
                f"WHERE expansion_id IN ({marks})",
                tuple(expansions),
            ).fetchall()

        def speaks(row) -> bool:
            return row[4] == ",," or f",{language}," in row[4]

        number = plain_number(collector_number)
        chosen = pick(
            [row for row in every if number and row[1] == number and speaks(row)],
            names,
            lambda row: row[0],
        )
        if chosen is None:
            # By name among every card of the set, whatever its language, so
            # "Paras" is never taken for a "Parasect" listed in another one.
            # A very short name ("N") would agree with too much.
            chosen = pick([row for row in every if len(row[0]) >= 4], names, lambda row: row[0])
            if chosen is not None and not speaks(chosen):
                chosen = None
        return None if chosen is None else (int(chosen[2]), chosen[3])

    def tcgplayer_products(self, cardmarket_ids: list[int]) -> list[int]:
        """The TCGplayer products of a set's cards, where CardTrader knows them."""
        found: list[int] = []
        with self._lock:
            for start in range(0, len(cardmarket_ids), 500):
                part = cardmarket_ids[start:start + 500]
                found += [
                    int(row[0])
                    for row in self._conn.execute(
                        f"SELECT product_id FROM tcgplayer_ids "
                        f"WHERE cardmarket_id IN ({','.join('?' for _ in part)})",
                        part,
                    )
                ]
        return found

    def first_edition_product(self, cardmarket_id: int) -> int | None:
        """The Cardmarket product that holds this card's first edition copies,
        where the marketplaces keep them apart; None where they do not."""
        self.refresh_map_if_stale()
        with self._lock:
            row = self._conn.execute(
                "SELECT first_edition_id FROM first_editions WHERE cardmarket_id = ?",
                (cardmarket_id,),
            ).fetchone()
        return None if row is None else int(row[0])

    def tcgplayer_id(self, cardmarket_id: int) -> int | None:
        """TCGplayer's product for a Cardmarket one, where CardTrader knows it."""
        self.refresh_map_if_stale()
        with self._lock:
            row = self._conn.execute(
                "SELECT product_id FROM tcgplayer_ids WHERE cardmarket_id = ?",
                (cardmarket_id,),
            ).fetchone()
        return None if row is None else int(row[0])

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
        fallback: int | None = None,
    ) -> dict[str, Any]:
        """The app's payload: seller rows, how many matched, and when read.

        [fallback] is the blueprint found by set, number and name (see find),
        used when the Cardmarket id finds none.
        """
        self.refresh_map_if_stale()
        language = LANGUAGE_CODES.get(catalogue_language.lower())
        blueprints = self.blueprints(cardmarket_id) if language else []
        if language and not blueprints and fallback is not None:
            blueprints = [fallback]
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
