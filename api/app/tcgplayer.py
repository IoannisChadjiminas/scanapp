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
from collections import Counter
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.market_match import pick, plain, plain_number, voted

log = logging.getLogger("tcgplayer")

SOURCE = "https://tcgcsv.com"
# A product's public page on TCGplayer.
PRODUCT_PAGE = "https://www.tcgplayer.com/product/{product_id}"
# TCGplayer's categories: Pokémon, and Pokémon Japan.
CATEGORIES = (3, 85)
JAPAN = 85
# Raised when the stored data gains something: an older store is imported again.
STORE_VERSION = "2"
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
    """Market, low and mid, whichever are known, in that order.

    Many Japanese cards have listings but no recent sales: those carry a low
    price and no market price, and the app says so.
    """
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
    return found if any(item["label"] in ("Market", "Low") for item in found) else []


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
            CREATE TABLE IF NOT EXISTS listed (
                category INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                set_code TEXT NOT NULL,
                number TEXT NOT NULL,
                name TEXT NOT NULL,
                product_id INTEGER PRIMARY KEY
            );
            CREATE INDEX IF NOT EXISTS listed_group ON listed (group_id, number);
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            -- A printing's price on the days it moved: the market price, or
            -- the lowest listing where nothing sold. For a chart.
            CREATE TABLE IF NOT EXISTS history (
                product_id INTEGER NOT NULL,
                printing TEXT NOT NULL,
                day TEXT NOT NULL,
                price REAL NOT NULL,
                PRIMARY KEY (product_id, printing, day)
            ) WITHOUT ROWID;
            """
        )
        self._importing = False
        # (catalogue language, set id) -> its groups here, until the next import.
        self.set_groups: dict[tuple[str, str], set[int]] = {}

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
        if (
            imported is not None
            and self._meta("version") == STORE_VERSION
            and time.time() - float(imported) < self.max_age_s
        ):
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
        # Every card of every set with its number and name: how a catalogue
        # card nothing else ties to a product is found (see find).
        cards: list[tuple[int, int, str, str, str, int]] = []
        for category in CATEGORIES:
            groups = self._client.get(f"/tcgplayer/{category}/groups")
            groups.raise_for_status()
            for group in groups.json().get("results") or []:
                listed = self._client.get(f"/tcgplayer/{category}/{group['groupId']}/products")
                listed.raise_for_status()
                for product in listed.json().get("results") or []:
                    number = plain_number(next(
                        (
                            extra.get("value")
                            for extra in product.get("extendedData") or []
                            if extra.get("name") == "Number"
                        ),
                        None,
                    ))
                    # Sealed products have no number.
                    if number:
                        cards.append((
                            category,
                            int(group["groupId"]),
                            plain(group.get("abbreviation")),
                            number,
                            plain(str(product.get("name") or "").split(" - ")[0].split(" (")[0]),
                            int(product["productId"]),
                        ))
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
                self._conn.execute("DELETE FROM listed")
                self._conn.executemany(
                    "INSERT OR REPLACE INTO listed VALUES (?, ?, ?, ?, ?, ?)", cards
                )
                self._conn.execute("DELETE FROM prices")
                self._conn.executemany("INSERT OR REPLACE INTO prices VALUES (?, ?, ?, ?, ?)", rows)
                self._conn.executemany(
                    "INSERT OR REPLACE INTO meta VALUES (?, ?)",
                    [
                        ("imported_at", str(time.time())),
                        ("priced_at", stamp.text.strip()),
                        ("version", STORE_VERSION),
                    ],
                )
        self.set_groups.clear()
        day = (_utc(stamp.text.strip()) or datetime.now(timezone.utc).strftime("%Y-%m-%d"))[:10]
        self.record_day(day, ((row[0], row[1], row[2], row[3]) for row in rows))
        return len(rows)

    def record_day(self, day: str, rows) -> int:
        """Keeps [day]'s prices, (product, printing, market, low) each, where
        they moved: a price within 2% (or two cents) of the last one kept
        before that day adds nothing a chart would show."""
        kept = 0
        with self._lock:
            with self._conn:
                for product_id, printing, market, low in rows:
                    price = market if isinstance(market, (int, float)) and market > 0 else low
                    if not isinstance(price, (int, float)) or price <= 0:
                        continue
                    last = self._conn.execute(
                        "SELECT price FROM history WHERE product_id = ? AND printing = ? AND day < ? "
                        "ORDER BY day DESC LIMIT 1",
                        (product_id, printing, day),
                    ).fetchone()
                    if last is not None and abs(price - last[0]) < max(0.02, 0.02 * last[0]):
                        continue
                    self._conn.execute(
                        "INSERT OR REPLACE INTO history VALUES (?, ?, ?, ?)",
                        (int(product_id), str(printing), day, round(float(price), 2)),
                    )
                    kept += 1
        return kept

    def history(
        self, product_id: int | None, *, reverse: bool = False, first_edition: bool | None = None
    ) -> list[tuple[str, float]]:
        """(day, dollars) for the copy's printing, oldest first: the days
        its price moved. Empty for a product or printing never priced."""
        if product_id is None:
            return []
        with self._lock:
            printings = [row[0] for row in self._conn.execute(
                "SELECT DISTINCT printing FROM history WHERE product_id = ?", (product_id,)
            )]
            chosen = pick_printing(
                {name: {"name": name} for name in printings},
                reverse=reverse, first_edition=first_edition,
            )
            if chosen is None:
                return []
            return [(str(day), float(price)) for day, price in self._conn.execute(
                "SELECT day, price FROM history WHERE product_id = ? AND printing = ? ORDER BY day",
                (product_id, chosen["name"]),
            )]

    def groups_for(self, product_ids: list[int], set_code: str, catalogue_language: str) -> set[int]:
        """TCGplayer's sets that hold a catalogue set's cards: the ones most of
        its known products ([product_ids]) are in, and any with its set code."""
        category = JAPAN if str(catalogue_language).lower() == "ja" else CATEGORIES[0]
        votes: Counter[int] = Counter()
        with self._lock:
            for start in range(0, len(product_ids), 500):
                part = product_ids[start:start + 500]
                for group_id, count in self._conn.execute(
                    f"SELECT group_id, COUNT(*) FROM listed WHERE category = ? "
                    f"AND product_id IN ({','.join('?' for _ in part)}) GROUP BY 1",
                    (category, *part),
                ):
                    votes[int(group_id)] += int(count)
            coded = self._conn.execute(
                "SELECT DISTINCT group_id FROM listed WHERE category = ? AND set_code = ?",
                (category, plain(set_code)),
            ).fetchall() if plain(set_code) else []
        return voted(votes) | {int(row[0]) for row in coded}

    def find(self, groups: set[int], collector_number: object, names: list[str]) -> int | None:
        """A card's product inside [groups], by collector number.

        Its name must agree with one of [names] where there are any; a card
        with no name to check is taken when the number has one product.
        Anything but exactly one product gives None. Where the right product
        was already known this picked the same one for 99.6% of Japanese
        cards (21 November 2026).
        """
        number = plain_number(collector_number)
        if not (groups and number):
            return None
        with self._lock:
            rows = self._conn.execute(
                f"SELECT name, product_id FROM listed "
                f"WHERE group_id IN ({','.join('?' for _ in groups)}) AND number = ?",
                (*groups, number),
            ).fetchall()
        chosen = pick(rows, names, lambda row: row[0])
        return None if chosen is None else int(chosen[1])

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
            # The product's page, for a product with prices (a matched one).
            "url": PRODUCT_PAGE.format(product_id=product_id) if found else None,
            "observed_at": _utc(self._meta("priced_at")) if found else None,
        }


def _utc(stamp: str | None) -> str | None:
    """TCGCSV's "2026-11-20T20:06:21+0000" as the app's UTC stamp."""
    try:
        at = datetime.strptime(stamp or "", "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None
    return at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
