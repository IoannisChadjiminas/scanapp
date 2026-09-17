from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
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


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(len(ordered) * fraction)))
    return ordered[index]


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
    recall20 = 0
    matched_n = matched_correct = 0
    wrong_print = wrong_language = 0
    unknown_n = unknown_rejected = 0
    latencies: list[float] = []
    rows: list[dict] = []
    splits: dict[str, dict[str, float]] = defaultdict(lambda: {"n": 0, "top1": 0, "matched_precision_n": 0, "matched_correct": 0})
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
            store_capture=False,
        )
        elapsed = (time.perf_counter() - started) * 1000
        latencies.append(elapsed)
        predicted = [c.card_id for c in result.suggestions]
        stored = dbs.results.execute(
            "SELECT visual_ranking_json FROM scans WHERE id = ?",
            (result.id,),
        ).fetchone()
        retrieved = [
            str(row.get("card_id") or "")
            for row in json.loads(stored["visual_ranking_json"] or "[]")
        ][:20]
        truth = item.get("card_id") or ""
        unknown = bool(item.get("unknown")) or truth in {"", "unknown"}
        status = result.status.value
        if status in {"failed", "retake"}:
            failures += 1
        if unknown:
            unknown_n += 1
            if status in {"no_match", "uncertain", "retake"}:
                unknown_rejected += 1
        else:
            if predicted and predicted[0] == truth:
                top1 += 1
            if truth in predicted:
                top3 += 1
            if truth in retrieved:
                recall20 += 1
            if predicted and predicted[0] != truth:
                top = result.suggestions[0]
                truth_lang = str(item.get("language") or "")
                if truth_lang and top.language and top.language != truth_lang:
                    wrong_language += 1
                else:
                    wrong_print += 1
        if status == "matched":
            matched_n += 1
            if predicted and predicted[0] == truth and not unknown:
                matched_correct += 1
        for tag in item.get("tags") or ["all"]:
            bucket = splits[str(tag)]
            bucket["n"] += 1
            if not unknown and predicted and predicted[0] == truth:
                bucket["top1"] += 1
            if status == "matched":
                bucket["matched_precision_n"] += 1
                if predicted and predicted[0] == truth and not unknown:
                    bucket["matched_correct"] += 1
        rows.append(
            {
                "file": item["file"],
                "truth": truth,
                "status": status,
                "predicted": predicted,
                "retrieved20": retrieved,
                "latency_ms": round(elapsed, 2),
                "tags": item.get("tags") or [],
            }
        )

    labelled = max(len(labels) - unknown_n, 1)
    report = {
        "n": len(labels),
        "top1": top1 / labelled,
        "top3": top3 / labelled,
        "recall@20": recall20 / labelled,
        "matched_precision": (matched_correct / matched_n) if matched_n else None,
        "wrong_print_rate": wrong_print / labelled,
        "wrong_language_rate": wrong_language / labelled,
        "unknown_rejection": (unknown_rejected / unknown_n) if unknown_n else None,
        "failures": failures,
        "p50_ms": _percentile(latencies, 0.50),
        "p95_ms": _percentile(latencies, 0.95),
        "preprocess": args.preprocess,
        "use_ocr": args.use_ocr,
        "note": "A cosine score is similarity, not a probability.",
        "splits": {
            tag: {
                "n": int(stats["n"]),
                "top1": stats["top1"] / stats["n"] if stats["n"] else None,
                "matched_precision": (
                    stats["matched_correct"] / stats["matched_precision_n"]
                    if stats["matched_precision_n"]
                    else None
                ),
            }
            for tag, stats in splits.items()
        },
        "rows": rows,
    }
    Path(args.out).write_text(json.dumps(report, indent=2))
    csv_path = Path(args.out).with_suffix(".csv")
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["file", "truth", "status", "predicted", "latency_ms", "tags"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "file": row["file"],
                    "truth": row["truth"],
                    "status": row["status"],
                    "predicted": " ".join(row["predicted"]),
                    "latency_ms": row["latency_ms"],
                    "tags": " ".join(row["tags"]),
                }
            )
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
