"""Acquire exact-number/name images from a TCG Stats Japanese set page."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import time
import urllib.request
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


def extract_cards(page: str) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    for block in re.findall(r'<a\b[^>]*class="bg-paper-2 block[^>]*>.*?</a>', page, re.I | re.S):
        image = re.search(r'<img\b[^>]*\bsrc="([^"]+)"[^>]*\balt="([^"]*)"', block, re.I)
        if not image:
            continue
        name = html.unescape(image.group(2)).strip()
        text = html.unescape(re.sub(r"<[^>]+>", " ", block))
        number = re.search(rf"{re.escape(name)}\s*#\s*(\d+)\b", text, re.I)
        cards.append({
            "source_list_name": name,
            "source_list_number": number.group(1) if number else "",
            "source_image_url": html.unescape(image.group(1)),
        })
    return cards


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--set-label", required=True)
    parser.add_argument("--page-url", required=True)
    parser.add_argument("--output-name", required=True)
    parser.add_argument("--match-unique-name", action="store_true", help="Match only names unique in both the exact source set and checklist group")
    args = parser.parse_args()

    page = get(args.page_url, "https://www.tcgstats.com/").decode("utf-8", "replace")
    cards = extract_cards(page)
    if not cards:
        raise RuntimeError("No set card images found on the TCG Stats page")

    coverage_path = REVIEW / "image-coverage-reconciliation-20261030.csv"
    with coverage_path.open(encoding="utf-8-sig", newline="") as handle:
        coverage = list(csv.DictReader(handle))
    missing = [row for row in coverage if row["group_id"] == args.group_id and row["image_status"] == "missing_image_file"]
    group_rows = [row for row in coverage if row["group_id"] == args.group_id]

    by_number_name: dict[tuple[str, str], dict[str, dict[str, str]]] = {}
    by_name: dict[str, dict[str, dict[str, str]]] = {}
    for card in cards:
        identity = (card["source_list_number"], norm(card["source_list_name"]))
        by_number_name.setdefault(identity, {})[card["source_image_url"]] = card
        by_name.setdefault(norm(card["source_list_name"]), {})[card["source_image_url"]] = card

    target_name_counts: dict[str, int] = {}
    for row in group_rows:
        name = norm(row["card_name"])
        target_name_counts[name] = target_name_counts.get(name, 0) + 1

    targets: list[tuple[dict[str, str], dict[str, str], str]] = []
    for row in missing:
        name = norm(row["card_name"])
        number_match = re.match(r"\s*(\d+)", row["printed_number"])
        if number_match:
            candidates = by_number_name.get((str(int(number_match.group(1))), name), {})
            if len(candidates) == 1:
                targets.append((row, next(iter(candidates.values())), "printed_number_and_name"))
        elif name and (target_name_counts[name] == 1 or args.match_unique_name):
            candidates = by_name.get(name, {})
            if len(candidates) == 1 and (not args.match_unique_name or target_name_counts[name] == 1):
                card = next(iter(candidates.values()))
                if not card["source_list_number"] or args.match_unique_name:
                    targets.append((row, card, "unique_name"))

    output = REVIEW / args.output_name
    previous = json.loads(output.read_text()).get("records", []) if output.exists() else []
    target_keys = {(row["printed_number"], row["card_name"]) for row, _, _ in targets}
    records = [r for r in previous if (r.get("printed_number", ""), r.get("checklist_card_name", "")) not in target_keys]
    image_root = ROOT / "images" / "tcgstats" / args.group_id
    image_root.mkdir(parents=True, exist_ok=True)

    for row, card, method in targets:
        label = card["source_list_number"] or re.sub(r"[^a-z0-9]+", "_", norm(row["card_name"]))
        dest = image_root / f"{args.group_id}_{label}_{norm(row['card_name'])}"
        try:
            content = get(card["source_image_url"], args.page_url)
            ext, width, height = image_helpers.image_info(content)
            if width < 200 or height < 300:
                raise ValueError(f"Image too small: {width}x{height}")
            dest = dest.with_suffix(".png" if ext == "png" else ".jpg")
            if not dest.exists():
                dest.write_bytes(content)
            records.append({
                "group_id": args.group_id,
                "printed_number": row["printed_number"],
                "checklist_card_name": row["card_name"],
                "source_list_number": card["source_list_number"],
                "source_list_name": card["source_list_name"],
                "source_image_url": card["source_image_url"],
                "source_list_url": args.page_url,
                "checklist_match": True,
                "image_file": str(dest),
                "image_bytes": len(content),
                "image_width": width,
                "image_height": height,
                "image_sha256": hashlib.sha256(content).hexdigest(),
                "status": "downloaded_or_reused_exact_set_image",
                "match_method": method,
                "association_basis": (
                    f"TCG Stats exact {args.set_label} card number and exact English name"
                    if method == "printed_number_and_name" else
                    f"TCG Stats exact {args.set_label} page with a unique exact name for an unnumbered checklist entry"
                ),
            })
        except Exception as error:
            records.append({
                "group_id": args.group_id,
                "printed_number": row["printed_number"],
                "checklist_card_name": row["card_name"],
                "source_list_number": card["source_list_number"],
                "source_list_name": card["source_list_name"],
                "source_image_url": card["source_image_url"],
                "source_list_url": args.page_url,
                "checklist_match": False,
                "status": "failed",
                "error": str(error)[:400],
            })
        time.sleep(0.1)

    output.write_text(json.dumps({"source_list_url": args.page_url, "group_id": args.group_id, "records": records}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "group_id": args.group_id,
        "source_cards": len(cards),
        "exact_targets": len(targets),
        "acquired": sum(r.get("checklist_match", False) for r in records),
        "failed": sum(r.get("status") == "failed" for r in records),
    }))


if __name__ == "__main__":
    main()
