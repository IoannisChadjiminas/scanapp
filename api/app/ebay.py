"""What graded copies of a card are offered for on eBay, from its Browse API.

Only graded copies, and only asking prices: eBay gives sold prices to approved
partners alone, so this is the average of the cheapest Buy It Now listings for
the card in the copy's grade. Auctions are left out: a current bid says
nothing until the auction ends. The server asks, never the phone; an answer is
reused for a day, by everyone: the first
collector to ask about a card pays for the lookup, the rest read it from here.

eBay titles are free text, so a listing counts only when its title passes
every rule in `listing_is` (the card's name, number, year and language; the
exact grade; no other card, variant or grader). The rules were set against
real listings on 21 November 2026: a first version let through a reprint with
the same number (Celebrations "4/102"), raw cards titled "NOT PSA 10" and
"PSA 10 worthy", and Japanese copies of English cards.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import sqlite3
import statistics
import threading
import time
import dataclasses
from dataclasses import dataclass, fields
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
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
# eBay's own name for each grader, as its "Professional Grader" field and
# filter spell it (read from eBay on 22 November 2026).
GRADER_NAMES = {
    "PSA": "Professional Sports Authenticator (PSA)",
    "BGS": "Beckett Grading Services (BGS)",
    "CGC": "Certified Guaranty Company (CGC)",
    "TAG": "Technical Authentication & Grading (TAG)",
    "AGS": "Automated Grading Systems (AGS)",
}
# eBay's condition for a card in a grader's slab.
GRADED_CONDITION = "2750"
# How many of the cheapest listings are opened to confirm the average.
CHECKS = 12
# How long an answer is kept at all. A day old it is asked again when someone
# looks; a collection's value may use it for longer than see no value.
KEEP_S = 45 * 86400
# A slab stays on the daily round this long after a collection last asked.
OWNED_S = 30 * 86400
HISTORY_DAYS = 400
# Graders the app does not offer still mark a listing as another slab.
_ALL_GRADERS = (*GRADERS, "SGC", "ACE", "PCA", "MNT", "GMA", "HGA", "CGA", "ARS", "BECKETT")
# CGC's grade above its Gem Mint 10, on the label as "Pristine 10" (and, on
# older slabs, "Perfect 10"): the same number, a dearer card.
PRISTINE = "P10"
PRISTINE_GRADERS = ("CGC",)
GRADE = re.compile(r"^(10|[1-9](\.5)?|P10)$")
_PRISTINE = re.compile(r"\b(pristine|perfect)\b", re.IGNORECASE)
USER_AGENT = "scanapp-prices/1.0"

# Words sellers put between the grader and the number: "PSA GEM MT 10".
_FILLER = r"(?:\s*[:\[\]\(\)\-#]?\s*(?:gem|mint|mt|nm|nm-mt|grade|graded|pristine|perfect)\b)*"
# A cheaper listing than this share of the middle price is left out of the
# average: a mislisted card or a bait title that passed the other rules.
OUTLIER_SHARE = 0.5

# Not one real graded card of the usual kind.
_NOT_A_CARD = re.compile(
    r"\b(lots?|bundle|proxy|custom|reprint|replica|fake|digital|choose|pick|"
    r"read\s+desc\w*|empty|case\s+only|display|sealed|booster|box|pack|"
    r"signed|autograph\w*|auto|error|misprint|miscut|damaged|"
    r"big\s+three|trio|duo|pair|both|all\s+three|set\s+of|complete|"
    # Merchandise filed among single cards: a "LARGE BLANKET 50x60".
    r"blanket|poster|playmat|play\s+mat|sleeves?|binder|plush|keychain|magnet|"
    r"stickers?|canvas|towel|shirt|mug|coin|pin|art\s+print|read|"
    r"pristine|perfect|black\s+label|bl)\b",
    re.IGNORECASE,
)
# A raw card dressed as a slab: "NOT PSA 10", "PSA 10 worthy", "PSA ready".
_BAIT = re.compile(
    r"\b(not|no|non|worthy|candidat\w*|potential|possible|contend\w*|ready|"
    r"strong|equivalent|"
    r"regrade|crack|quality|like|likely|maybe|ungraded|raw)\b|"
    r"\bor\s+(?:lower|better|higher)\b|\?",
    re.IGNORECASE,
)
# A reverse pattern a copy can be: the words sellers title it with, and what
# eBay is asked for. The other patterns Cardmarket lists (Energy, Team
# Rocket) and the stamped promos have no settled wording in titles, so a
# copy of one is not priced from eBay at all.
PATTERNS: dict[str, tuple[str, re.Pattern[str]]] = {
    key: (label, re.compile(words, re.IGNORECASE))
    for key, label, words in (
        ("pokeball", "Poke Ball", r"\bpok[eé]\s*-?\s*ball\b"),
        ("masterball", "Master Ball", r"\bmaster\s*-?\s*ball\b"),
        ("loveball", "Love Ball", r"\blove\s*-?\s*ball\b"),
        ("duskball", "Dusk Ball", r"\bdusk\s*-?\s*ball\b"),
        ("quickball", "Quick Ball", r"\bquick\s*-?\s*ball\b"),
        ("friendball", "Friend Ball", r"\bfriend\s*-?\s*ball\b"),
    )
}
# Another printing of the same card, worth something else.
_VARIANT = re.compile(
    r"\b(pok[eé]\s*ball|master\s*ball|love\s*ball|dusk\s*ball|quick\s*ball|"
    r"friend\s*ball|stamp(?:ed)?|staff|pre-?release|jumbo|"
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
# Each with the anniversary words its own listings carry: "30th" marks
# another set on a Celebrations (25th) title, and the other way round.
_ANNIVERSARY = {"celebration", "celebrations", "classic collection", "anniversary"}
REPRINT_SETS = {
    "30th-c": _ANNIVERSARY | {"30th"},
    "cel25c": _ANNIVERSARY | {"25th"},
    "cel25cc": _ANNIVERSARY | {"25th"},
}
# Words of a set's name that do not tell sets apart.
_SET_NOISE = {"pokemon", "pokémon", "the", "and", "of", "set", "tcg", "card", "cards", "game"}
# A two-letter language code in capitals: "PSA 10 DE White Flames". Lower
# case would catch ordinary words.
_LANGUAGE_CODE = re.compile(r"(?<![A-Za-z0-9])(DE|FR|ES|PT|KR|KO|CN|ZH)(?![A-Za-z0-9])")
# A reverse holo, as English and Japanese listings say it.
_REVERSE = re.compile(r"\b(reverse|rev\.?\s*(?:foil|holo)|mirror|parallel)\b", re.IGNORECASE)
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
    # The copy is this reverse pattern of the card (a key of PATTERNS): a
    # product of its own, priced apart from the card's plain and reverse copies.
    pattern: str = ""

    def __repr__(self) -> str:
        """The key answers and price history are kept under. A copy without a
        pattern reads exactly as it did before patterns, so what is held for
        it still stands."""
        parts = [
            f"{field.name}={getattr(self, field.name)!r}"
            for field in fields(self) if field.name != "pattern"
        ]
        if self.pattern:
            parts.append(f"pattern={self.pattern!r}")
        return f"GradedCard({', '.join(parts)})"

    @property
    def pristine(self) -> bool:
        return self.grade == PRISTINE

    @property
    def grade_number(self) -> str:
        """The number on the slab: "10" for a Pristine 10 too."""
        return "10" if self.pristine else self.grade

    @property
    def grade_words(self) -> str:
        """The grade as eBay is asked for it."""
        return "Pristine 10" if self.pristine else self.grade

    @property
    def pattern_label(self) -> str:
        """"Master Ball", as eBay is asked for it; empty for other copies."""
        return PATTERNS[self.pattern][0] if self.pattern in PATTERNS else ""

    @property
    def titled(self) -> str:
        """The card's name with its pattern, as a search names the copy."""
        return f"{self.name} {self.pattern_label}".strip()

    @property
    def lettered(self) -> bool:
        """A number with letters ("XY28", "SM167", "TG16") is a promo's or a
        subset's code: with the card's name it is the card, and it is never
        written over the set's total."""
        return any(ch.isalpha() for ch in self.number)

    @property
    def promo(self) -> bool:
        """A promo series: "XY Black Star Promos", or a Japanese one, whose
        code ends in "-P" ("SV-P", "M-P"). Its cards are numbered without a
        total, over several years, and often carry an event's stamp."""
        return (
            "promo" in self.set_words
            or "プロモ" in self.set_name
            or self.set_code.endswith("-p")
        )

    @property
    def number_label(self) -> str:
        """The number as sellers write it: "4/102", or "XY28" or a promo's
        "132" alone."""
        if self.total and not self.lettered and not self.promo:
            return f"{self.number}/{self.total}"
        return self.number

    @property
    def search(self) -> str:
        """What eBay is asked for, as sellers title their listings."""
        return " ".join(
            part for part in (
                self.titled, self.number_label, "Japanese" if self.japanese else "",
                self.grader, self.grade_words,
            ) if part
        )

    @property
    def set_words(self) -> list[str]:
        """The words that name the set, each in the singular, without ones
        every title has. A promo set is its series and "promo": sellers
        seldom write "Black Star"."""
        words = [_one(word) for word in _words(self.set_name) if word not in _SET_NOISE]
        if "promo" in words:
            words = [word for word in words if word not in {"black", "star"}]
        return words

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
                self.titled, named, "Japanese" if self.japanese else "", self.grader,
                self.grade_words,
            ) if part
        )


