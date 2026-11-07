"""Acquire high-resolution exact-variant scans for remaining Japanese XY promos."""
from __future__ import annotations

import hashlib
import argparse
import json
import urllib.request
from pathlib import Path

from acquire_official_group_images import image_info

ROOT = Path("data/catalogue-gaps/ja-set-recovery-20261029-v3")
REVIEW = ROOT / "review"
GROUP_ID = "ja-ref-703"
OUTPUT = REVIEW / "alternate-source-ja-ref-703-xy-promos-image-acquisition-20261030.json"
IMAGE_DIR = ROOT / "images" / "alternate-source" / GROUP_ID

# Exact event/retail printings were visually matched to the checklist images.
SOURCES = {
    "No. 301": {
        "name": "Grass Energy",
        "provider": "cardrush_pokemon",
        "url": "https://www.cardrush-pokemon.jp/data/cardrushpokemon/product/LAWSONKUSA.jpg",
        "page": "https://www.cardrush-pokemon.jp/product-group/214/0/normal?page=22",
        "basis": "CardRush Japanese product image shows the Lawson-stamped Grass Energy; the Grass symbol, Lawson mark, and XY-P footer match the XY Promos checklist entry.",
    },
    "No. 302": {
        "name": "Fire Energy",
        "provider": "cardrush_pokemon",
        "url": "https://www.cardrush-pokemon.jp/data/cardrushpokemon/product/LAWSONHONOO.jpg",
        "page": "https://www.cardrush-pokemon.jp/product-group/214/0/normal?page=22",
        "basis": "CardRush Japanese product image shows the Lawson-stamped Fire Energy; the Fire symbol, Lawson mark, and XY-P footer match the XY Promos checklist entry.",
    },
    "No. 303": {
        "name": "Water Energy",
        "provider": "cardrush_pokemon",
        "url": "https://www.cardrush-pokemon.jp/data/cardrushpokemon/product/LAWSONMIZU.jpg",
        "page": "https://www.cardrush-pokemon.jp/product-group/214/0/normal?page=22",
        "basis": "CardRush Japanese product image shows the Lawson-stamped Water Energy printing; the artwork, Lawson mark, and XY-P footer match the XY Promos checklist entry.",
    },
    "No. 306": {
        "name": "Fighting Energy",
        "provider": "cardrush_pokemon",
        "url": "https://www.cardrush-pokemon.jp/data/cardrushpokemon/product/LAWSONTOU.jpg",
        "page": "https://www.cardrush-pokemon.jp/product-group/214/0/normal?page=22",
        "basis": "CardRush Japanese product image shows the Lawson-stamped Fighting Energy; the Fighting symbol, Lawson mark, and XY-P footer match the XY Promos checklist entry.",
    },
    "No. 307": {
        "name": "Darkness Energy",
        "provider": "cardrush_pokemon",
        "url": "https://www.cardrush-pokemon.jp/data/cardrushpokemon/product/LAWSONAKU.jpg",
        "page": "https://www.cardrush-pokemon.jp/product-group/214/0/normal?page=22",
        "basis": "CardRush Japanese product image shows the Lawson-stamped Darkness Energy; the Darkness symbol, Lawson mark, and XY-P footer match the XY Promos checklist entry.",
    },
    "No. 308": {
        "name": "Metal Energy",
        "provider": "cardrush_pokemon",
        "url": "https://www.cardrush-pokemon.jp/data/cardrushpokemon/product/LAWSONHAGANE.jpg",
        "page": "https://www.cardrush-pokemon.jp/product-group/214/0/normal?page=22",
        "basis": "CardRush Japanese product image shows the Lawson-stamped Metal Energy; the Metal symbol, Lawson mark, and XY-P footer match the XY Promos checklist entry.",
    },
    "No. 304": {
        "name": "Lightning Energy",
        "provider": "hareruya2",
        "url": "https://omiya.hareruya2.com/cdn/shop/files/GQeH1FpHqhV30lmr0MN0r4v3LpxdDYuxr6vxUEx3.webp?v=1756445042&width=1445",
        "page": "https://omiya.hareruya2.com/products/30221",
        "basis": "Hareruya2 listing is titled Lawson XY-P Lightning Energy. The 1445x2052 full-card scan visibly includes the Lawson logo and XY-P footer, matching the checklist print.",
    },
    "No. 305": {
        "name": "Psychic Energy",
        "provider": "hareruya2",
        "url": "https://omiya.hareruya2.com/cdn/shop/files/wsC8LuelTv1XAGDqX6hnc7GmP3YGQSxDo294dZJ0.jpg?v=1756444625&width=1445",
        "page": "https://omiya.hareruya2.com/products/30222",
        "basis": "Hareruya2 listing is titled Lawson XY-P Psychic Energy. The 864x1212 full-card scan visibly includes the Lawson logo and XY-P footer, matching the checklist print.",
    },
    "No. 309": {
        "name": "Fairy Energy",
        "provider": "hareruya2",
        "url": "https://omiya.hareruya2.com/cdn/shop/files/INZYZROv9kLxZE7piCcUifx9rw0Wz3lI6ZbKGXgV.webp?v=1756444514&width=1946",
        "page": "https://omiya.hareruya2.com/products/30226",
        "basis": "Hareruya2 listing is titled Lawson XY-P Fairy Energy. The 1477x2077 full-card scan visibly includes the Lawson logo and XY-P footer, matching the checklist print.",
    },
    "No. 404": {
        "name": "M Mewtwo-EX",
        "provider": "pokellector",
        "url": "https://den-cards.pokellector.com/141/M-Mewtwo-X-Jumbo.XYP.0.png",
        "page": "https://jp.pokellector.com/card/11878/M-Mewtwo-X-Jumbo-XY-Promos-XYP-XY-P0",
        "basis": "Pokellector identifies the XY-P jumbo as the Blue Impact M Mewtwo X printing; the 230 HP, Vanishing Strike attack, artwork, and XY-P footer match checklist No. 404.",
    },
    "No. 405": {
        "name": "M Mewtwo-EX",
        "provider": "pokellector",
        "url": "https://den-cards.pokellector.com/141/M-Mewtwo-Y-Jumbo.XYP.0.png",
        "page": "https://jp.pokellector.com/card/11879/M-Mewtwo-Y-Jumbo-XY-Promos-XYP-XY-P0",
        "basis": "Pokellector identifies the XY-P jumbo as the Red Flash M Mewtwo Y printing; the 210 HP, Psychic Infinity attack, artwork, and XY-P footer match checklist No. 405.",
    },
    "No. 314": {
        "name": "Tierno",
        "provider": "pokemon_card_official",
        "url": "https://www.pokemon-card.com/assets/images/card_images/large/XYP/030228_T_TEIERUNO.jpg",
        "page": "https://www.pokemon-card.com/card-search/details.php/card/30228",
        "basis": "Official Japanese card database identifies the XY-P Tierno card and its Battle Festa 2013 stamp; the target checklist image has the same stamp and artwork.",
    },
    "No. 347": {
        "name": "Pikachu",
        "provider": "pokepedia",
        "url": "https://www.pokepedia.fr/images/1/12/Carte_XY_Puromo_K%C4%81do_NN49.png",
        "page": "https://www.pokepedia.fr/ピカチュウ_(XYプロモカード_Toys_%22R%22_Us)",
        "basis": "Japanese XY-P Toys 'R' Us Pikachu printing; illustration, Toys 'R' Us mark, and printed card details visually match the target checklist image.",
    },
    "No. 398": {
        "name": "Empoleon BREAK",
        "provider": "cardotaku",
        "url": "https://cardotaku.com/cdn/shop/products/Empoleon-BREAK.XYP.0_1.webp?v=1680152054&width=2048",
        "page": "https://cardotaku.com/en-fr/products/pokemon-card-game-promo-xy-p-empoleon-2015-battle-festival",
        "basis": "Japanese XY-P Empoleon BREAK from Battle Festival 2015; event stamp, illustration, and card text visually match the target checklist image.",
    },
    "No. 408": {
        "name": "Crobat BREAK",
        "provider": "the_card_collector_uk",
        "url": "https://www.thecardcollector-uk.com/cdn/shop/products/xypcrobatbreakpokemoncardgym_1024x.jpg?v=1578933066",
        "page": "https://www.thecardcollector-uk.com/products/crobat-break-pokemon-card-gym-logo-crobat-break-battle-top-3-prize-holo",
        "basis": "Japanese XY-P Crobat BREAK with Pokémon Card Gym logo; logo placement, illustration, and card text visually match the target checklist image.",
    },
    "No. 409": {
        "name": "Crobat BREAK",
        "provider": "hareruya2",
        "url": "https://omiya.hareruya2.com/cdn/shop/files/zVycrlh6ZoQLn5gppHW1fSG0EByu61IWYbwV2pgD.jpg?v=1756447082&width=1445",
        "page": "https://omiya.hareruya2.com/products/32141",
        "basis": "Hareruya2 exact-title listing identifies the Kamex Mega Battle XY-P Crobat BREAK. The 745x1039 full-card photo visibly includes the Kamex Mega Battle event mark and XY-P footer, matching checklist No. 409.",
    },
    "No. 427": {
        "name": "Volcanion-EX",
        "provider": "mercari",
        "url": "https://static.mercdn.net/item/detail/orig/photos/m74034384124_3.jpg?1782374067",
        "page": "https://jp.mercari.com/item/m74034384124",
        "basis": "Mercari seller photo shows the Volcanion-EX jumbo from the Special Jumbo Card Pack. The 1080x1080 photo presents the full card with its XY-P footer, jumbo proportions, 180 HP, Steam Up, and Volcanic Heat text, matching checklist No. 427.",
    },
}


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.read()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--numbers", nargs="+", help="Only acquire the listed printed numbers (for example: 303).")
    args = parser.parse_args()
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    existing = json.loads(OUTPUT.read_text()).get("records", []) if OUTPUT.exists() else []
    by_number = {record.get("printed_number"): record for record in existing}
    selected = {number: source for number, source in SOURCES.items()
                if not args.numbers or number.removeprefix("No. ") in args.numbers}
    for number, source in selected.items():
        data = fetch(source["url"])
        extension, width, height = image_info(data)
        record: dict[str, object] = {
            "group_id": GROUP_ID,
            "printed_number": number,
            "checklist_card_name": source["name"],
            "source_provider": source["provider"],
            "source_page_url": source["page"],
            "source_image_url": source["url"],
            "checklist_match": False,
            "image_width": width,
            "image_height": height,
            "image_bytes": len(data),
            "image_sha256": hashlib.sha256(data).hexdigest(),
        }
        if extension not in {"jpg", "png", "webp"} or width < 500 or height < 700:
            record.update({"status": "rejected_source_image_below_minimum_resolution", "rejection_reason": "Portrait image dimensions after orientation must be at least 500x700."})
            by_number[number] = record
            continue
        path = IMAGE_DIR / f"ja-ref-703_{number.removeprefix('No. ')}_{source['provider']}.{extension}"
        path.write_bytes(data)
        record.update({
            "checklist_match": True,
            "status": "downloaded_exact_variant_high_resolution_image",
            "image_file": path.as_posix(),
            "association_basis": source["basis"],
            "match_method": "visual_print_variant_match_supported_by_source_page",
        })
        by_number[number] = record
    records = list(by_number.values())
    OUTPUT.write_text(json.dumps({"group_id": GROUP_ID, "records": records}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"records": len(records), "acquired": sum(bool(r["checklist_match"]) for r in records), "rejected": sum(r["status"].startswith("rejected") for r in records), "manifest": OUTPUT.as_posix()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
