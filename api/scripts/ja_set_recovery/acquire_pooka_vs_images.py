"""Acquire numbered Pokémon VS card images from Pooka's Japanese card set."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import time
import urllib.request
from pathlib import Path

import acquire_official_group_images as image_helpers

ROOT = Path("data/catalogue-gaps/ja-set-recovery-20261029-v3")
REVIEW = ROOT / "review"
GROUP_ID = "ja-ref-1020"
PAGE_URL = "https://pooka.app/list/set/prices/ja-pok-mon-vs/Pok%C3%A9mon%20VS"
AUDIT = REVIEW / "pooka-vs-image-acquisition-20261030.json"
DEST = ROOT / "images" / "pooka" / GROUP_ID


def get(url: str, referer: str) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; ScanappImageRecovery/1.0)",
        "Referer": referer,
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def main() -> None:
    # Pooka lists numbered cards as card URLs and CDN assets with the same
    # number. Number 006 was visually checked: the downloaded face reads 006/141.
    page = get(PAGE_URL, "https://pooka.app/").decode("utf-8", "replace")
    names_by_number = {
        int(number): name
        for number, name in re.findall(
            r'<a href="/card/ja-pok-mon-vs-(\d+)/[^"]+"><b>(.*?)</b></a>\s*<span class="muted num">#\d+</span>',
            page,
            re.S,
        )
    }
    if not names_by_number or names_by_number.get(1) is None:
        raise RuntimeError("Could not parse Pooka's numbered Pokémon VS card list")

    coverage = list(csv.DictReader((REVIEW / "image-coverage-reconciliation-20261030.csv").open(encoding="utf-8")))
    targets = {
        int(row["printed_number"]): row
        for row in coverage
        if row["group_id"] == GROUP_ID and row["image_status"] == "missing_image_file"
        and row["printed_number"].isdigit() and 1 <= int(row["printed_number"]) <= 141
    }
    if sorted(targets) != list(range(1, 142)):
        raise RuntimeError(f"Expected checklist numbers 001-141; found {len(targets)} targets")

    DEST.mkdir(parents=True, exist_ok=True)
    old = json.loads(AUDIT.read_text()) if AUDIT.exists() else {"records": []}
    previous = {int(record["printed_number"]): record for record in old.get("records", [])}
    records = []
    for number, row in sorted(targets.items()):
        url = f"https://cdn.pooka.app/card/ja-pok-mon-vs-{number}.png?size=large"
        dest = DEST / f"{GROUP_ID}_{number:03d}_VS.png"
        try:
            content = dest.read_bytes() if dest.is_file() else get(url, PAGE_URL)
            ext, width, height = image_helpers.image_info(content)
            if ext != "png" or width < 300 or height < 400:
                raise ValueError(f"Unexpected image type or small image: {ext} {width}x{height}")
            if not dest.is_file():
                dest.write_bytes(content)
            records.append({
                "group_id": GROUP_ID,
                "printed_number": row["printed_number"],
                "checklist_card_name": row["card_name"],
                "source_list_name": names_by_number.get(number, ""),
                "source_list_url": PAGE_URL,
                "source_image_url": url,
                "checklist_match": True,
                "image_file": str(dest),
                "image_bytes": len(content),
                "image_width": width,
                "image_height": height,
                "image_sha256": hashlib.sha256(content).hexdigest(),
                "status": "downloaded_or_reused_number_matched_image",
                "association_basis": "Pooka card asset/list number matches checklist number; sample asset 006 was visually confirmed to show printed number 006/141",
            })
        except Exception as error:
            records.append({
                "group_id": GROUP_ID,
                "printed_number": row["printed_number"],
                "checklist_card_name": row["card_name"],
                "source_list_name": names_by_number.get(number, ""),
                "source_list_url": PAGE_URL,
                "source_image_url": url,
                "checklist_match": False,
                "status": "failed",
                "error": str(error)[:400],
            })
        if number % 10 == 0:
            AUDIT.write_text(json.dumps({"source_list_url": PAGE_URL, "group_id": GROUP_ID, "records": records}, ensure_ascii=False, indent=2) + "\n")
            print(f"VS: {number}/141; acquired {sum(record.get('checklist_match', False) for record in records)}", flush=True)
        time.sleep(0.1)
    AUDIT.write_text(json.dumps({"source_list_url": PAGE_URL, "group_id": GROUP_ID, "records": records}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"target_rows": len(targets), "acquired": sum(record.get("checklist_match", False) for record in records), "failed": sum(record.get("status") == "failed" for record in records)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
