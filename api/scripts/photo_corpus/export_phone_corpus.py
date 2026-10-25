"""Create the private Stage1Checks payload consumed by PokeSingle debug builds."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re

from PIL import Image, ImageOps


def export(corpus: Path, destination: Path, run_id: str, offset: int, count: int) -> int:
    with (corpus / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not 300 <= len(rows) <= 500:
        raise ValueError(f"expected 300–500 photos, found {len(rows)}")
    if offset < 0 or not 1 <= count <= 50 or offset >= len(rows):
        raise ValueError("offset must address the corpus and batch count must be 1–50")
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,36}", run_id):
        raise ValueError("run ID must be 1–36 ASCII letters, digits, underscores, or hyphens")
    destination.mkdir(parents=True, exist_ok=True)
    batch = rows[offset:offset + count]
    cases = []
    for i, row in enumerate(batch, 1):
        source = corpus / row["photo"]
        if not source.is_file():
            raise FileNotFoundError(source)
        name = f"photo-{i:04d}.jpg"
        with Image.open(source) as image:
            upright = ImageOps.exif_transpose(image).convert("RGB")
            upright.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
            upright.save(destination / name, format="JPEG", quality=90, optimize=True)
        cases.append({"file": name, "index": offset + i - 1})
    (destination / "corpus.json").write_text(json.dumps({
        "diagnostic_run": run_id,
        "photos": cases,
    }, separators=(",", ":")), encoding="utf-8")
    print(f"Prepared {len(cases)} private photos for run {run_id}.")
    return len(cases)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("data/photo-corpus-fullsize-20261023"))
    parser.add_argument("--destination", type=Path, default=Path("/tmp/pokesingle-fullsize-Stage1Checks/Corpus"))
    parser.add_argument("--run-id", default="ebay-fullsize-20261023")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--count", type=int, default=50)
    args = parser.parse_args()
    return 0 if export(args.corpus, args.destination, args.run_id, args.offset, args.count) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