def _one(word: str) -> str:
    """"promos" and "promo", "celebrations" and "celebration" are one word."""
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def _words(text: str) -> list[str]:
    """"Misty's Psyduck" -> ["mistys", "psyduck"]."""
    plain = text.lower().replace("'", "").replace("’", "")
    return re.findall(r"[a-z0-9]+", plain)


def _plain_number(text: str) -> str:
    head = text.split("/")[0].strip().lower()
    return head.lstrip("0") or ("0" if head else "")


def other_slab(title: str, grader: str, grade: str) -> bool:
    """Whether a title names another grader, or this grader with another
    number: "PSA 9 ... BGS", "PSA 9 ... PSA 10" for a wanted PSA 10."""
    for other in _ALL_GRADERS:
        if other != grader and re.search(rf"(?<![A-Za-z]){other}(?![A-Za-z])", title, re.IGNORECASE):
            return True
    for found in re.finditer(
        rf"(?<![A-Za-z]){re.escape(grader)}{_FILLER}\s*[:\-\]]?\s*(\d{{1,2}}(?:\.5)?\+?)(?![\d]|\.\d)",
        title,
        re.IGNORECASE,
    ):
        # Any other number, a made-up one included ("PSA 20", "PSA 9+").
        if found.group(1) != grade:
            return True
    return False


