"""Acquire exact-number images from Bynx's Japanese XY Promos card list."""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

import acquire_official_group_images as image_helpers

ROOT = Path("data/catalogue-gaps/ja-set-recovery-20261029-v3")
REVIEW = ROOT / "review"
GROUP_ID = "ja-ref-703"
SET_URL = "https://bynx.gg/set/xypj"
OUTPUT = REVIEW / "bynx-ja-ref-703-xy-promos-image-acquisition-20261030.json"


def get(url: str, referer: str) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; ScanappImageRecovery/1.0)",
        "Referer": referer,
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def main() -> None:
    page = get(SET_URL, SET_URL).decode("utf-8", "replace")
    cards: dict[int, dict[str, str]] = {}
    for block in re.findall(r"<a\b[^>]*href=\"/carta/[^\"]+\"[^>]*>.*?</a>", page, re.I | re.S):
        image = re.search(r"<img\b[^>]*\balt=\"([^\"]+)\"[^>]*\bsrcSet=\"([^\"]+)\"", block, re.I)
        if not image:
            continue
        alt = html.unescape(image.group(1)).strip()
        match = re.match(r"(.+?)\s+(\d+)\s+—\s+XY Promos \(JP\)", alt, re.I)
        if not match:
            continue
        choices = []
        for entry in html.unescape(image.group(2)).split(","):
            part = entry.strip().split()
            if len(part) != 2 or not part[1].endswith("w"):
                continue
            next_url = urllib.parse.urljoin("https://bynx.gg", part[0])
            query = urllib.parse.parse_qs(urllib.parse.urlparse(next_url).query)
            original = query.get("url", [""])[0]
            width = int(part[1][:-1])
            if original:
                choices.append((width, original))
        if choices:
            number = int(match.group(2))
            cards[number] = {"source_card_name": match.group(1), "source_image_url": max(choices)[1]}

    coverage_path = REVIEW / "image-coverage-reconciliation-20261030.csv"
    with coverage_path.open(encoding="utf-8-sig", newline="") as handle:
        coverage = list(csv.DictReader(handle))
    targets = [row for row in coverage if row["group_id"] == GROUP_ID and row["image_status"] == "missing_image_file"]
    number_counts: dict[int, int] = {}
    parsed_targets = []
    for row in targets:
        match = re.search(r"(\d+)\s*$", row["printed_number"])
        if not match:
            continue
        number = int(match.group(1))
        number_counts[number] = number_counts.get(number, 0) + 1
        parsed_targets.append((number, row))

    image_dir = ROOT / "images" / "bynx" / GROUP_ID
    image_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for number, row in parsed_targets:
        source = cards.get(number)
        if not source or number_counts[number] != 1:
            continue
        destination = image_dir / f"{GROUP_ID}_{number:03d}_bynx.jpg"
        try:
            data = destination.read_bytes() if destination.is_file() else get(source["source_image_url"], SET_URL)
            extension, width, height = image_helpers.image_info(data)
            if extension not in {"jpg", "png", "webp"} or width < 500 or height < 700:
                raise ValueError(f"Unexpected image type or dimensions: {extension} {width}x{height}")
            if not destination.is_file():
                destination = destination.with_suffix(f".{extension}")
                destination.write_bytes(data)
            records.append({
                "group_id": GROUP_ID,
                "printed_number": row["printed_number"],
                "checklist_card_name": row["card_name"],
                "source_card_name": source["source_card_name"],
                "source_card_url": SET_URL,
                "source_image_url": source["source_image_url"],
                "source_list_url": SET_URL,
                "checklist_match": True,
                "image_file": destination.as_posix(),
                "image_bytes": len(data),
                "image_width": width,
                "image_height": height,
                "image_sha256": hashlib.sha256(data).hexdigest(),
                "status": "downloaded_or_reused_exact_set_number_image",
                "association_basis": "Bynx Japanese XY Promos set listing has a unique matching printed number; image is served for that exact set entry",
                "match_method": "unique_printed_number_in_exact_set",
            })
        except Exception as error:
            records.append({
                "group_id": GROUP_ID,
                "printed_number": row["printed_number"],
                "checklist_card_name": row["card_name"],
                "source_card_name": source["source_card_name"],
                "source_image_url": source["source_image_url"],
                "source_list_url": SET_URL,
                "checklist_match": False,
                "status": "failed",
                "error": str(error)[:400],
            })
        if len(records) % 10 == 0:
            OUTPUT.write_text(json.dumps({"source_list_url": SET_URL, "group_id": GROUP_ID, "source_card_records": len(cards), "records": records}, ensure_ascii=False, indent=2) + "\n")

    OUTPUT.write_text(json.dumps({"source_list_url": SET_URL, "group_id": GROUP_ID, "source_card_records": len(cards), "records": records}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"source_cards": len(cards), "missing_targets": len(targets), "matched_targets": len(records), "acquired": sum(r.get("checklist_match", False) for r in records), "manifest": str(OUTPUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
