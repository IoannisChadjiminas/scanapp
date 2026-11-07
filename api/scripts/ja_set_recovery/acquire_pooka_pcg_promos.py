"""Acquire number-matched Japanese PCG-P promo images from Pooka's set list."""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import acquire_official_group_images as image_helpers

ROOT = Path("data/catalogue-gaps/ja-set-recovery-20261029-v3")
REVIEW = ROOT / "review"
GROUP_ID = "ja-ref-983"
PAGE_URL = "https://pooka.app/ja/list/set/cards/ja-pcg-promos/PCG%20Promos"
AUDIT = REVIEW / "pooka-pcg-promos-image-acquisition-20261030.json"
DEST = ROOT / "images" / "pooka" / GROUP_ID


def get(url: str, referer: str) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; ScanappImageRecovery/1.0)",
        "Referer": referer,
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def listed_cards(page: str) -> list[dict[str, str]]:
    # The page emits the whole set in card image elements; each alt label
    # contains its position and set name (for example, "ピジョット 73, PCG プロモカード").
    pattern = re.compile(
        r'<img\s+src="(?P<url>https://cdn\.pooka\.app/card/ja-pcg-promos-(?P<id>\d+)\.png\?size=(?:small|default))"'
        r'\s+alt="(?P<alt>[^"]+)"', re.I
    )
    cards: dict[int, dict[str, str]] = {}
    for match in pattern.finditer(page):
        number = int(match.group("id"))
        alt = html.unescape(match.group("alt"))
        label_number = re.search(r"\s(\d{1,3}),\s*PCG プロモカード$", alt)
        if not label_number or int(label_number.group(1)) != number:
            continue
        cards[number] = {
            "source_list_position": str(number),
            "source_label": alt,
            "source_card_url": f"https://pooka.app/ja/card/ja-pcg-promos-{number}",
            "source_image_url": match.group("url").split("?", 1)[0] + "?size=large",
        }
    return [cards[number] for number in sorted(cards)]


def main() -> None:
    page = get(PAGE_URL, "https://pooka.app/").decode("utf-8", "replace")
    cards = listed_cards(page)
    if len(cards) != 154 or [int(card["source_list_position"]) for card in cards] != list(range(1, 155)):
        raise RuntimeError(f"Expected 154 sequential, number-labelled cards; parsed {len(cards)}")

    coverage = list(csv.DictReader((REVIEW / "image-coverage-reconciliation-20261030.csv").open(encoding="utf-8")))
    targets = {
        int(row["printed_number"].split("/", 1)[0]): row
        for row in coverage
        if row["group_id"] == GROUP_ID and row["image_status"] == "missing_image_file"
        and row["printed_number"].split("/", 1)[0].isdigit()
    }
    DEST.mkdir(parents=True, exist_ok=True)
    old = json.loads(AUDIT.read_text()) if AUDIT.exists() else {"records": []}
    previous = {int(record["printed_number"]): record for record in old.get("records", [])}
    records = []
    for source_card in cards:
        number = int(source_card["source_list_position"])
        row = targets.get(number)
        if row is None:
            continue
        cached = previous.get(number, {})
        dest = Path(cached.get("image_file", "")) if cached.get("image_file") else DEST / f"{GROUP_ID}_{number:03d}_PCG-P.png"
        try:
            if not dest.is_file():
                content = get(source_card["source_image_url"], PAGE_URL)
                ext, width, height = image_helpers.image_info(content)
                if ext != "png" or width < 300 or height < 400:
                    raise ValueError(f"Unexpected image type or small image: {ext} {width}x{height}")
                if dest.suffix != ".png":
                    dest = dest.with_suffix(f".{ext}")
                dest.write_bytes(content)
            else:
                content = dest.read_bytes()
                ext, width, height = image_helpers.image_info(content)
            records.append({
                **source_card,
                "group_id": GROUP_ID,
                "printed_number": row["printed_number"],
                "checklist_card_name": row["card_name"],
                "checklist_match": True,
                "image_file": str(dest),
                "image_bytes": len(content),
                "image_width": width,
                "image_height": height,
                "image_sha256": hashlib.sha256(content).hexdigest(),
                "status": "downloaded_or_reused_number_matched_image",
                "association_basis": "Pooka list label number equals checklist PCG-P printed number; list contains exactly 154 sequential cards",
            })
        except Exception as error:
            records.append({
                **source_card,
                "group_id": GROUP_ID,
                "printed_number": row["printed_number"],
                "checklist_card_name": row["card_name"],
                "checklist_match": False,
                "status": "failed",
                "error": str(error)[:400],
            })
        if number % 10 == 0:
            print(f"PCG-P promos: {number}/154; acquired {sum(r.get('checklist_match', False) for r in records)}", flush=True)
            AUDIT.write_text(json.dumps({"source_page": PAGE_URL, "group_id": GROUP_ID, "records": records}, ensure_ascii=False, indent=2) + "\n")
        time.sleep(0.15)
    AUDIT.write_text(json.dumps({"source_page": PAGE_URL, "group_id": GROUP_ID, "records": records}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"target_rows": len(targets), "acquired": sum(r.get("checklist_match", False) for r in records), "failed": sum(r.get("status") == "failed" for r in records)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
