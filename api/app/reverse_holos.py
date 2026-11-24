"""Reverse holo printings TCGdex leaves out.

TCGdex marks almost every Black & White, XY and Sun & Moon card, and every
card from Delta Species to Power Keepers, as having no reverse holo (Cubone
90/214 from Unbroken Bonds, for one), so no finish choice was offered for them.
Those sets print a reverse holo of every Common, Uncommon and Rare inside the
printed set total; the ex/EX, GX, BREAK, Prism Star, Gold Star, basic Energy
and secret cards above the total have none. Cardmarket's price file is no help
here: its reverse holo columns also carry figures for ultra rares and for Base
Set cards, so it cannot say which cards have one.

The rule only adds a reverse finish next to a plain or holo one, so prices of
reverse-only printings are unchanged.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

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
_BASIC_ENERGY = re.compile(r"^(Grass|Fire|Water|Lightning|Psychic|Fighting|Darkness|Metal|Fairy) Energy$")


def prints_reverse(set_id: Any, number: Any, rarity: Any, name: Any, language: Any = "en") -> bool:
    """Whether this card has a reverse holo that TCGdex may not list."""
    if str(language or "en").lower() == "ja":
        return False
    total = PRINTED_TOTALS.get(str(set_id or ""))
    number = str(number or "").strip()
    if total is None or not number.isdigit() or not 0 < int(number) <= total:
        return False
    if str(rarity or "").strip().lower() not in _REGULAR:
        return False
    name = str(name or "").strip()
    return not (_NO_REVERSE_NAME.search(name) or _BASIC_ENERGY.match(name))


def with_reverse(variants: dict[str, Any], card: Mapping[str, Any] | Any) -> dict[str, Any]:
    """The stored variants, with the reverse finish the rule says exists.

    `card` is a catalogue row with `set_id`, `collector_number`, `rarity`,
    `name` and `language`; a row without them is returned as stored.
    """
    if variants.get("reverse") or not (variants.get("normal") or variants.get("holo")):
        return variants
    try:
        printed = prints_reverse(
            card["set_id"], card["collector_number"], card["rarity"], card["name"], card["language"]
        )
    except (KeyError, IndexError, TypeError):
        return variants
    return {**variants, "reverse": True} if printed else variants
