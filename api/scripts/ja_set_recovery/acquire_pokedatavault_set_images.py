"""Acquire checklist-matched images from an exact PokeDataVault Japanese set page."""
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


def extract_cards(page: str, set_slug: str) -> dict[int, dict[str, str]]:
    cards: dict[int, dict[str, str]] = {}
    for block in re.findall(r'<a\b[^>]*class="card-tile"[^>]*>.*?</a>', page, re.I | re.S):
        href = re.search(r'\bhref="([^"]+)"', block, re.I)
        image = re.search(r'<img\b[^>]*\bsrc="([^"]+)"[^>]*>', block, re.I)
        name = re.search(r'<strong>(.*?)</strong>', block, re.I | re.S)
        card_text = html.unescape(re.sub(r"<[^>]+>", " ", block))
        number = re.search(r'#\s*(\d+)\b', card_text)
        if not (href and image and name and number and set_slug.lower() in href.group(1).lower()):
            continue
        cards[int(number.group(1))] = {
            "source_list_name": html.unescape(re.sub(r"<[^>]+>", "", name.group(1))).strip(),
            "source_image_url": urllib.request.urljoin("https://www.pokedatavault.com/", html.unescape(image.group(1))),
            "source_card_url": urllib.request.urljoin("https://www.pokedatavault.com/", html.unescape(href.group(1))),
        }
    return cards


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def webp_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("Image response is not WebP")
    chunk = data[12:16]
    if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
        return width, height
    if chunk == b"VP8X" and len(data) >= 30:
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return width, height
    raise ValueError(f"Unsupported WebP encoding: {chunk!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--set-slug", required=True)
    parser.add_argument("--page-url", required=True)
    parser.add_argument("--output-name", required=True)
    parser.add_argument("--match-unique-name", action="store_true", help="Match only names unique in both this exact source set and the checklist group")
    parser.add_argument("--match-number-only", action="store_true", help="Use a unique printed number from this exact set page when the checklist name differs")
    parser.add_argument("--require-cardmarket-set-route", default="", help="Require exactly one candidate whose Cardmarket Singles route contains this set slug")
    parser.add_argument("--ignore-level-suffix", action="store_true", help="Ignore a trailing Lv. number when matching card names")
    args = parser.parse_args()

    page = get(args.page_url, "https://www.pokedatavault.com/").decode("utf-8", "replace")
    cards = extract_cards(page, args.set_slug)
    if not cards:
        raise RuntimeError(f"No numbered card images found for {args.set_slug}")

    coverage_path = REVIEW / "image-coverage-reconciliation-20261030.csv"
    with coverage_path.open(encoding="utf-8-sig", newline="") as handle:
        coverage = list(csv.DictReader(handle))
    missing = [row for row in coverage if row["group_id"] == args.group_id and row["image_status"] == "missing_image_file"]
    targets: list[tuple[int, dict[str, str]]] = []
    if args.match_unique_name:
        def target_name(row: dict[str, str]) -> str:
            name = row["card_name"]
            if args.ignore_level_suffix:
                name = re.sub(r"\s+Lv\.?\s*\d+\s*$", "", name, flags=re.I)
            return norm(name)

        eligible: list[dict[str, str]] = []
        for row in missing:
            if args.require_cardmarket_set_route:
                urls = [url.strip() for url in row.get("cardmarket_candidate_urls", "").split("|") if url.strip()]
                route = f"/Products/Singles/{args.require_cardmarket_set_route}/"
                if row.get("cardmarket_candidate_count") != "1" or len(urls) != 1 or route not in urls[0]:
                    continue
            eligible.append(row)
        source_by_name: dict[str, list[int]] = {}
        for number, source in cards.items():
            name = source["source_list_name"]
            if args.ignore_level_suffix:
                name = re.sub(r"\s+Lv\.?\s*\d+\s*$", "", name, flags=re.I)
            source_by_name.setdefault(norm(name), []).append(number)
        target_name_counts: dict[str, int] = {}
        for row in eligible:
            name = target_name(row)
            target_name_counts[name] = target_name_counts.get(name, 0) + 1
        for row in eligible:
            name = target_name(row)
            source_numbers = source_by_name.get(name, [])
            if name and target_name_counts[name] == 1 and len(source_numbers) == 1:
                targets.append((source_numbers[0], row))
    else:
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
            if source and target_numbers[number] == 1 and (args.match_number_only or norm(row["card_name"]) == norm(source["source_list_name"])):
                targets.append((number, row))

    out = REVIEW / args.output_name
    previous = json.loads(out.read_text()).get("records", []) if out.exists() else []
    target_numbers = {number for number, _ in targets}
    records = [r for r in previous if int(r.get("source_list_number", "0")) not in target_numbers]
    image_root = ROOT / "images" / "pokedatavault" / args.group_id
    image_root.mkdir(parents=True, exist_ok=True)
    for number, row in targets:
        source = cards[number]
        dest = image_root / f"{args.group_id}_{number:03d}_{args.set_slug}.webp"
        try:
            content = dest.read_bytes() if dest.is_file() else get(source["source_image_url"], args.page_url)
            if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
                ext, (width, height) = "webp", webp_dimensions(content)
            else:
                ext, width, height = image_helpers.image_info(content)
            if ext != "webp" or width < 250 or height < 350:
                raise ValueError(f"Unexpected image type or dimensions: {ext} {width}x{height}")
            if not dest.is_file():
                dest.write_bytes(content)
            records.append({
                "group_id": args.group_id,
                "printed_number": row["printed_number"],
                "checklist_card_name": row["card_name"],
                "source_list_number": str(number),
                "source_list_name": source["source_list_name"],
                "source_image_url": source["source_image_url"],
                "source_card_url": source["source_card_url"],
                "source_list_url": args.page_url,
                "checklist_match": True,
                "image_file": str(dest),
                "image_bytes": len(content),
                "image_width": width,
                "image_height": height,
                "image_sha256": hashlib.sha256(content).hexdigest(),
                "status": "downloaded_or_reused_number_and_name_matched_image",
                "association_basis": (
                    f"PokeDataVault {args.set_slug} exact-set membership with a unique printed number"
                    if args.match_number_only else
                    f"PokeDataVault {args.set_slug} exact-set membership, single Cardmarket set route, and unique exact card-name match after removing the trailing level suffix"
                    if args.require_cardmarket_set_route and args.ignore_level_suffix else
                    f"PokeDataVault {args.set_slug} exact-set membership with a unique exact-name match on the single Cardmarket set route"
                    if args.require_cardmarket_set_route else
                    f"PokeDataVault {args.set_slug} exact-set membership and unique exact card-name match after removing the trailing level suffix"
                    if args.ignore_level_suffix else
                    f"PokeDataVault {args.set_slug} exact-set membership with unique exact card-name matching"
                    if args.match_unique_name else
                    f"PokeDataVault {args.set_slug} set membership with exact printed number and exact card-name match"
                ),
                "match_method": "printed_number_only" if args.match_number_only else "single_set_route_unique_name" if args.require_cardmarket_set_route else "unique_exact_name" if args.match_unique_name else "printed_number_and_name",
            })
        except Exception as error:
            records.append({
                "group_id": args.group_id,
                "printed_number": row["printed_number"],
                "checklist_card_name": row["card_name"],
                "source_list_number": str(number),
                "source_list_name": source["source_list_name"],
                "source_image_url": source["source_image_url"],
                "source_card_url": source["source_card_url"],
                "source_list_url": args.page_url,
                "checklist_match": False,
                "status": "failed",
                "error": str(error)[:400],
            })
        time.sleep(0.1)

    out.write_text(json.dumps({"source_list_url": args.page_url, "group_id": args.group_id, "records": records}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "group_id": args.group_id,
        "source_cards": len(cards),
        "exact_number_and_name_targets": len(targets),
        "acquired": sum(r.get("checklist_match", False) for r in records),
        "failed": sum(r.get("status") == "failed" for r in records),
    }))


if __name__ == "__main__":
    main()
