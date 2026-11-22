"""What graded copies of a card are offered for on eBay, from its Browse API.

Only graded copies, and only asking prices: eBay gives sold prices to approved
partners alone, so this is the average of the cheapest Buy It Now listings for
the card in the copy's grade. Auctions are left out: a current bid says
nothing until the auction ends. The server asks, never the phone; an answer is
reused for six hours.

eBay titles are free text, so a listing counts only when its title passes
every rule in `listing_is` (the card's name, number, year and language; the
exact grade; no other card, variant or grader). The rules were set against
real listings on 21 November 2026: a first version let through a reprint with
the same number (Celebrations "4/102"), raw cards titled "NOT PSA 10" and
"PSA 10 worthy", and Japanese copies of English cards.
"""
from __future__ import annotations

import base64
import logging
import re
import statistics
import threading
import time
from dataclasses import dataclass
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
# Graders the app does not offer still mark a listing as another slab.
_ALL_GRADERS = (*GRADERS, "SGC", "ACE", "PCA", "MNT", "GMA", "HGA", "CGA", "ARS", "BECKETT")
GRADE = re.compile(r"^(10|[1-9](\.5)?)$")
USER_AGENT = "scanapp-prices/1.0"

# Words sellers put between the grader and the number: "PSA GEM MT 10".
_FILLER = r"(?:\s*[:\[\]\(\)\-#]?\s*(?:gem|mint|mt|nm|nm-mt|grade|graded)\b)*"
# A cheaper listing than this share of the middle price is left out of the
# average: a mislisted card or a bait title that passed the other rules.
OUTLIER_SHARE = 0.5

# Not one real graded card of the usual kind.
_NOT_A_CARD = re.compile(
    r"\b(lots?|bundle|proxy|custom|reprint|replica|fake|digital|choose|pick|"
    r"read\s+desc\w*|empty|case\s+only|display|sealed|booster|box|pack|"
    r"signed|autograph\w*|auto|error|misprint|miscut|damaged|"
    r"big\s+three|trio|duo|pair|both|all\s+three|set\s+of|complete|"
    r"pristine|perfect|black\s+label)\b",
    re.IGNORECASE,
)
# A raw card dressed as a slab: "NOT PSA 10", "PSA 10 worthy", "PSA ready".
_BAIT = re.compile(
    r"\b(not|no|non|worthy|candidate|potential|possible|contender|ready|"
    r"regrade|crack|quality|like|ungraded|raw)\b|\?",
    re.IGNORECASE,
)
# Another printing of the same card, worth something else.
_VARIANT = re.compile(
    r"\b(pok[eé]\s*ball|master\s*ball|stamp(?:ed)?|staff|pre-?release|jumbo|"
    r"oversized|cosmos|costco|league|winner|promo|shadowless|metal|sequential|"
    r"exclusive|best\s+buy|gamestop|walmart|target|pok[eé]mon\s+cent(?:er|re))\b",
    re.IGNORECASE,
)
# A later reprint that keeps the old number.
_REPRINT = re.compile(
    r"\b(celebrations?|classic\s+collection|anniversary|25th|30th)\b", re.IGNORECASE
)
_JAPANESE = re.compile(r"\b(japanese|japan|jpn|jp)\b", re.IGNORECASE)
_OTHER_LANGUAGE = re.compile(
    r"\b(korean|kor|chinese|chn|thai|indonesian|german|french|italian|spanish|"
    r"portuguese|dutch|russian|ita|deu|ger|fra|fre|esp|spa|por)\b",
    re.IGNORECASE,
)
# Sets whose cards keep the number of the card they reprint.
REPRINT_SETS = {"30th-c", "cel25c"}
# Words of a set's name that do not tell sets apart.
_SET_NOISE = {"pokemon", "pokémon", "the", "and", "of", "set", "tcg", "card", "cards", "game"}
_YEAR = re.compile(r"(?<!\d)(19[89]\d|20[0-4]\d)(?!\d)")
_FRACTION = re.compile(r"(?<![\d.])(\d{1,3})\s*/\s*(\d{1,3})(?![\d.])")


