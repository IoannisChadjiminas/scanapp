"""Acquire a bounded outside-list batch. No catalogue writes or image approvals.

Run from the repository root, with Python -I. Downloads are cached per URL and
recorded before the next request; image approval remains a separate eye check.
Only rows that carry an image_url on limitlesstcg.nyc3.cdn.digitaloceanspaces.com are taken.
Example: python -I api/scripts/ja_set_recovery/acquire_limitless_batch.py \
    RUN_DIR --set-code SI --catalogue-json RUN_DIR/catalogue-current.json
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image


HOSTS = {"limitlesstcg.nyc3.cdn.digitaloceanspaces.com", "www.pokemon-card.com"}


def row_key(row):
    """The row's number, or for unnumbered rows the token between the set code and `_R_JP` in the image URL."""
    if row["number"] is not None:
        return str(row["number"])
    stem = urlparse(row["image_url"]).path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    if urlparse(row["image_url"]).netloc == "www.pokemon-card.com":
        return stem
    return stem.split("_")[1] if stem.count("_") >= 2 else stem


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--set-code", required=True)
    parser.add_argument("--catalogue-json", required=True, type=Path)
    parser.add_argument("--gap", type=float, default=0.5)
    parser.add_argument("--our-set", default=None, help="set_id of the catalogue snapshot when it differs from --set-code")
    parser.add_argument("--row-source", default="limitless", help="row_source of the rows to take")
    parser.add_argument("--statuses", default="missing", help="comma list of row statuses to take")
    parser.add_argument("--source-set-name", default=None, help="source_set value when it differs from --set-code")
    args = parser.parse_args()
    if args.gap < 0.5:
        parser.error("request gap must be at least 0.5 seconds")
    run = args.run_dir.resolve()
    images = run / "images" / "limitless"
    images.mkdir(parents=True, exist_ok=True)
    source = Path("docs/outside-list-missing-rows-20261111.json")
    rows = [r for r in json.loads(source.read_text())["rows"]
            if r["language"] == "ja" and r["source_set"] == args.set_code
            and r["row_source"] == args.row_source and r["status"] in args.statuses.split(",")
            and r.get("image_url")]
    existing = json.loads(args.catalogue_json.read_text())
    if not rows or any(r["set_id"] != (args.our_set or args.set_code) for r in existing):
        raise ValueError("empty batch or catalogue snapshot for a different set")
    numbers = {str(r["collector_number"]).lstrip("0") for r in existing}
    skipped = [r for r in rows if r["number"] is not None and r["number"].lstrip("0") in numbers]
    targets = [r for r in rows if r not in skipped]
    (run / "source-rows.json").write_text(json.dumps(targets, ensure_ascii=False, indent=2) + "\n")
    (run / "already-present.json").write_text(json.dumps(skipped, ensure_ascii=False, indent=2) + "\n")
    audit = run / "acquisition.jsonl"
    previous = [json.loads(line) for line in audit.read_text().splitlines()] if audit.exists() else []
    cached = {r["url"]: r for r in previous}
    for row in targets:
        url = row["image_url"]
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc not in HOSTS:
            raise ValueError("unexpected source host")
        if parsed.netloc == "www.pokemon-card.com":  # official card search: the file name is the key
            suffix = parsed.path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            extension = urlparse(url).path.rsplit(".", 1)[-1].lower()  # jpg, png or gif
        else:
            number = row_key(row)
            suffix = f"{int(number):03d}" if number.isdigit() else number
            extension = "png"
        if not re.fullmatch(r"[A-Za-z0-9_-]+", suffix):
            raise ValueError("unsafe source number")
        filename = images / f'{args.set_code}_{suffix}.{extension}'
        if url in cached:
            record = cached[url]
            if not filename.is_file() or hashlib.sha256(filename.read_bytes()).hexdigest() != record["sha256"]:
                raise ValueError(f"cached image changed: {filename}")
            continue
        if filename.exists():
            raise ValueError(f"unrecorded image: {filename}")
        request = urllib.request.Request(url, headers={"User-Agent": "ScanappCatalogueRecovery/1.0"})
        with urllib.request.urlopen(request, timeout=45) as response:
            if response.url != url:
                raise ValueError("unexpected redirect")
            data = response.read()
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            if image.format != {"png": "PNG", "jpg": "JPEG", "gif": "GIF"}.get(extension):
                raise ValueError("unexpected image format")
            width, height = image.size
        filename.write_bytes(data)
        record = {"number": row_key(row), "name": row["name"], "row_url": row["row_url"],
                  "url": url, "file": str(filename), "bytes": len(data), "width": width,
                  "height": height, "sha256": hashlib.sha256(data).hexdigest(),
                  "downloaded_at": datetime.now(timezone.utc).isoformat(), "eye_check": "pending"}
        with audit.open("a") as output:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(json.dumps({"number": row_key(row), "width": width, "height": height}), flush=True)
        time.sleep(args.gap)
    print(json.dumps({"targets": len(targets), "already_present": len(skipped)}))


if __name__ == "__main__":
    main()
