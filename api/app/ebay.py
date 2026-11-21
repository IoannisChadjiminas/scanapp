"""What graded copies of a card are offered for on eBay, from its Browse API.

Only graded copies, and only asking prices: eBay gives sold prices to approved
partners alone, so this is the average of the cheapest Buy It Now listings
whose title names the grade ("PSA 10"). Auctions are left out: a current bid
says nothing until the auction ends. The server asks, never the phone; an
answer is reused for six hours.
"""
from __future__ import annotations

import base64
import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx

log = logging.getLogger("ebay")

HOSTS = {
    "production": "https://api.ebay.com",
    "sandbox": "https://api.sandbox.ebay.com",
}
SCOPE = "https://api.ebay.com/oauth/api_scope"
# eBay's category for single trading cards: no boxes, packs or lots.
SINGLE_CARDS = "183454"
GRADERS = ("PSA", "BGS", "CGC", "TAG", "AGS")
GRADE = re.compile(r"^(10|[1-9](\.5)?)$")
USER_AGENT = "scanapp-prices/1.0"

# Titles that are not one real card.
_NOT_A_CARD = re.compile(
    r"\b(lot|lots|bundle|proxy|custom|reprint|replica|fake|digital|"
    r"choose|pick|read\s+description|empty|case\s+only|display)\b",
    re.IGNORECASE,
)


def names_grade(title: str, grader: str, grade: str) -> bool:
    """Whether a listing's title says this grader and grade: "PSA 10", "PSA10",
    "PSA-10", and never "PSA 10" for a wanted "PSA 1" or "9.5" for "9"."""
    pattern = rf"(?<![A-Za-z]){re.escape(grader)}\s*-?\s*{re.escape(grade)}(?![\d.]\d|\d)"
    return re.search(pattern, title, re.IGNORECASE) is not None


def graded_listings(
    items: list[dict[str, Any]], *, grader: str, grade: str, currency: str
) -> list[dict[str, Any]]:
    """Buy It Now listings of one card in this grade, cheapest first."""
    found = []
    for item in items:
        title = str(item.get("title") or "")
        price = item.get("price") or {}
        try:
            amount = float(price.get("value"))
        except (TypeError, ValueError):
            continue
        if amount <= 0 or price.get("currency") != currency:
            continue
        if "FIXED_PRICE" not in (item.get("buyingOptions") or []):
            continue
        if not names_grade(title, grader, grade) or _NOT_A_CARD.search(title):
            continue
        found.append({
            "title": title[:120],
            "amount": round(amount, 2),
            "currency": currency,
            "country": str((item.get("itemLocation") or {}).get("country") or ""),
            "url": str(item.get("itemWebUrl") or ""),
        })
    found.sort(key=lambda listing: listing["amount"])
    return found


class Ebay:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        environment: str = "production",
        marketplace: str = "EBAY_US",
        currency: str = "USD",
        reuse_s: int = 6 * 3600,
        take: int = 5,
        least: int = 3,
        client: httpx.Client | None = None,
    ) -> None:
        self._basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        self.marketplace = marketplace
        self.currency = currency
        self.reuse_s = reuse_s
        self.take = take
        self.least = least
        self._client = client or httpx.Client(
            base_url=HOSTS.get(environment, HOSTS["production"]),
            timeout=20,
            headers={"User-Agent": USER_AGENT},
        )
        self._lock = threading.Lock()
        self._token: tuple[float, str] | None = None
        self._kept: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}

    def close(self) -> None:
        self._client.close()

    def _bearer(self) -> str:
        with self._lock:
            if self._token is not None and time.time() < self._token[0]:
                return self._token[1]
        reply = self._client.post(
            "/identity/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {self._basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials", "scope": SCOPE},
        )
        reply.raise_for_status()
        body = reply.json()
        token = str(body["access_token"])
        with self._lock:
            # Renewed a minute early.
            self._token = (time.time() + max(60, int(body.get("expires_in", 7200)) - 60), token)
        return token

    def graded(self, query: str, grader: str, grade: str) -> dict[str, Any]:
        """The app's payload: the average of the cheapest listings, how many
        matched, the listings averaged, and when eBay was asked."""
        key = (" ".join(query.lower().split()), grader, grade)
        kept = self._kept.get(key)
        if kept is not None and time.time() - kept[0] < self.reuse_s:
            return kept[1]
        reply = self._client.get(
            "/buy/browse/v1/item_summary/search",
            headers={
                "Authorization": f"Bearer {self._bearer()}",
                "X-EBAY-C-MARKETPLACE-ID": self.marketplace,
            },
            params={
                "q": query,
                "category_ids": SINGLE_CARDS,
                "filter": "buyingOptions:{FIXED_PRICE}",
                "sort": "price",
                "limit": 50,
            },
        )
        reply.raise_for_status()
        listings = graded_listings(
            reply.json().get("itemSummaries") or [],
            grader=grader,
            grade=grade,
            currency=self.currency,
        )
        cheapest = listings[: self.take]
        enough = len(listings) >= self.least
        answer = {
            "enabled": True,
            "average": round(sum(item["amount"] for item in cheapest) / len(cheapest), 2)
            if enough
            else None,
            "currency": self.currency,
            "count": len(listings),
            "listings": cheapest if enough else [],
            "observed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self._kept[key] = (time.time(), answer)
        if len(self._kept) > 5000:
            cutoff = time.time() - self.reuse_s
            self._kept = {k: v for k, v in self._kept.items() if v[0] >= cutoff}
        return answer


def from_settings(settings) -> Ebay | None:
    """None without keys: the app then shows no eBay row."""
    client_id = (settings.ebay_client_id or "").strip()
    secret = (settings.ebay_client_secret or "").strip()
    if not (client_id and secret):
        return None
    return Ebay(
        client_id,
        secret,
        environment=settings.ebay_environment,
        marketplace=settings.ebay_marketplace,
        currency=settings.ebay_currency,
        reuse_s=max(300, int(settings.ebay_reuse_minutes) * 60),
    )
