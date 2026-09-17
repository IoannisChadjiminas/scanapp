from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import time

from app.config import Settings
from app.db import Databases
from app.recognition.pipeline import recognize_bytes
from app.recognition.runtime import Runtime


def load_labels(path: Path) -> list[dict]:
    items = []
    for line in path.read_text().splitlines():
        if line.strip():
            items.append(json.loads(line))
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Recognition evaluation harness")
    parser.add_argument("--dataset", required=True, help="Directory with images/ and labels.jsonl")
    parser.add_argument("--preprocess", default="pad")
    parser.add_argument("--use-ocr", action="store_true", default=True)
    parser.add_argument("--out", default="eval-report.json")
    args = parser.parse_args()

    dataset = Path(args.dataset)
    labels = load_labels(dataset / "labels.jsonl")
    settings = Settings(preprocess_config=args.preprocess, use_ocr=args.use_ocr)
    dbs = Databases(settings)
    dbs.results.execute(
        "INSERT OR IGNORE INTO sessions (id, created_at, last_seen) VALUES ('eval', datetime('now'), datetime('now'))"
    )
    dbs.results.commit()
    runtime = Runtime(settings=settings)
    runtime.load()
    runtime.bind_card_languages(dbs.catalog)
    if not runtime.ready:
        raise SystemExit(runtime.error or "runtime not ready")

    top1 = top3 = failures = 0
    latencies: list[float] = []
    rows: list[dict] = []
    for item in labels:
        image_path = dataset / "images" / item["file"]
        data = image_path.read_bytes()
        started = time.perf_counter()
        result = recognize_bytes(
            data,
            settings=settings,
            runtime=runtime,
            catalog=dbs.catalog,
            results=dbs.results,
            session_id="eval",
        )
        elapsed = (time.perf_counter() - started) * 1000
        latencies.append(elapsed)
        predicted = [c.card_id for c in result.suggestions]
        truth = item["card_id"]
        if result.status.value == "failed" or result.status.value == "retake":
            failures += 1
        if predicted and predicted[0] == truth:
            top1 += 1
        if truth in predicted:
            top3 += 1
        rows.append(
            {
                "file": item["file"],
                "truth": truth,
                "status": result.status.value,
                "predicted": predicted,
                "latency_ms": round(elapsed, 2),
            }
        )

    n = max(len(labels), 1)
    latencies.sort()
    report = {
        "n": len(labels),
        "top1": top1 / n,
        "top3": top3 / n,
        "failures": failures,
        "p50_ms": latencies[len(latencies) // 2] if latencies else None,
        "p95_ms": latencies[int(len(latencies) * 0.95)] if latencies else None,
        "preprocess": args.preprocess,
        "use_ocr": args.use_ocr,
        "rows": rows,
    }
    Path(args.out).write_text(json.dumps(report, indent=2))
    csv_path = Path(args.out).with_suffix(".csv")
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["file", "truth", "status", "predicted", "latency_ms"])
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "predicted": " ".join(row["predicted"])})
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
