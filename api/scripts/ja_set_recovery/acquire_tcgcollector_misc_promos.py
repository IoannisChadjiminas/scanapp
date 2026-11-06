"""Acquire exact-card images from the source checklist for Japanese Miscellaneous Promos."""
from __future__ import annotations

import csv
import argparse
import hashlib
import html
import json
import re
import time
import urllib.request
from pathlib import Path

from acquire_official_group_images import image_info

ROOT = Path("data/catalogue-gaps/ja-set-recovery-20261029-v3")
REVIEW = ROOT / "review"
GROUP_ID = "ja-ref-1157"
SET_URL = "https://www.tcgcollector.com/sets/11410/miscellaneous-promos"
OUTPUT = REVIEW / "tcgcollector-ja-ref-1157-misc-promos-image-acquisition-20261030.json"


def get(url: str, referer: str) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; ScanappImageRecovery/1.0)",
        "Referer": referer,
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--limit", type=int, default=50, help="Maximum new downloads in this resumable pass")
    args = cli.parse_args()
    page = get(SET_URL, SET_URL).decode("utf-8", "replace")
    anchors = list(re.finditer(r'<a\b[^>]*href="(/cards/\d+/[^\"]+)"[^>]*>', page, re.I))
    cards: dict[str, dict[str, str]] = {}
    for index, match in enumerate(anchors):
        block = page[match.start(): anchors[index + 1].start() if index + 1 < len(anchors) else len(page)]
        card_url = "https://www.tcgcollector.com" + html.unescape(match.group(1))
        title_match = re.search(r'\btitle="([^"]*Miscellaneous Promos No\. \d{3}[^"]*)"', block)
        srcset_match = re.search(r'\bsrcset="([^"]+)"', block)
        if not title_match or not srcset_match:
            continue
        title = html.unescape(title_match.group(1))
        number_match = re.search(r'Miscellaneous Promos No\. (\d{3})', title)
        if not number_match:
            continue
        name = title.split(" (Miscellaneous Promos No.", 1)[0]
        choices = []
        for entry in srcset_match.group(1).split(","):
            part = entry.strip().split()
            if len(part) == 2 and part[1].endswith("w"):
                choices.append((int(part[1][:-1]), part[0]))
        if choices:
            cards[number_match.group(1)] = {
                "card_name": name,
                "card_url": card_url,
                "image_url": max(choices)[1],
            }

    with (REVIEW / "image-coverage-reconciliation-20261030.csv").open(encoding="utf-8-sig", newline="") as handle:
        coverage = list(csv.DictReader(handle))
    targets = [row for row in coverage if row["group_id"] == GROUP_ID and row["image_status"] == "missing_image_file"]
    records: list[dict[str, object]] = json.loads(OUTPUT.read_text()).get("records", []) if OUTPUT.exists() else []
    attempted = {
        (r.get("printed_number", ""), r.get("checklist_card_name", ""))
        for r in records if r.get("status") != "failed"
    }
    image_dir = ROOT / "images" / "tcgcollector" / GROUP_ID
    image_dir.mkdir(parents=True, exist_ok=True)
    new_downloads = 0
    for row in targets:
        if (row["printed_number"], row["card_name"]) in attempted:
            continue
        number_match = re.search(r"(\d{3})$", row["printed_number"])
        if not number_match:
            continue
        number = number_match.group(1)
        source = cards.get(number)
        if not source or source["card_name"].casefold() != row["card_name"].casefold():
            continue
        ext_from_url = Path(source["image_url"].split("?", 1)[0]).suffix.lstrip(".") or "jpg"
        image_path = image_dir / f"{GROUP_ID}_{number}_tcgcollector.{ext_from_url}"
        try:
            if image_path.is_file():
                data = image_path.read_bytes()
            else:
                if new_downloads >= args.limit:
                    continue
                data = get(source["image_url"], source["card_url"])
                new_downloads += 1
            extension, width, height = image_info(data)
        except Exception as error:
            records.append({
                "group_id": GROUP_ID,
                "printed_number": row["printed_number"],
                "checklist_card_name": row["card_name"],
                "source_card_name": source["card_name"],
                "source_card_url": source["card_url"],
                "source_image_url": source["image_url"],
                "source_list_url": SET_URL,
                "checklist_match": False,
                "status": "failed",
                "error": str(error)[:400],
            })
            if len(records) % 10 == 0:
                OUTPUT.write_text(json.dumps({"source_list_url": SET_URL, "group_id": GROUP_ID, "source_card_records": len(cards), "records": records}, ensure_ascii=False, indent=2) + "\n")
            continue
        if extension not in {"jpg", "png", "webp"} or width < 500 or height < 700:
            records.append({
                "group_id": GROUP_ID,
                "printed_number": row["printed_number"],
                "checklist_card_name": row["card_name"],
                "source_card_name": source["card_name"],
                "source_card_url": source["card_url"],
                "source_image_url": source["image_url"],
                "source_list_url": SET_URL,
                "checklist_match": False,
                "status": "rejected_source_image_below_minimum_resolution",
                "image_width": width,
                "image_height": height,
            })
            attempted.add((row["printed_number"], row["card_name"]))
            if len(records) % 10 == 0:
                OUTPUT.write_text(json.dumps({"source_list_url": SET_URL, "group_id": GROUP_ID, "source_card_records": len(cards), "records": records}, ensure_ascii=False, indent=2) + "\n")
            continue
        if not image_path.is_file():
            image_path = image_dir / f"{GROUP_ID}_{number}_tcgcollector.{extension}"
            image_path.write_bytes(data)
        records.append({
            "group_id": GROUP_ID,
            "printed_number": row["printed_number"],
            "checklist_card_name": row["card_name"],
            "source_card_name": source["card_name"],
            "source_card_url": source["card_url"],
            "source_image_url": source["image_url"],
            "source_list_url": SET_URL,
            "checklist_match": True,
            "image_file": image_path.as_posix(),
            "image_bytes": len(data),
            "image_width": width,
            "image_height": height,
            "image_sha256": hashlib.sha256(data).hexdigest(),
            "status": "downloaded_or_reused_exact_source_checklist_card_image",
            "association_basis": "TCG Collector is the checklist source; exact card number and card name match its direct Japanese card record",
            "match_method": "exact_checklist_number_and_name",
        })
        attempted.add((row["printed_number"], row["card_name"]))
        if len(records) % 10 == 0:
            OUTPUT.write_text(json.dumps({"source_list_url": SET_URL, "group_id": GROUP_ID, "source_card_records": len(cards), "records": records}, ensure_ascii=False, indent=2) + "\n")
        if new_downloads and new_downloads % 5 == 0:
            time.sleep(0.1)

    OUTPUT.write_text(json.dumps({"source_list_url": SET_URL, "group_id": GROUP_ID, "source_card_records": len(cards), "records": records}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"source_cards_with_images": len(cards), "missing_targets": len(targets), "acquired": sum(r.get("checklist_match", False) for r in records), "new_downloads": new_downloads, "manifest": str(OUTPUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