def names_grade(title: str, grader: str, grade: str) -> bool:
    """Whether a title says this grader and exact grade, and no other slab:
    "PSA 10", "PSA10", "PSA GEM MT 10", "[PSA: 9]"; never "PSA 10" for a
    wanted "PSA 1", "9.5" for "9", or a title that also names "BGS"."""
    wanted = rf"(?<![A-Za-z]){re.escape(grader)}{_FILLER}\s*[:\-\]]?\s*{re.escape(grade)}(?![\d+]|\.\d)"
    if re.search(wanted, title, re.IGNORECASE) is None:
        return False
    return not other_slab(title, grader, grade)


def _names_set(title: str, card: GradedCard) -> bool:
    """Whether a title names the card's set: every word of its name, or its
    code; and not a later set that only adds a number ("Base Set 2")."""
    present = [_one(word) for word in _words(title)]
    words = card.set_words
    by_name = bool(words) and all(word in present for word in words)
    # "sv2a" as a word; "sv-p" also as "SV-P", "SVP" or "SV P".
    code = card.set_code.lower()
    by_code = bool(code) and (
        code in present
        or (
            "-" in code
            and re.search(
                r"(?<![a-z0-9])" + r"[-\s]?".join(map(re.escape, code.split("-"))) + r"(?![a-z0-9])",
                title.lower(),
            )
            is not None
        )
    )
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


