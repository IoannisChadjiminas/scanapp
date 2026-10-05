"""Read-only replay of an isolated staging test session; never changes settings."""
from __future__ import annotations

import argparse
import json
import sqlite3

from app.recognition.rank import _finish_twins, _visual_second, decide_status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--session")
    target.add_argument("--anchor-scan", help="Find the isolated test session internally; do not print its cookie ID")
    parser.add_argument("--database", default="/data/results.sqlite")
    args = parser.parse_args()
    conn = sqlite3.connect(f"file:{args.database}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    try:
        clause = "session_id=?" if args.session else "session_id=(SELECT session_id FROM scans WHERE id=?)"
        rows = conn.execute(
            "SELECT id,status,combined_ranking_json,threshold_config_json "
            f"FROM scans WHERE {clause} ORDER BY created_at,id",
            (args.session or args.anchor_scan,),
        ).fetchall()
        results = []
        for row in rows:
            ranking = json.loads(row["combined_ranking_json"] or "[]")
            thresholds = json.loads(row["threshold_config_json"])
            hypothetical = decide_status(
                ranking,
                enable_matched=True,
                min_visual=thresholds["min_visual"],
                min_visual_ocr=thresholds.get("min_visual_ocr"),
                min_gap=thresholds["min_gap"],
                retake=row["status"] == "retake",
            )
            top = ranking[0] if ranking else {}
            results.append({
                "scan_id": row["id"],
                "actual_status": row["status"],
                "hypothetical_status": hypothetical,
                "top_id": top.get("card_id"),
                "visual_score": top.get("visual_score"),
                "visual_gap": float(top.get("visual_score", 0))
                    - _visual_second(ranking, top.get("card_id", "")),
                "ocr_consistent": top.get("ocr_consistent"),
                "collector_conflict": top.get("collector_conflict"),
                "finish_twins": [r["card_id"] for r in
                    _finish_twins(ranking, top, thresholds["min_gap"])] if ranking else [],
                "candidate_ids": [r["card_id"] for r in ranking],
                "thresholds": thresholds,
            })
        print(json.dumps(results))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
