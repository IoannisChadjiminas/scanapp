"""Name Cardmarket listings that are only numbered (V1, V2, V3) by rule.

Writes candidate rows for ``app/cardmarket_listing_labels.csv``. Nothing here
opens Cardmarket. Evidence, in order of use:

1. TCGdex ``variants_detailed`` names a product by its Cardmarket product id
   (stamp, foil, jumbo size). The product id comes from the listing photo
   address. A stamped or special-foil product is named only when it trends
   above the card's plain listing in Cardmarket's price guide; otherwise it
   keeps its number for photo reading.
2. McDonald's Collection 25th Anniversary: V1 is the non-holo, V2 the holo
   (TCGdex agrees on every pair it has).
3. A listing in a different expansion from the card is named by that
   expansion (Professor Program, Southeast Asia promo, W stamp, Trainer Kit).
4. The card's own listing, unnumbered and alone in its expansion, is "Normal".

A label is never guessed: unknown TCGdex stamps keep the number, and if two
listings of one card would get the same label, both keep their numbers.

Inputs (see docs/cardmarket-numbered-listings.md for how they are made):
  --rows    JSON list of listings: card_id, url, expansion, name, image, card_url
  --tcgdex  JSON object: TCGdex card id -> {"variants_detailed": [...]}
  --guide   Cardmarket price_guide_6.json
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

PRODUCT_ID = re.compile(r"/(\d+)/\1\.(?:jpe?g|png|webp)", re.I)
VERSION = re.compile(r"-V(\d+)(?:-|$)")

STAMPS = {
    "set-logo": "Set logo stamp",
    "staff": "Staff stamp",
    "pre-release": "Prerelease stamp",
    "player-rewards-program": "Play! Pokémon stamp",
    "professor-program": "Professor Program",
    "snowflake": "Snowflake stamp",
    "winner": "Winner stamp",
    "regional-championships": "Regionals stamp",
    "national-championships": "Nationals stamp",
    "state-championships": "States stamp",
    "city-championships": "City Championships stamp",
    "pokemon-center": "Pokémon Center stamp",
    "poke-ball-league": "League stamp",
    "great-ball-league": "League stamp",
    "ultra-ball-league": "League stamp",
    "master-ball-league": "League stamp",
    "gym-challenge": "Gym Challenge stamp",
    "gamestop": "GameStop stamp",
    "eb-games": "EB Games stamp",
    "worlds-2023": "Worlds 2023 stamp",
    "worlds-2025": "Worlds 2025 stamp",
    "pokemon-day": "Pokémon Day stamp",
    "trick-or-trade": "Trick or Trade stamp",
    "build-a-bear": "Build-A-Bear stamp",
    "10th-anniversary": "10th anniversary stamp",
    "toys-r-us": "Toys R Us stamp",
    "comic-con": "Comic-Con stamp",
    "judge": "Judge stamp",
    "champion": "Champion stamp",
    "w-promo": "W stamp",
}
PLACES = {
    "1st-place": "1st place", "2nd-place": "2nd place", "3rd-place": "3rd place",
    "4th-place": "4th place", "top-eight": "top 8", "top-sixteen": "top 16",
    "top-thirty-two": "top 32", "semi-finalist": "semi-finalist", "finalist": "finalist",
}
FOILS = {
    "cosmos": "Cosmos holo",
    "cracked-ice": "Cracked ice holo",
    "galaxy": "Galaxy holo",
    "tinsel": "Tinsel",
    "pokeball": "Poké Ball pattern",
    "masterball": "Master Ball pattern",
}
# A league foil is the reverse pattern of a league stamp; it adds nothing to the stamp's name.
SILENT_FOILS = {"league", "player-reward"}
PLAIN_TYPES = {"normal": "Non-holo", "holo": "Holo", "reverse": "Reverse holo"}

EXPANSIONS = {
    "Professor-Program": "Professor Program",
    "Southeast-Asia-Promos": "Southeast Asia promo",
    "W-Promos": "W stamp",
    "SM-Trainer-Kit-Alolan-Sandslash-Alolan-Ninetales": "Trainer Kit",
}
MCDONALDS = {"McDonalds-Collection-25th-Anniversary": {1: "Non-holo", 2: "Holo"}}


def product_id(image: str | None) -> int | None:
    match = PRODUCT_ID.search(image or "")
    return int(match.group(1)) if match else None


def version(url: str) -> int | None:
    match = VERSION.search(url.rsplit("/", 1)[-1])
    return int(match.group(1)) if match else None


def is_plain(variant: dict) -> bool:
    stamps = set(variant.get("stamp") or []) - {"1st-edition"}
    return (not stamps and not variant.get("foil")
            and (variant.get("size") or "standard") == "standard"
            and variant.get("type") in PLAIN_TYPES)


def special_label(variant: dict) -> str | None:
    """Short name of a stamped, special-foil or jumbo variant; None if unknown."""
    if variant.get("type") not in PLAIN_TYPES:
        return None
    parts: list[str] = []
    if (variant.get("size") or "standard") == "jumbo":
        parts.append("Jumbo")
    elif (variant.get("size") or "standard") != "standard":
        return None
    foil = variant.get("foil")
    if foil and foil not in SILENT_FOILS:
        if foil not in FOILS:
            return None
        parts.append(FOILS[foil])
    stamps = list(variant.get("stamp") or [])
    places = [PLACES[s] for s in stamps if s in PLACES]
    named = [s for s in stamps if s not in PLACES and s != "1st-edition"]
    if "1st-edition" in stamps:
        return None  # 1st Edition is a condition on the product's own listing
    if "set-logo" in named and "staff" in named:
        named.remove("set-logo")
    if any(s not in STAMPS for s in named) or len(places) > 1:
        return None
    if len(named) > 1:
        return None
    if named:
        label = STAMPS[named[0]]
        if places:
            label = label.replace(" stamp", f" {places[0]} stamp") if label.endswith(" stamp") else f"{label} {places[0]}"
        parts.append(label)
    elif places:
        return None
    if not parts:
        return None
    if foil in SILENT_FOILS and not named:
        return None
    return ", ".join(parts)


def _trend(guide: dict[int, dict], pid: int | None) -> float | None:
    row = guide.get(pid) if pid else None
    if not row:
        return None
    for key in ("trend", "avg30", "trend-holo", "avg30-holo"):
        value = row.get(key)
        if value:
            return float(value)
    return None


def name_card(listings: list[dict], variants: list[dict], guide: dict[int, dict]) -> dict[str, tuple[str, str]]:
    """url -> (label, rule) for one catalogue card's listings."""
    by_pid: dict[int, list[dict]] = collections.defaultdict(list)
    for variant in variants:
        pid = (variant.get("thirdParty") or {}).get("cardmarket")
        if pid:
            by_pid[int(pid)].append(variant)
    found: dict[str, tuple[str, str]] = {}
    plain: dict[str, set[str]] = {}
    special: dict[str, str] = {}
    mixed = False
    for item in listings:
        url, pid = item["url"], item["pid"]
        mine = by_pid.get(pid, []) if pid else []
        kinds = {is_plain(v) for v in mine}
        if kinds == {True, False}:
            mixed = True  # one product both plain and special: TCGdex contradicts itself
        elif mine and all(is_plain(v) for v in mine):
            plain[url] = {v["type"] for v in mine}
        elif len(mine) == 1 or (mine and len({special_label(v) for v in mine}) == 1):
            label = special_label(mine[0])
            if label:
                special[url] = label
    primary = {item["url"] for item in listings if item["primary"]}
    if mixed or (plain and not primary & plain.keys()):
        # TCGdex is used for a card only when it agrees with itself and its
        # plain product is the card's own listing.
        plain, special = {}, {}
    # Plain listings: "Normal" when there is one, by finish when there are several.
    if len(plain) == 1:
        (url,) = plain
        found[url] = ("Normal", f"tcgdex {_pid(listings, url)}")
    elif len(plain) > 1:
        names = {url: _finish(types) for url, types in plain.items()}
        for url, label in names.items():
            if label:
                found[url] = (label, f"tcgdex {_pid(listings, url)}")
    plain_prices = [p for url in plain if (p := _trend(guide, _pid(listings, url)))]
    for url, label in special.items():
        price = _trend(guide, _pid(listings, url))
        if not plain_prices or price is None or price <= max(plain_prices):
            continue  # TCGdex unconfirmed by price: leave for photo reading
        found[url] = (label, f"tcgdex {_pid(listings, url)}")
    home = {item["expansion"] for item in listings if item["primary"]}
    for item in listings:
        url, expansion = item["url"], item["expansion"]
        if url in found:
            continue
        rule = MCDONALDS.get(expansion)
        if rule and version(url) in rule:
            if url in plain and _finish(plain[url]) not in (None, rule[version(url)]):
                continue
            found[url] = (rule[version(url)], "mcdonalds")
        elif expansion in EXPANSIONS and expansion not in home:
            found[url] = (EXPANSIONS[expansion], "expansion")
        elif (item["primary"] and version(url) is None
              and sum(other["expansion"] == expansion for other in listings) == 1):
            found[url] = ("Normal", "own listing")
    counts = collections.Counter(label for label, _ in found.values())
    return {url: value for url, value in found.items() if counts[value[0]] == 1}