def listing_is(title: str, card: GradedCard, *, graded: bool = False) -> bool:
    """Whether a listing's title is this card in this grade and nothing else.

    [graded]: eBay's own grader and grade fields already say so (the listing
    came through that filter). Such a title need not repeat the grade, since
    many are eBay's catalogue titles ("Charizard ex 199/165 ... Holo"); it
    still must not name another slab.
    """
    if graded:
        if other_slab(title, card.grader, card.grade_number):
            return False
    elif not names_grade(title, card.grader, card.grade_number):
        return False
    # A Pristine 10 says so; eBay's own grade field reads "10" for both, so
    # the title is what tells them apart.
    # A word that rules a listing out does not when it is part of the card's
    # or the set's own name (the set "Perfect Order", a card named "Pick").
    # It may appear as often as the name holds it and no more: "Perfect
    # Order ... CGC 10 PERFECT" is still the dearer slab.
    own = f"{card.name} {card.set_name}".lower()
    # A Pristine 10 says so, beyond what the card's own name says; eBay's
    # own grade field reads "10" for both, so the title is what tells them
    # apart.
    if card.pristine:
        said = [found.group(0).lower() for found in _PRISTINE.finditer(title)]
        if not any(said.count(word) > own.count(word) for word in set(said)):
            return False
    for rule in (_NOT_A_CARD, _BAIT):
        seen: dict[str, int] = {}
        for found in rule.finditer(title):
            word = found.group(0).lower()
            if card.pristine and _PRISTINE.fullmatch(word):
                continue
            seen[word] = seen.get(word, 0) + 1
            if seen[word] > own.count(word):
                return False
    # Every word of the card's name.
    present = set(_words(title))
    if not all(word in present for word in _words(card.name)):
        return False
    # Its number, and no other card's. "4/102" names the card by itself;
    # a title without one ("#4", as on a slab's label) must name the set too.
    wanted = _plain_number(card.number)
    fractions = _FRACTION.findall(title)
    # A reprint set's cards keep the number of the card they reprint, not
    # the catalogue's: there the set and a name no other card in it has are
    # the card, whatever number the title gives.
    reprint = card.set_code in REPRINT_SETS and card.unique_name and _names_set(title, card)
    if card.lettered and wanted in {_plain_number(word) for word in present}:
        # "XY28", "TG16": a code that, with the name, is the card.
        pass
    elif fractions:
        if not reprint:
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
        # An unmarked number counts unless it is also a word of the set's
        # or the card's name: "151" in a title of the 151 set is the set.
        spoken = {_plain_number(word) for word in (*card.set_words, *_words(card.name))}
        numbered = all(number == wanted for number in marked) if marked else (
            wanted not in spoken and wanted in {_plain_number(word) for word in present}
        )
        if not numbered and not (reprint and len(marked) == 1):
            return False
    # The language.
    # A Japanese set's code ("sm12", "sv2a") says Japanese as well as the word.
    says_japanese = bool(_JAPANESE.search(title)) or (
        card.japanese and bool(card.set_code) and card.set_code.lower() in present
    )
    if card.japanese != says_japanese or _OTHER_LANGUAGE.search(title):
        return False
    if _LANGUAGE_CODE.search(title):
        return False
    # The printing. A pattern copy is titled with its pattern, with or
    # without "reverse holo", and never with another pattern beside it.
    own_pattern = PATTERNS.get(card.pattern)
    if own_pattern is not None:
        if own_pattern[1].search(title) is None:
            return False
        if any(
            words.search(title) for key, (_, words) in PATTERNS.items() if key != card.pattern
        ):
            return False
    elif card.reverse != bool(_REVERSE.search(title)):
        return False
    # A copy not marked first edition is an unlimited one: a "1st Edition"
    # listing is another, dearer card.
    first = bool(re.search(r"\b1st\b|\bfirst\s+ed", title, re.IGNORECASE))
    if bool(card.first_edition) != first:
        return False
    # Every such word, not only the first. A promo is often an event's own
    # stamped card, so those words belong to it; "staff" is always dearer.
    promo_words = {"promo", "prerelease", "pre-release", "stamp", "stamped", "league", "winner"}
    for rule in (_VARIANT, _REPRINT):
        for found in rule.finditer(title):
            word = found.group(0).lower()
            if word in card.set_name.lower() or (card.promo and word in promo_words):
                continue
            if " ".join(word.split()) in REPRINT_SETS.get(card.set_code, ()):
                continue
            if card.first_edition and word == "shadowless":
                continue
            if own_pattern is not None and own_pattern[1].search(word):
                continue
            return False
    # The year, where the title gives one: a reprint is years later.
    # Not for promos: one promo series is printed over several years.
    if card.year is not None and not card.promo:
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
        if not listing_is(title, card, graded=bool(item.get("gradedByEbay"))):
            continue
        found.append({
            "id": str(item.get("itemId") or ""),
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


def item_confirms(item: dict[str, Any], card: GradedCard) -> bool:
    """Whether an opened listing's own fields agree it is the card in the grade."""
    recorded = {
        str(entry.get("name")): str((entry.get("values") or [{}])[0].get("content") or "")
        for entry in item.get("conditionDescriptors") or []
    }
    grader = recorded.get("Professional Grader")
    if grader and grader != GRADER_NAMES.get(card.grader):
        return False
    grade = recorded.get("Grade")
    if grade and grade != card.grade_number:
        return False
    entered = {
        str(aspect.get("name")): str(aspect.get("value") or "")
        for aspect in item.get("localizedAspects") or []
    }
    language = entered.get("Language", "").strip().lower()
    if language and language != "not specified":
        if card.japanese != (language == "japanese") or (
            not card.japanese and language != "english"
        ):
            return False
    number = entered.get("Card Number", "").strip()
    if number and card.set_code not in REPRINT_SETS:
        parts = _FRACTION.findall(number)
        head = parts[0][0] if parts else number.lstrip("#")
        if head.strip().isdigit() and _plain_number(head) != _plain_number(card.number):
            return False
        if parts and card.total and int(parts[0][1]) != card.total:
            return False
    return True


class Ebay:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        environment: str = "production",
        marketplace: str = "EBAY_US",
        currency: str = "USD",
        reuse_s: int = 24 * 3600,
        path: Path | None = None,
        take: int = 5,
        least: int = 2,
        background_daily: int = 200,
        client: httpx.Client | None = None,
    ) -> None:
        self._basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        self.marketplace = marketplace
        self.currency = currency
        self.reuse_s = reuse_s
        self.take = take
        self.least = least
        # Lookups nobody is waiting for: graded copies in collections, asked
        # about one at a time, up to a number a day.
        self.background_daily = background_daily
        self._wanted: dict[GradedCard, None] = {}
        self._filled: list[float] = []
        self._filler: threading.Thread | None = None
        self._client = client or httpx.Client(
            base_url=HOSTS.get(environment, HOSTS["production"]),
            timeout=20,
            headers={"User-Agent": USER_AGENT},
        )
        self._lock = threading.Lock()
        self._token: tuple[float, str] | None = None
        # Answers by card and grade. On disk where a path is given, so a
        # restart does not ask eBay for everything again.
        self._store = sqlite3.connect(path or ":memory:", check_same_thread=False)
        self._store.execute(
            "CREATE TABLE IF NOT EXISTS answers (card TEXT PRIMARY KEY, at REAL NOT NULL, answer TEXT NOT NULL)"
        )
        # What each card and grade went for, one figure a day, for the rise
        # or fall; and the slabs collections hold, read again every day.
        self._store.execute(
            "CREATE TABLE IF NOT EXISTS history (card TEXT NOT NULL, day TEXT NOT NULL, "
            "average REAL NOT NULL, PRIMARY KEY (card, day))"
        )
        self._store.execute(
            "CREATE TABLE IF NOT EXISTS owned (card TEXT PRIMARY KEY, spec TEXT NOT NULL, at REAL NOT NULL)"
        )
        self._store.commit()
        self._closed = threading.Event()

    def own(self, card: GradedCard) -> None:
        """Notes that a collection holds the card in the grade, so its price
        is read again each day for as long as collections keep asking."""
        with self._lock:
            with self._store:
                self._store.execute(
                    "INSERT OR REPLACE INTO owned VALUES (?, ?, ?)",
                    (repr(card), json.dumps(dataclasses.asdict(card)), time.time()),
                )

    def refresh_owned(self) -> int:
        """Queues every held slab whose price is more than a day old. Slabs
        no collection asked about for 30 days are forgotten."""
        with self._lock:
            with self._store:
                self._store.execute("DELETE FROM owned WHERE at < ?", (time.time() - OWNED_S,))
            rows = self._store.execute(
                "SELECT o.spec FROM owned o LEFT JOIN answers a ON a.card = o.card "
                "WHERE a.at IS NULL OR a.at < ?",
                (time.time() - self.reuse_s,),
            ).fetchall()
        for (spec,) in rows:
            self.want(GradedCard(**json.loads(spec)))
        return len(rows)

    def keep_fresh(self, every_s: float = 3600) -> None:
        """Reads held slabs again each day, without anyone opening the app,
        so the price history has a point for every day."""
        def loop() -> None:
            while not self._closed.wait(every_s):
                try:
                    self.refresh_owned()
                except Exception as exc:
                    log.warning("ebay daily refresh failed error_type=%s", type(exc).__name__)

        threading.Thread(target=loop, name="ebay-daily", daemon=True).start()

    def change(self, card: GradedCard, *, days: int = 30, least_days: int = 7) -> dict[str, Any] | None:
        """How the price moved: today's figure against the oldest one in the
        last [days], when that is at least a week back. None before then."""
        today = datetime.now(timezone.utc).date()
        with self._lock:
            rows = self._store.execute(
                "SELECT day, average FROM history WHERE card = ? AND day >= ? ORDER BY day",
                (repr(card), (today - timedelta(days=days)).isoformat()),
            ).fetchall()
        if len(rows) < 2:
            return None
        first, last = rows[0], rows[-1]
        span = (date.fromisoformat(last[0]) - date.fromisoformat(first[0])).days
        # The newest figure has to be a current one, and the old one real.
        if span < least_days or (today - date.fromisoformat(last[0])).days > 2 or first[1] <= 0:
            return None
        return {"percent": round((last[1] / first[1] - 1) * 100, 1), "days": span}

    def daily(self) -> "Ebay":
        self.keep_fresh()
        return self

    def close(self) -> None:
        self._closed.set()
        self._client.close()
        with self._lock:
            self._store.close()

    def kept(self, card: GradedCard, *, max_age_s: float | None = None) -> dict[str, Any] | None:
        """The answer already held for the card and grade, while it stands:
        a day for a look at one card; [max_age_s] for a longer view."""
        found = self.last(card)
        if found is None or found[0] >= (self.reuse_s if max_age_s is None else max_age_s):
            return None
        return found[1]

    def last(self, card: GradedCard) -> tuple[float, dict[str, Any]] | None:
        """The last answer held, however old, with its age in seconds."""
        with self._lock:
            row = self._store.execute(
                "SELECT at, answer FROM answers WHERE card = ?", (repr(card),)
            ).fetchone()
        return None if row is None else (time.time() - float(row[0]), json.loads(row[1]))

    def want(self, card: GradedCard) -> None:
        """Asks eBay about the card in the background, when its turn comes."""
        with self._lock:
            self._wanted.setdefault(card, None)
            if self._filler is None or not self._filler.is_alive():
                self._filler = threading.Thread(target=self._fill, name="ebay-fill", daemon=True)
                self._filler.start()

    def _fill(self) -> None:
        while True:
            with self._lock:
                day_ago = time.time() - 86400
                self._filled = [at for at in self._filled if at > day_ago]
                if not self._wanted or len(self._filled) >= self.background_daily:
                    # Out of work, or out of today's allowance: what is left
                    # waits for the next request to start this again.
                    if len(self._filled) >= self.background_daily:
                        self._wanted.clear()
                    self._filler = None
                    return
                card = next(iter(self._wanted))
                del self._wanted[card]
                self._filled.append(time.time())
            try:
                if self.kept(card) is None:
                    self.graded(card)
            except Exception as exc:  # one card failing does not stop the rest
                log.warning("ebay background read failed error_type=%s", type(exc).__name__)
            time.sleep(1.0)

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

    def _page(self, query: str, *, graded: GradedCard | None) -> list[dict[str, Any]]:
        params = {
            "q": query,
            "category_ids": SINGLE_CARDS,
            "filter": "buyingOptions:{FIXED_PRICE}",
            "sort": "price",
            "limit": 200,
        }
        if graded is not None:
            params["filter"] += f",conditionIds:{{{GRADED_CONDITION}}}"
            params["aspect_filter"] = (
                f"categoryId:{SINGLE_CARDS},"
                f"Professional Grader:{{{GRADER_NAMES[graded.grader]}}},Grade:{{{graded.grade_number}}}"
            )
        reply = self._client.get(
            "/buy/browse/v1/item_summary/search",
            headers={
                "Authorization": f"Bearer {self._bearer()}",
                "X-EBAY-C-MARKETPLACE-ID": self.marketplace,
            },
            params=params,
        )
        reply.raise_for_status()
        return reply.json().get("itemSummaries") or []

    def search(self, card: GradedCard) -> list[dict[str, Any]]:
        """eBay's Buy It Now single-card listings that may be the card.

        Four searches, merged. Two ask eBay for its own grader and grade
        fields, with the card by number and by set: they find listings whose
        title never says the grade (16% of a sample on 22 November 2026).
        Two put the grade in the words instead: they find slabs listed under
        the wrong condition, and listings on eBay's other sites. A listing
        from the first two carries "gradedByEbay".
        """
        jp = " Japanese" if card.japanese else ""
        number = card.number_label
        named = " ".join(card.set_words) if card.set_name.isascii() else card.set_code
        found: dict[str, dict[str, Any]] = {}
        if card.grader in GRADER_NAMES:
            for query in dict.fromkeys(
                q for q in (f"{card.titled} {number}{jp}", f"{card.titled} {named}{jp}" if named else "") if q
            ):
                for item in self._page(query, graded=card):
                    key = str(item.get("itemId") or item.get("itemWebUrl") or item.get("title"))
                    found[key] = {**item, "gradedByEbay": True}
        for query in dict.fromkeys(q for q in (card.search, card.set_search) if q):
            for item in self._page(query, graded=None):
                # One listing found by several searches counts once.
                key = str(item.get("itemId") or item.get("itemWebUrl") or item.get("title"))
                found.setdefault(key, item)
        return list(found.values())

    def confirms(self, item_id: str, card: GradedCard) -> bool:
        """Whether the listing itself, opened, is the card in the grade: its
        recorded grader and grade, and the card number and language the
        seller entered. What it does not record is not held against it."""
        if not item_id:
            return False
        reply = self._client.get(
            f"/buy/browse/v1/item/{item_id}",
            headers={
                "Authorization": f"Bearer {self._bearer()}",
                "X-EBAY-C-MARKETPLACE-ID": self.marketplace,
            },
        )
        if reply.status_code != 200:
            return False
        return item_confirms(reply.json(), card)

    def graded(self, card: GradedCard) -> dict[str, Any]:
        """The app's payload: the average of the cheapest listings, how many
        matched, the listings averaged, and when eBay was asked."""
        kept = self.kept(card)
        if kept is not None:
            return kept
        items = self.search(card)
        listings = graded_listings(items, card, currency=self.currency)
        # The cheapest listings set the average, so each is opened and
        # checked before it counts.
        cheapest: list[dict[str, Any]] = []
        refused = 0
        for listing in listings[:CHECKS]:
            if len(cheapest) == self.take:
                break
            if self.confirms(listing["id"], card):
                cheapest.append(listing)
            else:
                refused += 1
        enough = len(cheapest) >= self.least
        log.info(
            "ebay graded grader=%s grade=%s fetched=%s kept=%s confirmed=%s refused=%s",
            card.grader, card.grade, len(items), len(listings), len(cheapest), refused,
        )
        cheapest = [
            {key: value for key, value in listing.items() if key != "id"} for listing in cheapest
        ]
        answer = {
            "enabled": True,
            # The middle of the cheapest listings, not their mean: four at
            # $750 and one at $2,999 are a $775 card, not a $1,200 one.
            "average": round(statistics.median(item["amount"] for item in cheapest), 2)
            if enough
            else None,
            "currency": self.currency,
            "count": max(0, len(listings) - refused),
            # Fewer than enough for an average are still shown as they are.
            "listings": cheapest,
            "observed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        with self._lock:
            with self._store:
                self._store.execute(
                    "INSERT OR REPLACE INTO answers VALUES (?, ?, ?)",
                    (repr(card), time.time(), json.dumps(answer)),
                )
                self._store.execute(
                    "DELETE FROM answers WHERE at < ?", (time.time() - KEEP_S,)
                )
                if answer["average"] is not None:
                    today = datetime.now(timezone.utc).date()
                    self._store.execute(
                        "INSERT OR REPLACE INTO history VALUES (?, ?, ?)",
                        (repr(card), today.isoformat(), answer["average"]),
                    )
                    self._store.execute(
                        "DELETE FROM history WHERE day < ?",
                        ((today - timedelta(days=HISTORY_DAYS)).isoformat(),),
                    )
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
        background_daily=max(0, int(settings.ebay_background_daily)),
        path=settings.data_dir / "ebay.sqlite",
    ).daily()
