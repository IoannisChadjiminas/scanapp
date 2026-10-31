"""Acquire uniquely named images from BinderBoss's Japanese Unnumbered Promos set."""
from __future__ import annotations

import csv
import argparse
import hashlib
import html
import json
import re
import struct
import urllib.request
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path("data/catalogue-gaps/ja-set-recovery-20261029-v3")
REVIEW = ROOT / "review"
DEFAULT_GROUP_ID = "ja-ref-1157"
DEFAULT_SOURCE_URL = "https://binderboss.io/sets/miscp_ja"


class CardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.cards: list[dict[str, str]] = []
        self.in_li = False
        self.current: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "li" and not self.in_li:
            self.in_li = True
            self.current = {}
        elif self.in_li and tag == "img" and self.current is not None:
            self.current["alt"] = attrs_dict.get("alt") or ""
            self.current["image_url"] = attrs_dict.get("src") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "li" and self.in_li:
            if self.current and self.current.get("alt") and self.current.get("image_url"):
                self.cards.append(self.current)
            self.current = None
            self.in_li = False


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ScanappImageRecovery/1.0)"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--group-id", default=DEFAULT_GROUP_ID)
    args.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    args.add_argument("--output-name", default="binderboss-ja-ref-1157-misc-promos-image-acquisition-20261030.json")
    options = args.parse_args()
    group_id = options.group_id
    source_url = options.source_url
    output_path = REVIEW / options.output_name
    parser = CardParser()
    parser.feed(get(source_url).decode("utf-8", "replace"))
    cards: list[dict[str, str]] = []
    for card in parser.cards:
        alt = html.unescape(card["alt"])
        match = re.search(r"\(([^()]*)\)\s*$", alt)
        name = match.group(1) if match else alt
        image_url = card["image_url"].replace("/small", "/large")
        cards.append({"name": name, "image_url": image_url})

    with (REVIEW / "image-coverage-reconciliation-20261030.csv").open(encoding="utf-8-sig", newline="") as handle:
        coverage = list(csv.DictReader(handle))
    group_rows = [row for row in coverage if row["group_id"] == group_id]
    missing = [row for row in group_rows if row["image_status"] == "missing_image_file"]
    source_counts = Counter(norm(card["name"]) for card in cards)
    checklist_counts = Counter(norm(row["card_name"]) for row in group_rows)
    by_name = {norm(card["name"]): card for card in cards if source_counts[norm(card["name"])] == 1}
    acquired: list[dict[str, object]] = []
    image_dir = ROOT / "images" / "binderboss" / group_id
    image_dir.mkdir(parents=True, exist_ok=True)

    for row in missing:
        key = norm(row["card_name"])
        if checklist_counts[key] != 1 or source_counts[key] != 1 or key not in by_name:
            continue
        source = by_name[key]
        data = get(source["image_url"])
        if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
            continue
        width, height = struct.unpack(">II", data[16:24])
        if width < 250 or height < 350:
            continue
        image_name = f"{group_id}_{row['printed_number'].lower().replace(' ', '_')}_binderboss.png"
        image_path = image_dir / image_name
        image_path.write_bytes(data)
        relative_path = image_path.as_posix()
        acquired.append({
            "group_id": group_id,
            "printed_number": row["printed_number"],
            "checklist_card_name": row["card_name"],
            "source_card_name": source["name"],
            "source_image_url": source["image_url"],
            "source_list_url": source_url,
            "checklist_match": True,
            "image_file": relative_path,
            "image_bytes": image_path.stat().st_size,
            "image_width": width,
            "image_height": height,
            "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
            "status": "downloaded_or_reused_unique_name_matched_image",
            "association_basis": f"BinderBoss exact Japanese set membership with unique exact English card-name match in source and checklist: {source_url}",
            "match_method": "unique_exact_name",
        })

    output_path.write_text(json.dumps({"source_list_url": source_url, "group_id": group_id, "records": acquired}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"source_cards": len(cards), "missing_targets": len(missing), "acquired": len(acquired), "manifest": str(output_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
