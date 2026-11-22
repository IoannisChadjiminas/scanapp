"""Dollars to euros at the European Central Bank's daily reference rate.

eBay's graded prices are in dollars and a collection's total is in euros. The
rate is read once in twelve hours and kept in a small file, so a restart or
an outage at the bank still has yesterday's.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path

import httpx

log = logging.getLogger("fx")

SOURCE = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
REFRESH_S = 12 * 3600
_USD = re.compile(r"currency=['\"]USD['\"]\s+rate=['\"]([0-9.]+)['\"]")
_DAY = re.compile(r"time=['\"](\d{4}-\d{2}-\d{2})['\"]")


class EuroRate:
    """How many dollars one euro is, and what a dollar price is in euros."""

    def __init__(self, path: Path | None = None, *, client: httpx.Client | None = None) -> None:
        self._path = path
        self._client = client or httpx.Client(timeout=15, headers={"User-Agent": "scanapp-prices/1.0"})
        self._lock = threading.Lock()
        self._rate: float | None = None
        self._day: str | None = None
        self._asked = 0.0
        if path is not None and path.exists():
            try:
                saved = json.loads(path.read_text())
                self._rate, self._day = float(saved["usd_per_eur"]), str(saved.get("day") or "")
            except (OSError, ValueError, KeyError, TypeError):
                pass

    def close(self) -> None:
        self._client.close()

    def _refresh(self) -> None:
        with self._lock:
            if time.time() - self._asked < REFRESH_S:
                return
            self._asked = time.time()
        try:
            reply = self._client.get(SOURCE)
            reply.raise_for_status()
            found = _USD.search(reply.text)
            rate = float(found.group(1)) if found else 0.0
            if not 0.5 < rate < 2.5:
                raise ValueError("no plausible rate")
            day = _DAY.search(reply.text)
            with self._lock:
                self._rate, self._day = rate, day.group(1) if day else ""
            if self._path is not None:
                self._path.write_text(json.dumps({"usd_per_eur": rate, "day": self._day}))
        except (httpx.HTTPError, ValueError, OSError) as exc:
            # The last rate stays in use.
            log.warning("euro rate not read error_type=%s", type(exc).__name__)

    @property
    def day(self) -> str | None:
        return self._day or None

    def usd_to_eur(self, amount: float | None) -> float | None:
        """None without an amount, or before any rate was ever read."""
        if amount is None:
            return None
        self._refresh()
        return round(amount / self._rate, 2) if self._rate else None