@dataclass(frozen=True)
class GradedCard:
    """What a listing must be: the card, and the copy's grade."""

    name: str
    number: str
    grader: str
    grade: str
    total: int | None = None
    year: int | None = None
    japanese: bool = False
    reverse: bool = False
    first_edition: bool | None = None
    set_name: str = ""
    # The set's code ("sv2a"), which sellers of Japanese cards put in titles.
    set_code: str = ""
    # No other card in the set has this name: in a reprint set (REPRINT_SETS)
    # the set and the name are then the card, whatever number is printed.
    unique_name: bool = False

    @property
    def search(self) -> str:
        """What eBay is asked for, as sellers title their listings."""
        number = f"{self.number}/{self.total}" if self.total else self.number
        return " ".join(
            part for part in (
                self.name, number, "Japanese" if self.japanese else "", self.grader, self.grade
            ) if part
        )

    @property
    def set_words(self) -> list[str]:
        """The words that name the set, without ones every title has."""
        return [word for word in _words(self.set_name) if word not in _SET_NOISE]

    @property
    def set_search(self) -> str:
        """The second search, by set instead of number: slab labels read
        "2026 POKEMON 30TH CELEBRATION CLASSIC COLLECTION #4 CHARIZARD", with
        no "4/102" for the first search to find. Empty with no set to name."""
        named = " ".join(self.set_words) if self.set_name.isascii() else self.set_code
        if not named:
            return ""
        return " ".join(
            part for part in (
                self.name, named, "Japanese" if self.japanese else "", self.grader, self.grade
            ) if part
        )


def _words(text: str) -> list[str]:
    """"Misty's Psyduck" -> ["mistys", "psyduck"]."""
    plain = text.lower().replace("'", "").replace("’", "")
    return re.findall(r"[a-z0-9]+", plain)


def _plain_number(text: str) -> str:
    head = text.split("/")[0].strip().lower()
    return head.lstrip("0") or ("0" if head else "")


def names_grade(title: str, grader: str, grade: str) -> bool:
    """Whether a title says this grader and exact grade, and no other slab:
    "PSA 10", "PSA10", "PSA GEM MT 10", "[PSA: 9]"; never "PSA 10" for a
    wanted "PSA 1", "9.5" for "9", or a title that also names "BGS"."""
    wanted = rf"(?<![A-Za-z]){re.escape(grader)}{_FILLER}\s*[:\-\]]?\s*{re.escape(grade)}(?![\d+]|\.\d)"
    if re.search(wanted, title, re.IGNORECASE) is None:
        return False
    for other in _ALL_GRADERS:
        if other != grader and re.search(rf"(?<![A-Za-z]){other}(?![A-Za-z])", title, re.IGNORECASE):
            return False
    # The same grader with another number: "PSA 9 ... PSA 10".
    for found in re.finditer(
        rf"(?<![A-Za-z]){re.escape(grader)}{_FILLER}\s*[:\-\]]?\s*(10|\d(?:\.5)?)(?![\d+]|\.\d)",
        title,
        re.IGNORECASE,
    ):
        if found.group(1) != grade:
            return False
    return True


def _names_set(title: str, card: GradedCard) -> bool:
    """Whether a title names the card's set: every word of its name, or its
    code; and not a later set that only adds a number ("Base Set 2")."""
    present = _words(title)
    words = card.set_words
    by_name = bool(words) and all(word in present for word in words)
    by_code = bool(card.set_code) and card.set_code.lower() in present
    if not (by_name or by_code):
        return False
    if by_name and not by_code:
        last = words[-1]
        # "Base Set 2": past words like "set", which every title has.
        told = [word for word in present if word not in _SET_NOISE]
        for index, word in enumerate(told[:-1]):
            follows = told[index + 1]
            if word == last and follows in {"2", "ii"} and follows not in words:
                return False
    return True


