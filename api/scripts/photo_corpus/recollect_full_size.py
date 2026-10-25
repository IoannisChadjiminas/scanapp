"""Re-download the existing private eBay panel from Browse `image.imageUrl` at s-l1600.

The source corpus is preserved. Outputs go to a new gitignored corpus folder,
and only deduplicated primary listing images with a >=1000px long edge are kept.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
import sys

import httpx

import collect


def cached_images(cache_root: Path) -> dict[str, str]:
    images: dict[str, str] = {}
    for path in cache_root.glob("search-*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in data.get("itemSummaries", []):
            if not isinstance(item, dict):
                continue
            item_id = collect.item_id_from_summary(item, item.get("itemWebUrl"))
            image = item.get("image")
            url = image.get("imageUrl") if isinstance(image, dict) else None
            if item_id and isinstance(url, str):
                images.setdefault(item_id, url)
    return images


def run(source: Path, destination: Path, credentials: Path, limit: int) -> int:
    rows, _ = collect.read_manifest(source / "manifest.csv")
    image_map = cached_images(source / "cache" / "ebay")
    destination.mkdir(parents=True, exist_ok=True)
    raw = destination / "raw"
    raw.mkdir(exist_ok=True)
    rejected = destination / "cache" / "ebay" / "rejected-small-image-ids.txt"
    client_id, client_secret = collect.load_credentials(credentials)
    client = httpx.Client(timeout=35, follow_redirects=False)
    pacer = collect.Pacer()
    try:
        # The credentials are used only to confirm the Browse API token; image
        # URLs themselves are the `image.imageUrl` fields from cached searches.
        token = collect.get_token(client, client_id, client_secret, pacer)
        if not token:
            raise RuntimeError("Browse API token was empty")
        seen: set[str] = set()
        output: list[dict[str, str]] = []
        skipped_no_cache = skipped_small = skipped_bad = 0
        for old in rows:
            if len(output) >= limit:
                break
            item_id = collect.item_id_from_url(old.get("page_url", ""))
            if not item_id or item_id in seen:
                continue
            seen.add(item_id)
            image_url = image_map.get(item_id)
            if not image_url:
                skipped_no_cache += 1
                continue
            try:
                full_url = collect.full_size_image_url(image_url)
                response = collect.get_image(client, full_url, pacer)
                if response.status_code != 200:
                    skipped_bad += 1
                    continue
                ext = collect.image_extension(response.headers.get("content-type", ""), full_url)
                if not ext:
                    skipped_bad += 1
                    continue
                width, height = collect.image_dimensions(response.content)
            except Exception:
                skipped_bad += 1
                continue
            long_edge = max(width, height)
            if long_edge < collect.MIN_LONG_EDGE:
                skipped_small += 1
                rejected.parent.mkdir(parents=True, exist_ok=True)
                with rejected.open("a", encoding="utf-8") as handle:
                    handle.write(item_id + "\n")
                continue
            photo = f"raw/{len(output) + 1:04d}{ext}"
            (destination / photo).write_bytes(response.content)
            output.append({
                "photo": photo,
                "bucket": old.get("bucket", ""),
                "source_site": "ebay",
                "page_url": old["page_url"],
                "title": old.get("title", ""),
                "photo_index": old.get("photo_index", "1"),
                "width": str(width),
                "height": str(height),
                "long_edge": str(long_edge),
            })
            print(f"saved {len(output)}/{limit} ({width}x{height})", flush=True)
        collect.write_manifest(destination / "manifest.csv", output)
        print(json.dumps({
            "saved": len(output), "unique_source_rows": len(seen),
            "no_cached_image_url": skipped_no_cache, "under_1000px": skipped_small,
            "download_or_decode_failure": skipped_bad,
        }, sort_keys=True))
        return len(output)
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/photo-corpus"))
    parser.add_argument("--destination", type=Path, default=Path("data/photo-corpus-fullsize-20261023"))
    parser.add_argument("--credentials", type=Path, default=collect.DEFAULT_CREDENTIAL_FILE)
    parser.add_argument("--limit", type=int, default=350)
    args = parser.parse_args()
    if not 1 <= args.limit <= 500:
        parser.error("--limit must be between 1 and 500")
    return 0 if run(args.source, args.destination, args.credentials, args.limit) >= 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
