"""Acquire the eight pictured Japanese EN09 energy cards from Super Cartas."""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path("data/catalogue-gaps/ja-set-recovery-20261029-v3")
REVIEW = ROOT / "review"
GROUP_ID = "ja-ref-1134"
SET_URL = "https://supercartas.com/juego/pokemon/2009-energies"
OUTPUT = REVIEW / "supercartas-ja-ref-1134-2009-energies-image-acquisition-20261030.json"


class Images(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        attrs_map = dict(attrs)
        self.images.append({"src": attrs_map.get("src") or "", "alt": attrs_map.get("alt") or ""})


def get(url: str, referer: str) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; ScanappImageRecovery/1.0)",
        "Referer": referer,
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def webp_size(data: bytes) -> tuple[int, int]:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("Not a WebP image")
    chunk = data[12:16]
    if chunk == b"VP8X":
        return int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
    if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
        return int.from_bytes(data[26:28], "little") & 0x3FFF, int.from_bytes(data[28:30], "little") & 0x3FFF
    raise ValueError(f"Unsupported WebP encoding {chunk!r}")


def main() -> None:
    with (REVIEW / "image-coverage-reconciliation-20261030.csv").open(encoding="utf-8-sig", newline="") as handle:
        coverage = list(csv.DictReader(handle))
    missing = {
        (row["printed_number"], row["card_name"]): row
        for row in coverage
        if row["group_id"] == GROUP_ID and row["image_status"] == "missing_image_file"
    }

    page = get(SET_URL, SET_URL).decode("utf-8", "replace")
    list_items: list[dict[str, str]] = []
    for block in re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            payload = json.loads(html.unescape(block))
        except json.JSONDecodeError:
            continue
        graph = payload.get("@graph", []) if isinstance(payload, dict) else []
        for node in graph:
            if isinstance(node, dict) and node.get("@type") == "CollectionPage":
                items = node.get("mainEntity", {}).get("itemListElement", [])
                list_items.extend(item for item in items if isinstance(item, dict))

    records: list[dict[str, object]] = []
    image_dir = ROOT / "images" / "supercartas" / GROUP_ID
    image_dir.mkdir(parents=True, exist_ok=True)
    for number in range(1, 9):
        number_text = f"{number:03d}"
        jp_item = next((item for item in list_items if f"EN09 No. {number_text}" in item.get("name", "") and "JP" in item.get("name", "")), None)
        if not jp_item:
            continue
        card_url = jp_item["url"]
        detail_page = get(card_url, SET_URL).decode("utf-8", "replace")
        parser = Images()
        parser.feed(detail_page)
        image = next((item for item in parser.images if "/pokemon/cards/jp/" in item["src"] and "/thumbs/" not in item["src"]), None)
        if not image:
            continue
        target = next((row for (printed, _name), row in missing.items() if printed == number_text), None)
        if not target:
            continue
        image_url = urllib.parse.quote(urllib.parse.urljoin(card_url, html.unescape(image["src"])), safe=":/?=&%")
        data = get(image_url, SET_URL)
        width, height = webp_size(data)
        if width < 250 or height < 350:
            continue
        image_path = image_dir / f"{GROUP_ID}_{number_text}_supercartas.webp"
        image_path.write_bytes(data)
        records.append({
            "group_id": GROUP_ID,
            "printed_number": number_text,
            "checklist_card_name": target["card_name"],
            "source_list_name": jp_item.get("name", ""),
            "source_card_url": card_url,
            "source_image_url": image_url,
            "source_list_url": SET_URL,
            "checklist_match": True,
            "image_file": image_path.as_posix(),
            "image_bytes": len(data),
            "image_width": width,
            "image_height": height,
            "image_sha256": hashlib.sha256(data).hexdigest(),
            "status": "downloaded_or_reused_exact_japanese_set_number_image",
            "association_basis": "Super Cartas EN09 set page identifies this entry as the Japanese (JP) printing and its EN09 number exactly matches the numbered checklist row",
            "match_method": "exact_japanese_set_number",
        })

    OUTPUT.write_text(json.dumps({"source_list_url": SET_URL, "group_id": GROUP_ID, "records": records}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"japanese_numbered_targets": 8, "acquired": len(records), "manifest": str(OUTPUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
