"""Reverse holo printings TCGdex leaves out.

TCGdex marks almost every Black & White, XY and Sun & Moon card, and every
card from Delta Species to Power Keepers, as having no reverse holo (Cubone
90/214 from Unbroken Bonds, for one), so no finish choice was offered for them.
Those sets print a reverse holo of every Common, Uncommon and Rare inside the
printed set total; the ex/EX, GX, BREAK, Prism Star, Gold Star, basic Energy
and secret cards above the total have none (EX-era Darkness and Metal
Energy are special Energy Rares and do have one). Cardmarket's price file is no help
here: its reverse holo columns also carry figures for ultra rares and for Base
Set cards, so it cannot say which cards have one.

The rule only adds a reverse finish next to a plain or holo one, so prices of
reverse-only printings are unchanged.

The other way round, some cards have no plain reverse at all: every reverse
they have is a pattern (Poké Ball, Master Ball, Energy...) that Cardmarket
sells as its own product, as in JP 151 and Ascended Heroes. TCGdex still flags
them `reverse`, and the main product's reverse holo figures are then other
products' sales (8.33 € for JP 151 Bulbasaur, whose Poké Ball and Master Ball
versions sell at 1.58 € and 38.99 €). `pattern_only_reverses.csv` lists those
cards, read from TCGdex's detailed variants; they offer no plain reverse.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Mapping

PATTERN_ONLY_FILE = Path(__file__).with_name("pattern_only_reverses.csv")


def _read_pattern_only(path: Path = PATTERN_ONLY_FILE) -> frozenset[str]:
    try:
        with open(path, newline="", encoding="utf-8") as handle:
            return frozenset(row["card_id"] for row in csv.DictReader(handle) if row.get("card_id"))
    except FileNotFoundError:
        return frozenset()


PATTERN_ONLY: frozenset[str] = _read_pattern_only()

# Printed set totals of the sets with reverse holos for their regular cards.
# Sets with none (Generations, Double Crisis, Dragon Vault, Detective Pikachu,
# the Kalos Starter Set, Radiant Collection and promos) are left out.
PRINTED_TOTALS: dict[str, int] = {
    "ex11": 113, "ex12": 92, "ex13": 110, "ex14": 100, "ex15": 101, "ex16": 108,
    "bw1": 114, "bw2": 98, "bw3": 101, "bw4": 99, "bw5": 108, "bw6": 124,
    "bw7": 149, "bw8": 135, "bw9": 116, "bw10": 101, "bw11": 113,
    "xy1": 146, "xy2": 106, "xy3": 111, "xy4": 119, "xy5": 160, "xy6": 108,
    "xy7": 98, "xy8": 162, "xy9": 122, "xy10": 124, "xy11": 114, "xy12": 108,
    "sm1": 149, "sm2": 145, "sm3": 147, "sm3.5": 73, "sm4": 111, "sm5": 156,
    "sm6": 131, "sm7": 168, "sm7.5": 70, "sm8": 214, "sm9": 181, "sm10": 214,
    "sm11": 236, "sm115": 68, "sm12": 236,
}

_REGULAR = {"common", "uncommon", "rare"}
# TCGdex files some of these as plain "Rare".
_NO_REVERSE_NAME = re.compile(r"(-| )(EX|ex)\b|\bGX\b|\bBREAK\b|◇|☆|Prism Star|^M ")
_SPECIAL_ENERGY = {"Darkness Energy", "Metal Energy"}
_BASIC_ENERGY = re.compile(r"^(Grass|Fire|Water|Lightning|Psychic|Fighting|Darkness|Metal|Fairy) Energy$")


def prints_reverse(set_id: Any, number: Any, rarity: Any, name: Any, language: Any = "en") -> bool:
    """Whether this card has a reverse holo that TCGdex may not list."""
    if str(language or "en").lower() == "ja":
        return False
    total = PRINTED_TOTALS.get(str(set_id or ""))
    number = str(number or "").strip()
    if total is None or not number.isdigit() or not 0 < int(number) <= total:
        return False
    rarity_key = str(rarity or "").strip().lower()
    if rarity_key not in _REGULAR:
        return False
    name = str(name or "").strip()
    if _NO_REVERSE_NAME.search(name):
        return False
    # EX-era Darkness and Metal Energy are special Energy cards, printed as
    # Rares with a reverse holo like any other Rare.
    if _BASIC_ENERGY.match(name):
        special = str(set_id).startswith("ex") and name in _SPECIAL_ENERGY and rarity_key == "rare"
        return special
    return True


def with_reverse(variants: dict[str, Any], card: Mapping[str, Any] | Any) -> dict[str, Any]:
    """The stored variants, corrected: the reverse finish the rule says exists
    is added, and a reverse that is only sold as pattern products is removed.

    `card` is a catalogue row with `id`, `set_id`, `collector_number`,
    `rarity`, `name` and `language`; a row without them is returned as stored.
    """
    if not (variants.get("normal") or variants.get("holo")):
        return variants
    try:
        if variants.get("reverse"):
            return {**variants, "reverse": False} if card["id"] in PATTERN_ONLY else variants
        printed = prints_reverse(
            card["set_id"], card["collector_number"], card["rarity"], card["name"], card["language"]
        )
    except (KeyError, IndexError, TypeError):
        return variants
    return {**variants, "reverse": True} if printed else variants


def has_reverse(card_id: Any, set_id: Any, number: Any, rarity: Any, name: Any,
                language: Any, variants_json: Any) -> int:
    """`with_reverse` for SQL, registered on catalogue connections as
    `card_has_reverse`, so a search by finish agrees with the card page."""
    try:
        variants = json.loads(variants_json or "{}")
    except (TypeError, ValueError):
        return 0
    if not isinstance(variants, dict):
        return 0
    card = {"id": card_id, "set_id": set_id, "collector_number": number,
            "rarity": rarity, "name": name, "language": language}
    return int(bool(with_reverse(variants, card).get("reverse")))


def register(conn: Any) -> None:
    """Make `card_has_reverse(...)` available to SQL on this connection."""
    conn.create_function("card_has_reverse", 7, has_reverse, deterministic=True)


REVERSE_SQL = (
    "card_has_reverse(cards.id, cards.set_id, cards.collector_number, cards.rarity,"
    " cards.name, cards.language, cards.variants_json)=1"
)
