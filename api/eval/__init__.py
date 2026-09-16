"""Optional Tesseract comparison on a 50-image development sample.

Production recognition uses RapidOCR only. This script is for local evaluation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    try:
        import pytesseract
    except ImportError as exc:
        raise SystemExit("Install pytesseract and Tesseract only for this comparison.") from exc

    dataset = Path(args.dataset)
    labels = [
        json.loads(line)
        for line in (dataset / "labels.jsonl").read_text().splitlines()
        if line.strip()
    ][: args.limit]
    hits = 0
    for item in labels:
        image = Image.open(dataset / "images" / item["file"])
        text = pytesseract.image_to_string(image)
        if item.get("collector_number") and str(item["collector_number"]) in text.replace(" ", ""):
            hits += 1
    print(json.dumps({"n": len(labels), "collector_hits": hits}, indent=2))


if __name__ == "__main__":
    main()
