"""Acquire official Japanese card images when official set code and printed number can be matched.

This covers selected residual groups whose official result counts differ from the
recovery checklist. It downloads only a record whose printed number resolves to
one still-uncovered checklist row within that group.
"""
from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import acquire_official_group_images as official

ROOT = Path("data/catalogue-gaps/ja-set-recovery-20261029-v3")
REVIEW = ROOT / "review"
OUTPUT = REVIEW / "official-image-number-match-expansion-supplement-20261030.json"
GROUPS = [
    ("ja-ref-665", "XY5-Bg"), ("ja-ref-668", "XY5-Bt"),
    ("ja-ref-812", "L1-Bhg"), ("ja-ref-814", "L1-Bss"),
    ("ja-ref-736", "BW6-Bc"), ("ja-ref-738", "BW6-Bf"),
    ("ja-ref-629", "XY8-Bb"), ("ja-ref-638", "XY8-Br"),
    ("ja-ref-600", "XY11-Br"), ("ja-ref-603", "XY11-Bb"),
    ("ja-ref-718", "BW8-Brf"), ("ja-ref-720", "BW8-Brn"),
    ("ja-ref-764", "BW3-Bh"), ("ja-ref-766", "BW3-Bp"),
    ("ja-ref-780", "BW1-Bb"), ("ja-ref-782", "BW1-Bw"),
    ("ja-ref-744", "BW5-Brn"), ("ja-ref-746", "BW5-Brz"),
    ("ja-ref-677", "XY4"), ("ja-ref-680", "XY3"), ("ja-ref-686", "XY2"),
    ("ja-ref-754", "BW4"), ("ja-ref-790", "L3"), ("ja-ref-792", "LL"), ("ja-ref-794", "L2"),
]


def list_cards(code: str) -> tuple[list[dict], list[str]]:
    cards: list[dict] = []
    urls: list[str] = []
    page = 1
    max_page = 1
    while page <= max_page:
        query = urllib.parse.urlencode({
            "keyword": "", "sm_and_keyword": "true", "regulation_sidebar_form": "all",
            "illust": "", "pg": code, "page": page,
        })
        url = f"{official.BASE_URL}/card-search/resultAPI.php?{query}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": official.USER_AGENT, "Referer": f"{official.BASE_URL}/card-search/index.php"},
        )
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.load(response)
        cards.extend(card for card in payload.get("cardList", []) if card.get("cardID"))
        urls.append(url)
        max_page = int(payload.get("maxPage") or page)
        page += 1
        time.sleep(0.2)
    return cards, urls


def main() -> None:
    coverage = list(csv.DictReader((REVIEW / "image-coverage-reconciliation-20261030.csv").open(encoding="utf-8")))
    payload = json.loads(OUTPUT.read_text()) if OUTPUT.exists() else {
        "source": "Official Pokémon Japan card search; checklist association requires a unique printed-number match.",
        "groups": [],
    }
    for group_id, set_code in GROUPS:
        targets = [row for row in coverage if row["group_id"] == group_id and row["image_status"] == "missing_image_file"]
        cards, api_urls = list_cards(set_code)
        block = next((item for item in payload["groups"] if item.get("group_id") == group_id), None)
        if block is None:
            block = {
                "group_id": group_id,
                "set_code": set_code,
                "checklist_missing_rows": len(targets),
                "official_result_count": len(cards),
                "api_urls": api_urls,
                "records": [],
            }
        processed = {str(item.get("card_id")) for item in block["records"]}
        for position, item in enumerate(cards, 1):
            card_id = str(item["cardID"])
            if card_id in processed:
                continue
            record = {"card_id": card_id, "official_list_name_ja": item.get("cardNameAltText") or item.get("cardNameViewText")}
            try:
                detail = official.detail(card_id)
                record.update(detail)
                matches = [row for row in targets if official.numbers_match(row["printed_number"], detail.get("printed_number", ""))]
                record["checklist_matches"] = [
                    {"group_id": group_id, "printed_number": row["printed_number"], "card_name": row["card_name"]}
                    for row in matches
                ]
                record["checklist_match"] = len(matches) == 1
                if len(matches) == 1:
                    record.update(official.acquire_image(detail, group_id, ROOT / "images" / "official-number-match"))
                else:
                    record["image_acquisition_status"] = "not_downloaded_no_unique_full_number_match"
            except Exception as error:
                record["error"] = str(error)[:400]
                record["checklist_match"] = False
            block["records"].append(record)
            if position % 20 == 0:
                block["processed_candidates"] = position
                payload["groups"] = [entry for entry in payload["groups"] if entry.get("group_id") != group_id] + [block]
                OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
                print(f"{group_id} ({set_code}): {position}/{len(cards)} official records", flush=True)
            time.sleep(0.2)
        block["processed_candidates"] = len(cards)
        block["matched_records"] = sum(bool(record.get("checklist_match")) for record in block["records"])
        block["unique_target_rows_matched"] = len({
            (match["group_id"], match["printed_number"], match["card_name"])
            for record in block["records"] if record.get("checklist_match")
            for match in record.get("checklist_matches", [])
        })
        block["downloaded_images"] = sum(bool(record.get("asset_copied")) for record in block["records"])
        block["unmatched_or_ambiguous_records"] = sum(not record.get("checklist_match") for record in block["records"])
        payload["groups"] = [entry for entry in payload["groups"] if entry.get("group_id") != group_id] + [block]
        OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({key: block[key] for key in (
            "group_id", "set_code", "checklist_missing_rows", "official_result_count",
            "unique_target_rows_matched", "downloaded_images", "unmatched_or_ambiguous_records",
        )}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