def listing_is(title: str, card: GradedCard) -> bool:
    """Whether a listing's title is this card in this grade and nothing else."""
    if not names_grade(title, card.grader, card.grade):
        return False
    if _NOT_A_CARD.search(title) or _BAIT.search(title):
        return False
    # Every word of the card's name.
    present = set(_words(title))
    if not all(word in present for word in _words(card.name)):
        return False
    # Its number, and no other card's. "4/102" names the card by itself;
    # a title without one ("#4", as on a slab's label) must name the set too.
    wanted = _plain_number(card.number)
    fractions = _FRACTION.findall(title)
    if fractions:
        if any(_plain_number(number) != wanted for number, _ in fractions):
            return False
        if card.total:
            if not any(int(total) == card.total for _, total in fractions):
                return False
        elif not _names_set(title, card):
            return False
    else:
        if not _names_set(title, card):
            return False
        # A "#185" is the card's number, whatever else the title holds: the
        # 151 set's labels read "MEW EN-151", so "151" alone proves nothing.
        marked = [_plain_number(number) for number in re.findall(r"#\s*(\d+)", title)]
        numbered = all(number == wanted for number in marked) if marked else (
            wanted in {_plain_number(word) for word in present}
        )
        if not numbered:
            # A few reprint sets are numbered in the catalogue by their own
            # order, not by what is printed ("#4" for card 001 of 30). There
            # the set and a name no other card in it has are the card.
            if not (
                card.set_code in REPRINT_SETS and card.unique_name and len(marked) == 1
            ):
                return False
    # The language.
    if card.japanese != bool(_JAPANESE.search(title)) or _OTHER_LANGUAGE.search(title):
        return False
    # The printing.
    if card.reverse != bool(re.search(r"\breverse\b", title, re.IGNORECASE)):
        return False
    # A copy not marked first edition is an unlimited one: a "1st Edition"
    # listing is another, dearer card.
    first = bool(re.search(r"\b1st\b|\bfirst\s+ed", title, re.IGNORECASE))
    if bool(card.first_edition) != first:
        return False
    for rule in (_VARIANT, _REPRINT):
        found = rule.search(title)
        if found and found.group(0).lower() not in card.set_name.lower():
            # "shadowless" belongs to a first edition copy.
            if not (card.first_edition and found.group(0).lower() == "shadowless"):
                return False
    # The year, where the title gives one: a reprint is years later.
    if card.year is not None:
        years = [int(year) for year in _YEAR.findall(title)]
        if any(abs(year - card.year) > 1 for year in years):
            return False
    return True


def graded_listings(
    items: list[dict[str, Any]], card: GradedCard, *, currency: str
) -> list[dict[str, Any]]:
    """Buy It Now listings of the card in its grade, cheapest first."""
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
        if not listing_is(title, card):
            continue
        found.append({
            "title": title[:120],
            "amount": round(amount, 2),
            "currency": currency,
            "country": str((item.get("itemLocation") or {}).get("country") or ""),
            "url": str(item.get("itemWebUrl") or ""),
        })
    found.sort(key=lambda listing: listing["amount"])
    if len(found) >= 5:
        floor = OUTLIER_SHARE * statistics.median(item["amount"] for item in found)
        found = [item for item in found if item["amount"] >= floor]
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
        self._kept: dict[GradedCard, tuple[float, dict[str, Any]]] = {}

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

    def search(self, card: GradedCard) -> list[dict[str, Any]]:
        """eBay's Buy It Now single-card listings for the card, from both
        searches (by number, and by set), each cheapest first."""
        found: dict[str, dict[str, Any]] = {}
        for query in dict.fromkeys(q for q in (card.search, card.set_search) if q):
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
                    "limit": 200,
                },
            )
            reply.raise_for_status()
            for item in reply.json().get("itemSummaries") or []:
                # One listing found by both searches counts once.
                key = str(item.get("itemId") or item.get("itemWebUrl") or item.get("title"))
                found.setdefault(key, item)
        return list(found.values())

    def graded(self, card: GradedCard) -> dict[str, Any]:
        """The app's payload: the average of the cheapest listings, how many
        matched, the listings averaged, and when eBay was asked."""
        kept = self._kept.get(card)
        if kept is not None and time.time() - kept[0] < self.reuse_s:
            return kept[1]
        listings = graded_listings(self.search(card), card, currency=self.currency)
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
        self._kept[card] = (time.time(), answer)
        if len(self._kept) > 5000:
            cutoff = time.time() - self.reuse_s
            self._kept = {k: v for k, v in self._kept.items() if v[0] >= cutoff}
        return answer


def name_from_listing(cardmarket_url: object) -> str:
    """A card's English name from its Cardmarket address, for a card whose own
    name is not in Latin letters: ".../Mew-ex-V1-sv2a205" -> "Mew ex"."""
    tail = str(cardmarket_url or "").split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    words: list[str] = []
    for word in tail.split("-"):
        # The name ends where the version or the set code starts.
        if words and (re.fullmatch(r"[Vv]\d+", word) or any(ch.isdigit() for ch in word)):
            break
        if word:
            words.append(word)
    return " ".join(words)


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
