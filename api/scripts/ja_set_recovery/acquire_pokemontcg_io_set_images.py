"""Acquire exact-number/name card images from the PokémonTCG.io image CDN."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import time
import urllib.request
import urllib.parse
from pathlib import Path

import acquire_official_group_images as image_helpers

ROOT = Path("data/catalogue-gaps/ja-set-recovery-20261029-v3")
REVIEW = ROOT / "review"


def get(url: str, referer: str) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; ScanappImageRecovery/1.0)",
        "Referer": referer,
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def extract_cards(page: str, set_code: str, set_label: str) -> dict[int, dict[str, str]]:
    cards: dict[int, dict[str, str]] = {}
    for tag in re.findall(r"<img\b[^>]*>", page, re.I):
        alt = re.search(r'\balt="([^"]+)"', tag, re.I)
        srcset = re.search(r'\bsrcSet="([^"]+)"', tag, re.I)
        if not alt or not srcset:
            continue
        alt_text = html.unescape(alt.group(1)).strip()
        urls = urllib.parse.unquote(html.unescape(srcset.group(1)))
        image = re.search(rf"https://images\.pokemontcg\.io/{re.escape(set_code)}/(\d+)\.png", urls)
        if not image or set_label.lower() not in alt_text.lower():
            continue
        number = int(image.group(1))
        name_match = re.match(r"^(.*?)\s+\d+\s*/\s*\d+\s+—", alt_text)
        if not name_match:
            continue
        cards[number] = {
            "source_list_name": name_match.group(1).strip(),
            "source_image_url": f"https://images.pokemontcg.io/{set_code}/{number}_hires.png",
            "source_list_url": f"https://bynx.gg/set/{set_code}",
        }
    return cards


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--set-code", required=True)
    parser.add_argument("--set-label", required=True)
    parser.add_argument("--page-url", required=True)
    parser.add_argument("--output-name", required=True)
    args = parser.parse_args()

    page = get(args.page_url, "https://bynx.gg/").decode("utf-8", "replace")
    cards = extract_cards(page, args.set_code, args.set_label)
    if not cards:
        raise RuntimeError(f"No numbered image entries found for {args.set_code}")

    coverage_path = REVIEW / "image-coverage-reconciliation-20261030.csv"
    with coverage_path.open(encoding="utf-8-sig", newline="") as handle:
        coverage = list(csv.DictReader(handle))
    missing = [row for row in coverage if row["group_id"] == args.group_id and row["image_status"] == "missing_image_file"]
    targets: list[tuple[dict[str, str], dict[str, str]]] = []
    target_numbers: dict[int, int] = {}
    for row in missing:
        match = re.match(r"\s*(\d+)", row["printed_number"])
        if match:
            number = int(match.group(1))
            target_numbers[number] = target_numbers.get(number, 0) + 1
    for row in missing:
        match = re.match(r"\s*(\d+)", row["printed_number"])
        if not match:
            continue
        number = int(match.group(1))
        source = cards.get(number)
        if source and target_numbers[number] == 1 and norm(source["source_list_name"]) == norm(row["card_name"]):
            targets.append((row, source))

    output = REVIEW / args.output_name
    previous = json.loads(output.read_text()).get("records", []) if output.exists() else []
    target_keys = {(row["printed_number"], row["card_name"]) for row, _ in targets}
    records = [r for r in previous if (r.get("printed_number", ""), r.get("checklist_card_name", "")) not in target_keys]
    image_root = ROOT / "images" / "pokemon-tcg-io" / args.group_id
    image_root.mkdir(parents=True, exist_ok=True)
    for row, source in targets:
        number = int(re.match(r"\s*(\d+)", row["printed_number"]).group(1))
        dest = image_root / f"{args.group_id}_{number:03d}_{args.set_code}.png"
        try:
            content = get(source["source_image_url"], args.page_url)
            ext, width, height = image_helpers.image_info(content)
            if ext != "png" or width < 500 or height < 700:
                raise ValueError(f"Unexpected image type or dimensions: {ext} {width}x{height}")
            if not dest.exists():
                dest.write_bytes(content)
            records.append({
                "group_id": args.group_id,
                "printed_number": row["printed_number"],
                "checklist_card_name": row["card_name"],
                "source_list_number": str(number),
                "source_list_name": source["source_list_name"],
                "source_image_url": source["source_image_url"],
                "source_list_url": source["source_list_url"],
                "checklist_match": True,
                "image_file": str(dest),
                "image_bytes": len(content),
                "image_width": width,
                "image_height": height,
                "image_sha256": hashlib.sha256(content).hexdigest(),
                "status": "downloaded_or_reused_high_resolution_exact_set_image",
                "match_method": "printed_number_and_name",
                "association_basis": f"Exact {args.set_label} set number and exact card-name match; high-resolution image from PokémonTCG.io CDN",
            })
        except Exception as error:
            records.append({
                "group_id": args.group_id,
                "printed_number": row["printed_number"],
                "checklist_card_name": row["card_name"],
                "source_list_number": str(number),
                "source_list_name": source["source_list_name"],
                "source_image_url": source["source_image_url"],
                "source_list_url": source["source_list_url"],
                "checklist_match": False,
                "status": "failed",
                "error": str(error)[:400],
            })
        time.sleep(0.1)

    output.write_text(json.dumps({"source_list_url": args.page_url, "group_id": args.group_id, "records": records}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "group_id": args.group_id,
        "source_cards": len(cards),
        "exact_number_name_targets": len(targets),
        "acquired": sum(r.get("checklist_match", False) for r in records),
        "failed": sum(r.get("status") == "failed" for r in records),
    }))


if __name__ == "__main__":
    main()
