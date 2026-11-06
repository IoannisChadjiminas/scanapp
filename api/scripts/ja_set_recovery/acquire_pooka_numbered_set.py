"""Acquire a Japanese Pooka set page's number-labelled card images by checklist number."""
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


def extract_cards(page: str, set_slug: str, set_label: str) -> dict[int, dict[str, str]]:
    cards: dict[int, dict[str, str]] = {}
    for tag in re.findall(r"<img\b[^>]*>", page, re.I):
        src = re.search(r'\bsrc="([^"]+)"', tag)
        alt = re.search(r'\balt="([^"]*)"', tag)
        if not src or not alt:
            continue
        source_url = html.unescape(src.group(1))
        label = html.unescape(alt.group(1))
        match = re.search(rf"/card/{re.escape(set_slug)}-(\d+)\.png\?size=(?:small|default)$", source_url)
        label_match = re.search(rf"^(.*?)\s+(\d{{1,3}}),\s*{re.escape(set_label)}$", label)
        if not match or not label_match:
            continue
        asset_number = int(match.group(1))
        label_number = int(label_match.group(2))
        if asset_number != label_number:
            continue
        cards[asset_number] = {
            "source_list_name": label_match.group(1),
            "source_list_label": label,
            "source_image_url": f"https://cdn.pooka.app/card/{set_slug}-{asset_number}.png?size=large",
        }
    return cards


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def matching_name(value: str, ignore_level_suffix: bool) -> str:
    if ignore_level_suffix:
        value = re.sub(r"\s+Lv\.?\s*\d+\s*$", "", value, flags=re.I)
    return normalize_name(value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--set-slug", required=True)
    parser.add_argument("--set-label", required=True)
    parser.add_argument("--page-url", required=True)
    parser.add_argument("--output-name", required=True)
    parser.add_argument("--candidate-code", default="")
    parser.add_argument("--match-by-name", action="store_true")
    parser.add_argument("--match-number-and-name", action="store_true")
    parser.add_argument("--match-number-only", action="store_true", help="Use a unique printed number within an explicitly identified matching set")
    parser.add_argument("--also-unique-name", action="store_true")
    parser.add_argument("--ignore-level-suffix", action="store_true", help="Ignore a trailing card level such as 'Lv.56' when matching names")
    args = parser.parse_args()
    audit_path = REVIEW / args.output_name
    page = get(args.page_url, "https://pooka.app/").decode("utf-8", "replace")
    cards = extract_cards(page, args.set_slug, args.set_label)
    if not cards:
        raise RuntimeError(f"No number-labelled images found for {args.set_slug}")

    coverage = list(csv.DictReader((REVIEW / "image-coverage-reconciliation-20261030.csv").open(encoding="utf-8")))
    targets: list[tuple[int, dict[str, str], str]] = []
    missing_rows = [row for row in coverage if row["group_id"] == args.group_id and row["image_status"] == "missing_image_file"]
    if args.match_by_name:
        source_by_name: dict[str, list[tuple[int, dict[str, str]]]] = {}
        for number, source in cards.items():
            source_by_name.setdefault(matching_name(source["source_list_name"], args.ignore_level_suffix), []).append((number, source))
        target_name_counts: dict[str, int] = {}
        for row in missing_rows:
            name = matching_name(row["card_name"], args.ignore_level_suffix)
            target_name_counts[name] = target_name_counts.get(name, 0) + 1
        for row in missing_rows:
            name = matching_name(row["card_name"], args.ignore_level_suffix)
            source_matches = source_by_name.get(name, [])
            if name and target_name_counts.get(name) == 1 and len(source_matches) == 1:
                number, source = source_matches[0]
                targets.append((number, row, source["source_list_name"]))
    elif args.match_number_and_name or args.match_number_only:
        matched_rows: set[tuple[str, str, str]] = set()
        for row in missing_rows:
            number_match = re.match(r"\s*(\d+)", row["printed_number"])
            if not number_match:
                continue
            number = int(number_match.group(1))
            source = cards.get(number)
            if source and (args.match_number_only or (
                matching_name(row["card_name"], args.ignore_level_suffix)
                and matching_name(row["card_name"], args.ignore_level_suffix) == matching_name(source["source_list_name"], args.ignore_level_suffix)
            )):
                targets.append((number, row, source["source_list_name"]))
                matched_rows.add((row["group_id"], row["printed_number"], row["card_name"]))
        if args.also_unique_name:
            source_by_name: dict[str, list[tuple[int, dict[str, str]]]] = {}
            for number, source in cards.items():
                source_by_name.setdefault(matching_name(source["source_list_name"], args.ignore_level_suffix), []).append((number, source))
            target_name_counts: dict[str, int] = {}
            for row in missing_rows:
                name = matching_name(row["card_name"], args.ignore_level_suffix)
                target_name_counts[name] = target_name_counts.get(name, 0) + 1
            for row in missing_rows:
                key = (row["group_id"], row["printed_number"], row["card_name"])
                name = matching_name(row["card_name"], args.ignore_level_suffix)
                source_matches = source_by_name.get(name, [])
                if key not in matched_rows and name and target_name_counts[name] == 1 and len(source_matches) == 1:
                    number, source = source_matches[0]
                    targets.append((number, row, source["source_list_name"]))
                    matched_rows.add(key)
    else:
        for row in missing_rows:
            candidate_name = ""
            candidate_number = ""
            if args.candidate_code:
                expression = rf"([^;]+?)\s*\({re.escape(args.candidate_code)}\s*(\d+)\)"
                candidates = re.findall(expression, row.get("cardmarket_candidate_names", ""), re.I)
                if len(candidates) != 1:
                    continue
                candidate_name, candidate_number = candidates[0]
                if normalize_name(row["card_name"]) != normalize_name(candidate_name):
                    continue
                if normalize_name(candidate_name) != normalize_name(cards.get(int(candidate_number), {}).get("source_list_name", "")):
                    continue
            number_text = candidate_number or (re.match(r"\s*(\d+)", row["printed_number"]).group(1) if re.match(r"\s*(\d+)", row["printed_number"]) else "")
            if not number_text:
                continue
            number = int(number_text)
            if number not in cards:
                continue
            if candidate_number and row["printed_number"].strip().isdigit() and int(row["printed_number"]) != number:
                continue
            targets.append((number, row, candidate_name or cards[number]["source_list_name"]))
    source_counts: dict[int, int] = {}
    for number, _, _ in targets:
        source_counts[number] = source_counts.get(number, 0) + 1
    targets = [item for item in targets if source_counts[item[0]] == 1]

    dest_root = ROOT / "images" / "pooka" / args.group_id
    dest_root.mkdir(parents=True, exist_ok=True)
    previous = json.loads(audit_path.read_text()).get("records", []) if audit_path.exists() else []
    previous_by_number = {int(r["source_list_number"]): r for r in previous if str(r.get("source_list_number", "")).isdigit()}
    target_numbers = {number for number, _, _ in targets}
    records = [r for r in previous if int(r.get("source_list_number", "0")) not in target_numbers]
    for number, row, candidate_name in sorted(targets, key=lambda item: item[0]):
        source = cards.get(number)
        if not source:
            continue
        cached = previous_by_number.get(number, {})
        dest = Path(cached.get("image_file", "")) if cached.get("image_file") else dest_root / f"{args.group_id}_{number:03d}_{args.set_slug}.png"
        try:
            content = dest.read_bytes() if dest.is_file() else get(source["source_image_url"], args.page_url)
            ext, width, height = image_helpers.image_info(content)
            if ext != "png" or width < 300 or height < 400:
                raise ValueError(f"Unexpected image type or small image: {ext} {width}x{height}")
            if not dest.is_file():
                dest.write_bytes(content)
            records.append({
                "group_id": args.group_id,
                "printed_number": row["printed_number"],
                "checklist_card_name": row["card_name"],
                "source_list_number": str(number),
                "candidate_card_name": candidate_name,
                **source,
                "source_list_url": args.page_url,
                "checklist_match": True,
                "image_file": str(dest),
                "image_bytes": len(content),
                "image_width": width,
                "image_height": height,
                "image_sha256": hashlib.sha256(content).hexdigest(),
                "status": "downloaded_or_reused_number_matched_image",
                "association_basis": (
                    f"Pooka {args.set_label} set membership and exact card number/name match after removing a trailing card level suffix"
                    if args.ignore_level_suffix else
                    f"Pooka {args.set_label} set membership and unique exact printed number match"
                    if args.match_number_only else
                    f"Pooka {args.set_label} set list and checklist have a unique exact English card-name match"
                    if args.match_by_name else
                    f"Pooka {args.set_label} set membership and exact number/name or unique exact-name match"
                    if args.match_number_and_name else
                    f"Pooka {args.set_label} list and image number match the unique exact-name Cardmarket candidate"
                    if args.candidate_code else
                    f"Pooka {args.set_label} set membership and exact number/name or unique exact-name match"
                ),
            })
        except Exception as error:
            records.append({
                "group_id": args.group_id,
                "printed_number": row["printed_number"],
                "checklist_card_name": row["card_name"],
                "source_list_number": str(number),
                "candidate_card_name": candidate_name,
                **source,
                "source_list_url": args.page_url,
                "checklist_match": False,
                "status": "failed",
                "error": str(error)[:400],
            })
        if number % 20 == 0:
            audit_path.write_text(json.dumps({"source_list_url": args.page_url, "group_id": args.group_id, "records": records}, ensure_ascii=False, indent=2) + "\n")
            print(f"{args.group_id}: number {number}; acquired {sum(r.get('checklist_match', False) for r in records)}", flush=True)
        time.sleep(0.1)
    audit_path.write_text(json.dumps({"source_list_url": args.page_url, "group_id": args.group_id, "records": records}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"group_id": args.group_id, "list_numbers": len(cards), "missing_targets": len(targets), "acquired": sum(r.get("checklist_match", False) for r in records), "failed": sum(r.get("status") == "failed" for r in records)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