def _pid(listings: list[dict], url: str) -> int | None:
    return next(item["pid"] for item in listings if item["url"] == url)


def _finish(types: set[str]) -> str | None:
    if types in ({"normal"}, {"normal", "reverse"}):
        return "Non-holo"
    if types in ({"holo"}, {"holo", "reverse"}):
        return "Holo"
    if types == {"reverse"}:
        return "Reverse holo"
    return None


def build(rows: list[dict], tcgdex: dict, guide: dict[int, dict], known: set[str]) -> list[dict]:
    cards: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        cards[row["card_id"]].append({
            "url": row["url"], "expansion": row["expansion"], "pid": product_id(row.get("image")),
            "primary": row["url"] == row.get("card_url"),
        })
    out = []
    for card_id, listings in sorted(cards.items()):
        variants = (tcgdex.get(card_id.split(":", 1)[1]) or {}).get("variants_detailed") or []
        for url, (label, rule) in sorted(name_card(listings, variants, guide).items()):
            if url in known:
                continue
            pid = _pid(listings, url)
            out.append({"url": url, "label": label, "card_id": card_id,
                        "product_id": pid or "", "rule": rule})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--rows", type=Path, required=True)
    parser.add_argument("--tcgdex", type=Path, required=True)
    parser.add_argument("--guide", type=Path, required=True)
    parser.add_argument("--known", type=Path, default=Path(__file__).resolve().parents[1] / "app" / "cardmarket_listing_labels.csv")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    rows = json.loads(args.rows.read_text())
    tcgdex = json.loads(args.tcgdex.read_text())
    guide = {int(r["idProduct"]): r for r in json.loads(args.guide.read_text())["priceGuides"]}
    with open(args.known, newline="", encoding="utf-8") as handle:
        known = {row["url"] for row in csv.DictReader(handle)}
    named = build(rows, tcgdex, guide, known)
    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["url", "label", "card_id", "product_id", "rule"])
        writer.writeheader()
        writer.writerows(named)
    print(f"{len(named)} listings named; {collections.Counter(r['rule'].split()[0] for r in named)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
