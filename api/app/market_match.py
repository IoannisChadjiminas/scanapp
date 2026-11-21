"""Finding a catalogue card on another marketplace when its Cardmarket id does not.

CardTrader lists many Japanese cards without a Cardmarket id, and TCGplayer is
reached through CardTrader's list, so both leave gaps. This fills them: the
card's set is found on the other side (from the cards of the same set that do
match, the set's name, or its code), then the card inside it by collector
number and name.

Measured on the whole English and Japanese catalogue (51,270 cards, 21
November 2026): CardTrader 97.8% -> 99.6% of English and 83.9% -> 95.2% of
Japanese cards; where the right card was already known it picked the same one
for 99.4% of Japanese cards.
"""
from __future__ import annotations

import difflib
from collections import Counter
from collections.abc import Callable, Iterable
from typing import TypeVar

T = TypeVar("T")

# Our set -> the marketplace's name for it, where neither a matching card, the
# name nor the code finds it. Keyed by (catalogue language, set id).
SET_NAMES: dict[tuple[str, str], tuple[str, ...]] = {
    ("ja", "web1"): ("Pokémon Web",),
    ("ja", "PMCG5"): ("Gym Booster 1 Leaders' Stadium",),
    ("ja", "jr-quick-starter-gift-set-green"): ("Quick Starter Gift Set 1998",),
    ("ja", "jr-quick-starter-gift-set-red"): ("Quick Starter Gift Set 1998",),
    ("ja", "jr-master-kit-bulbasaur"): ("Master Kit: Bulbasaur Quarter Deck",),
    ("ja", "jr-master-kit-torchic"): ("Master Kit: Torchic Quarter Deck",),
    ("ja", "jr-master-kit-side-deck"): ("Master Kit - Sideboard",),
    ("ja", "HSP"): ("Beginning Set | Pikachu Version",),
    ("ja", "jr-neo-premium-file-1"): ("Gold, Silver, to a New World… Premium File",),
    ("ja", "jr-neo-premium-file-2"): ("Crossing the Ruins… Premium File 2",),
    ("ja", "jr-neo-premium-file-3"): ("Awakening Legends Premium File 3",),
    ("ja", "jr-movie-commemoration-random-pack"): ("Movie Commemoration Random",),
    ("ja", "LP"): ("L-P Promo",),
}

# A set counts as found from its matching cards when it holds at least this
# share of them (and two cards): a few promos filed elsewhere do not count.
VOTE_SHARE = 0.1
CLOSE_NAME = 0.9


def plain(text: object) -> str:
    """Letters and digits only, lower case: how names and set titles compare."""
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def plain_number(text: object) -> str:
    """"001/100" and "1" are the same collector number."""
    head = str(text or "").split("/")[0].strip().lower()
    return head.lstrip("0") or ("0" if head else "")


def listing_parts(cardmarket_url: object) -> tuple[str, str]:
    """A Cardmarket address's set and card names, plain: ("infinityzone", "parass31")."""
    tail = str(cardmarket_url or "").split("/Singles/", 1)
    if len(tail) != 2:
        return "", ""
    parts = tail[1].split("?")[0].split("/")
    return (plain(parts[0]), plain(parts[1])) if len(parts) >= 2 else ("", "")


def card_names(cardmarket_url: object, name: object) -> list[str]:
    """What the card is called, plain: from its Cardmarket address, and its
    own name where that is in Latin letters."""
    slug = listing_parts(cardmarket_url)[1]
    own = plain(name) if str(name or "").isascii() else ""
    return [text for text in (slug, own) if text]


def set_names(language: str, set_id: str, set_name: object, urls: Iterable[object]) -> set[str]:
    """Every plain name the card's set may go by on the other marketplace."""
    names = {plain(set_name)}
    for url in urls:
        listed = listing_parts(url)[0]
        # Cardmarket marks some Japanese sets "-JP"; the others do not.
        names |= {listed, listed.removesuffix("jp")}
    names |= {plain(alias) for alias in SET_NAMES.get((language, set_id), ())}
    return names - {""}


def close_names(wanted: Iterable[str], known: list[str]) -> set[str]:
    """Known set names spelt almost like a wanted one ("holonphantom")."""
    found: set[str] = set()
    for name in wanted:
        found.update(difflib.get_close_matches(name, known, n=2, cutoff=CLOSE_NAME))
    return found


def voted(votes: Counter) -> set:
    """The sets most of a catalogue set's matching cards are filed under."""
    total = sum(votes.values())
    return {key for key, count in votes.items() if count >= max(2, VOTE_SHARE * total)}


def pick(pool: Iterable[T], names: list[str], name_of: Callable[[T], str]) -> T | None:
    """The one candidate the card's name agrees with, or None.

    A candidate agrees when its name starts the card's ("pikachuex" and the
    card's "pikachuexsv2a001"); among several the longest wins, so
    "Pikachu ex" is not taken for "Pikachu". Failing that, one whose name
    the card's starts ("paras" for a candidate "paraslv16"). Without a name
    to check, a single candidate is taken as it is.
    """
    items = list(dict.fromkeys(pool))
    if names:
        inside = [
            item for item in items
            if (other := name_of(item)) and any(name.startswith(other) for name in names)
        ]
        if inside:
            longest = max(len(name_of(item)) for item in inside)
            items = [item for item in inside if len(name_of(item)) == longest]
        else:
            items = [
                item for item in items
                if (other := name_of(item)) and any(other.startswith(name) for name in names)
            ]
    return items[0] if len(items) == 1 else None
