"""Acquire official high-resolution images for checklist groups with exact set-code filters.

This intentionally handles only groups whose official result count equals the
recovery registry's listed-card count. Broader pools need separate reconciliation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = "https://www.pokemon-card.com"
USER_AGENT = "scanapp-catalogue/1.0"


def get(url: str, *, referer: str, retries: int = 3) -> bytes:
    delay = 2.0
    last: Exception | None = None
    for attempt in range(retries):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Referer": referer},
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (401, 403):
                raise RuntimeError(f"Official source requires manual review: HTTP {exc.code} {url}") from exc
            if exc.code not in (429, 500, 502, 503, 504) or attempt + 1 >= retries:
                raise
            retry_after = exc.headers.get("Retry-After")
            time.sleep(float(retry_after) if retry_after and retry_after.isdigit() else delay)
        except Exception as exc:
            last = exc
            if attempt + 1 >= retries:
                raise
            time.sleep(delay)
        delay = min(delay * 2, 20)
    raise last or RuntimeError(url)


def image_info(data: bytes) -> tuple[str, int, int]:
    if len(data) >= 30 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8X":
            return (
                "webp",
                int.from_bytes(data[24:27], "little") + 1,
                int.from_bytes(data[27:30], "little") + 1,
            )
        if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            return (
                "webp",
                int.from_bytes(data[26:28], "little") & 0x3FFF,
                int.from_bytes(data[28:30], "little") & 0x3FFF,
            )
        if chunk == b"VP8L" and data[20] == 0x2F:
            width = 1 + data[21] + ((data[22] & 0x3F) << 8)
            height = 1 + ((data[22] >> 6) & 0x03) + (data[23] << 2) + ((data[24] & 0x0F) << 10)
            return "webp", width, height
        raise ValueError(f"Unsupported WebP encoding: {chunk!r}")
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        return "gif", int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return "png", int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:2] != b"\xff\xd8":
        raise ValueError("Official image response has an unsupported image signature")
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        while i < len(data) and data[i] == 0xFF:
            i += 1
        if i >= len(data):
            break
        marker = data[i]
        i += 1
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            continue
        length = int.from_bytes(data[i : i + 2], "big")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            return "jpg", int.from_bytes(data[i + 5 : i + 7], "big"), int.from_bytes(data[i + 3 : i + 5], "big")
        i += length
    raise ValueError("JPEG dimensions were not found")


def card_list(code: str) -> tuple[list[dict], list[str]]:
    cards: list[dict] = []
    urls: list[str] = []
    page = 1
    max_page = 1
    while page <= max_page:
        params = urllib.parse.urlencode({
            "keyword": "", "sm_and_keyword": "true", "regulation_sidebar_form": "all",
            "illust": "", "pg": code, "page": page,
        })
        url = f"{BASE_URL}/card-search/resultAPI.php?{params}"
        payload = json.loads(get(url, referer=f"{BASE_URL}/card-search/index.php"))
        if int(payload.get("result") or 0) != 1:
            raise RuntimeError(f"Official result API returned no result for {code} page {page}")
        batch = payload.get("cardList") or []
        cards.extend(x for x in batch if isinstance(x, dict) and x.get("cardID"))
        urls.append(url)
        max_page = max(page, int(payload.get("maxPage") or page))
        if not batch:
            break
        page += 1
        time.sleep(0.2)
    return cards, urls


def detail(card_id: str) -> dict:
    url = f"{BASE_URL}/card-search/details.php/card/{urllib.parse.quote(card_id, safe='')}/regu/all"
    html = get(url, referer=f"{BASE_URL}/card-search/index.php").decode("utf-8", "replace")
    image = re.search(r'<img class="fit" src="([^"]+)"\s+alt="([^"]+)"', html)
    number = re.search(
        r'alt="([^"<>]+)"\s*/>\s*&nbsp;([0-9]{1,4})&nbsp;/&nbsp;'
        r'([0-9]{1,4}|[A-Za-z][A-Za-z0-9.-]*)&nbsp;',
        html,
    )
    if not image:
        raise ValueError(f"Could not parse official card detail {card_id}")
    image_path, name = image.groups()
    image_url = urllib.parse.urljoin(BASE_URL, image_path)
    if number:
        set_code, numerator, denominator = number.groups()
        printed = numerator if not denominator.isdigit() else f"{numerator}/{denominator}"
    else:
        logo = re.search(r'regulation_logo_[^/]+/[^"/]+\.(?:gif|png|svg)"[^>]*alt="([^"]+)"', html)
        set_code = logo.group(1) if logo else ""
        printed = ""
    return {"card_id": card_id, "official_name_ja": name, "set_code": set_code,
            "printed_number": printed, "image_url": image_url, "detail_url": url}


def checklist_rows(review: Path, group_id: str) -> list[dict]:
    result: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for path in review.glob("*-checklist*.csv"):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("group_id") != group_id:
                    continue
                key = (str(row.get("printed_number") or "").strip(), str(row.get("card_name") or "").strip())
                if key not in seen:
                    seen.add(key)
                    result.append(row)
    return result


def numbers_match(a: str, b: str) -> bool:
    a = str(a or "").strip().upper()
    b = str(b or "").strip().upper()
    if a == b:
        return bool(a)
    # A checklist sometimes stores only the numerator while the official card
    # detail provides numerator/denominator.
    return bool(a and b and "/" not in a and "/" in b and b.split("/", 1)[0] == a)


def acquire_image(record: dict, group_id: str, image_root: Path) -> dict:
    code = re.sub(r"[^A-Za-z0-9.-]+", "-", record.get("set_code") or "set").strip("-")
    number = re.sub(r"[^A-Za-z0-9.-]+", "-", record.get("printed_number") or "unnumbered").strip("-")
    stem = f"{group_id}_{code}_{number}_{record['card_id']}"
    dest_dir = image_root / group_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    cached = next((p for p in dest_dir.glob(f"{stem}.*") if p.is_file()), None)
    content = cached.read_bytes() if cached else get(record["image_url"], referer=f"{BASE_URL}/card-search/index.php")
    ext, width, height = image_info(content)
    dest = dest_dir / f"{stem}.{ext}"
    if cached and cached != dest:
        cached.unlink()
    if not dest.is_file() or dest.read_bytes() != content:
        dest.write_bytes(content)
    return {
        "image_file": str(dest),
        "image_bytes": len(content),
        "image_width": width,
        "image_height": height,
        "image_sha256": hashlib.sha256(content).hexdigest(),
        "asset_copied": True,
        "reuse_status": "downloaded_approved_official_source",
        "image_format": ext,
        "quality_note": "Official image; signature and dimensions validated.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/catalogue-gaps/ja-set-recovery-20261029-v3"))
    parser.add_argument("--max-groups", type=int, default=0, help="Checkpoint budget; 0 processes every eligible group")
    parser.add_argument("--start-after", default="", help="Resume after this registry group ID")
    args = parser.parse_args()
    review = args.root / "review"
    registry = json.loads((args.root / "set-registry.json").read_text())
    discovery = json.loads((review / "official-image-set-code-discovery.json").read_text())
    discovery_by_code = {str(x["code"]).upper(): x for x in discovery["results"]}
    index_path = review / "official-image-source-audit-index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"created": "2026-10-30", "audits": []}
    completed = {x["group_id"] for x in index.get("audits", [])}
    selected = []
    for group in registry:
        code = str(group.get("code") or "").strip()
        result = discovery_by_code.get(code.upper())
        if not result or not int(result.get("hit_count") or 0):
            continue
        if int(result["hit_count"]) != int(group.get("listed_cards") or 0):
            continue
        if group["group_id"] in completed:
            continue
        if args.start_after and group["group_id"] <= args.start_after:
            continue
        selected.append(group)
    if args.max_groups > 0:
        selected = selected[: args.max_groups]
    print(f"eligible new groups: {len(selected)}", flush=True)

    for group in selected:
        gid, code = group["group_id"], str(group["code"])
        checklist = checklist_rows(review, gid)
        cards, api_urls = card_list(code)
        expected = int(group["listed_cards"])
        if len(cards) != expected:
            raise RuntimeError(f"{gid} expected {expected} official list cards, got {len(cards)}")
        records = []
        for position, item in enumerate(cards, 1):
            card = detail(str(item["cardID"]))
            card.update(acquire_image(card, gid, args.root / "images" / "official"))
            matches = [r for r in checklist if numbers_match(r.get("printed_number", ""), card["printed_number"])]
            # Some source lists omit a denominator; a same-number match is only
            # accepted when it identifies exactly one checklist row.
            card["checklist_match"] = len(matches) == 1
            card["checklist_card_name"] = str(matches[0].get("card_name") or "") if len(matches) == 1 else ""
            card["checklist_match_count"] = len(matches)
            records.append(card)
            if position % 20 == 0:
                print(f"{gid}: detailed {position}/{len(cards)}", flush=True)
            time.sleep(0.15)

        unmatched = [r.get("printed_number", "") for r in checklist
                     if not any(x["checklist_match"] and numbers_match(r.get("printed_number", ""), x["printed_number"])
                                for x in records)]
        payload = {
            "group_id": gid,
            "name": group["name"],
            "official_card_search_filter": f"pg={code}",
            "api_urls": api_urls,
            "official_product_result_count": len(cards),
            "retrieved_card_records": len(records),
            "checklist_rows": len(checklist),
            "official_records_matching_checklist_by_printed_number": sum(x["checklist_match"] for x in records),
            "unmatched_checklist_numbers": unmatched,
            "unmatched_product_records": [x for x in records if not x["checklist_match"]],
            "total_image_bytes": sum(x["image_bytes"] for x in records),
            "image_dimensions": sorted({f"{x['image_width']}x{x['image_height']}" for x in records}),
            "records": records,
            "notes": ["Official result API set-code result count exactly matched the registry checklist count.",
                      "Official detail pages confirm each image URL and printed number. User confirmed approval to use these images."],
        }
        out = review / f"{gid}-official-image-source-audit.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        summary = {
            "file": out.name,
            "group_id": gid,
            "official_records": len(records),
            "checklist_rows": len(checklist),
            "matched_checklist_rows": payload["official_records_matching_checklist_by_printed_number"],
            "unmatched_checklist_rows": len(unmatched),
            "asset_files_copied": sum(bool(x["asset_copied"]) for x in records),
            "image_urls_recorded": sum(bool(x["image_url"]) for x in records),
            "total_image_bytes": payload["total_image_bytes"],
            "image_dimensions": payload["image_dimensions"],
            "reuse_status": "downloaded_approved_official_source",
        }
        index.setdefault("audits", []).append(summary)
        index["audit_count"] = len(index["audits"])
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
