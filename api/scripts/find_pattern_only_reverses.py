"""Rebuild app/pattern_only_reverses.csv from TCGdex's detailed variants.

A card is listed when every reverse TCGdex knows for it is a named pattern
(Poké Ball, Master Ball, Energy...) sold as its own Cardmarket product. Such a
card has no plain reverse, so the server offers none (see app/reverse_holos.py).

Only cards the catalogue flags `reverse` in the eras with patterns are read:
Scarlet & Violet, Mega Evolution and every non-English card.

    python scripts/find_pattern_only_reverses.py path/to/catalog.sqlite [--cache DIR]
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import csv
import json
import sqlite3
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "app" / "pattern_only_reverses.csv"
QUERY = """
SELECT id, language, cardmarket_id FROM cards
WHERE json_extract(variants_json, '$.reverse') = 1
  AND (language != 'en' OR set_id GLOB 'sv*' OR set_id GLOB 'me*' OR set_id GLOB '30th*')
"""


def _detail(card_id: str, language: str, cache: Path) -> dict:
    path = cache / (card_id.replace(":", "_").replace("/", "_") + ".json")
    if not path.exists():
        tcgdex_id = card_id.split(":", 1)[1] if ":" in card_id else card_id
        url = f"https://api.tcgdex.net/v2/{language}/cards/{urllib.parse.quote(tcgdex_id)}"
        with urllib.request.urlopen(url, timeout=20) as response:
            path.write_bytes(response.read())
    return json.loads(path.read_text())


def pattern_only(detail: dict, main_product: int | None) -> list[dict] | None:
    reverses = [item for item in detail.get("variants_detailed") or [] if item.get("type") == "reverse"]
    own = [(item.get("thirdParty") or {}).get("cardmarket") for item in reverses]
    if reverses and all(item.get("foil") for item in reverses) and all(p not in (None, main_product) for p in own):
        return reverses
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--cache", type=Path, default=Path(".tcgdex-cache"))
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.catalog)
    conn.row_factory = sqlite3.Row
    cards = conn.execute(QUERY).fetchall()
    with futures.ThreadPoolExecutor(8) as pool:
        details = list(pool.map(lambda row: _detail(row["id"], row["language"], args.cache), cards))
    rows = []
    for card, detail in zip(cards, details):
        reverses = pattern_only(detail, card["cardmarket_id"])
        if reverses:
            rows.append([
                card["id"],
                " ".join(sorted({item["foil"] for item in reverses})),
                " ".join(str(p) for p in sorted({item["thirdParty"]["cardmarket"] for item in reverses})),
            ])
    with open(OUT, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["card_id", "patterns", "cardmarket_products"])
        writer.writerows(sorted(rows))
    print(f"read {len(cards)} cards, wrote {len(rows)} to {OUT}")


if __name__ == "__main__":
    main()
