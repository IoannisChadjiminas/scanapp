"""Turn user feedback into a labelled set for threshold tuning.

Every scan the user confirmed, corrected or rejected becomes one JSON line
with what the server saw (its stored ranking and thresholds) and what the
user chose. No images or OCR text are copied.

    python scripts/export_labels.py --results /data/results.sqlite --out labels.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.scan_summary import scan_outcome  # noqa: E402

RANKING_KEYS = ('card_id', 'visual_score', 'combined_score', 'ocr_consistent', 'collector_conflict',
                'structured_collector_conflict', 'language_conflict', 'strong_name_conflict',
                'localized_name_unknown', 'name', 'set_name', 'collector_number', 'language', 'finish')


def labelled_rows(conn: sqlite3.Connection, since: str | None = None):
    conn.row_factory = sqlite3.Row
    query = ('SELECT id, created_at, status, threshold_config_json, combined_ranking_json, '
             'confirmed_card_id, rejected FROM scans '
             'WHERE (confirmed_card_id IS NOT NULL OR rejected = 1)')
    params: tuple = ()
    if since:
        query += ' AND created_at >= ?'
        params = (since,)
    for row in conn.execute(query + ' ORDER BY created_at', params):
        ranking = json.loads(row['combined_ranking_json'] or '[]')
        action = 'reject' if row['rejected'] else 'confirm'
        yield dict(
            scan_id=row['id'],
            created_at=row['created_at'],
            status=row['status'],
            thresholds=json.loads(row['threshold_config_json'] or '{}'),
            ranking=[{key: item.get(key) for key in RANKING_KEYS if key in item}
                     for item in ranking[:10]],
            chosen_card_id=row['confirmed_card_id'],
            rejected=bool(row['rejected']),
            outcome=scan_outcome(action, row['confirmed_card_id'], row['combined_ranking_json']),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--results', type=Path, required=True, help='results SQLite database')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--since', help='ISO timestamp; only scans created at or after it')
    args = parser.parse_args()
    conn = sqlite3.connect(f'file:{args.results}?mode=ro', uri=True)
    count = 0
    with args.out.open('w') as handle:
        for row in labelled_rows(conn, args.since):
            handle.write(json.dumps(row) + '\n')
            count += 1
    print(f'{count} labelled scans written to {args.out}')


if __name__ == '__main__':
    main()
