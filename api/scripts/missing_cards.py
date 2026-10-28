"""List catalogue cards without a picture vector, by set. Read-only.

Uses a phone-index export (export_cloud_snapshot.py output): catalog.sqlite plus
vectors/<preprocess>/embedding_card_ids.npy. A card without a vector cannot be found by
the picture search on the server or the phone.

    cd api && .venv/bin/python scripts/missing_cards.py --export <export-dir> \
        [--language en] [--csv <work>/missing-en.csv]

Prints a per-set summary; --csv writes one row per card. Each card is marked:
  no_image        no reference image: it needs an image before it can get a vector
  image_no_vector an image exists but no vector: often a deliberate exclusion (look-alike,
                  display-only); check the catalogue handoff notes before adding it
  pocket          a TCG Pocket card, which the scanner never searches
Public card data only.
"""
import argparse
from collections import Counter, defaultdict
import csv
from pathlib import Path
import sqlite3
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.physical_cards import is_tcg_pocket_card  # noqa: E402

FIELDS = ('id', 'name', 'set_id', 'set_name', 'collector_number', 'printed_collector_number',
          'rarity', 'category', 'reason', 'has_image', 'image_path', 'remote_image_url',
          'cardmarket_url')


def vector_ids(export: Path) -> set[str]:
    found = sorted(export.glob('vectors/*/embedding_card_ids.npy'))
    if len(found) != 1:
        sys.exit(f'expected one vectors/<preprocess>/embedding_card_ids.npy in {export}, found {len(found)}')
    return {str(card_id) for card_id in np.load(found[0], allow_pickle=False)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--export', required=True, type=Path)
    ap.add_argument('--language', default='en')
    ap.add_argument('--csv', type=Path)
    args = ap.parse_args()

    indexed = vector_ids(args.export)
    catalog = sqlite3.connect(f"file:{args.export / 'catalog.sqlite'}?mode=ro", uri=True)
    catalog.row_factory = sqlite3.Row
    columns = {row[1] for row in catalog.execute('PRAGMA table_info(cards)')}
    rows = catalog.execute('SELECT * FROM cards WHERE language = ? ORDER BY set_id, id',
                           (args.language,)).fetchall()

    missing = []
    for row in rows:
        if row['id'] in indexed:
            continue
        card = {field: (row[field] if field in columns else None) for field in FIELDS if field != 'reason'}
        card['reason'] = ('pocket' if is_tcg_pocket_card(row['language'], row['set_id'])
                          else 'image_no_vector' if row['has_image'] else 'no_image')
        missing.append(card)

    by_set = defaultdict(Counter)
    names = {}
    for card in missing:
        by_set[card['set_id']][card['reason']] += 1
        names[card['set_id']] = card['set_name']
    reasons = Counter(card['reason'] for card in missing)
    print(f"{args.language}: {len(rows)} cards, {len(rows) - len(missing)} with a vector, "
          f"{len(missing)} without ({', '.join(f'{k} {v}' for k, v in sorted(reasons.items()))})")
    print(f"{'set_id':<16} {'set name':<40} {'missing':>7}  reasons")
    for set_id, counts in sorted(by_set.items(), key=lambda item: (-sum(item[1].values()), item[0])):
        print(f"{set_id:<16} {str(names[set_id])[:40]:<40} {sum(counts.values()):>7}  "
              + ', '.join(f'{k} {v}' for k, v in sorted(counts.items())))
    if args.csv:
        with open(args.csv, 'w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(missing)
        print(f'wrote {len(missing)} rows to {args.csv}')


if __name__ == '__main__':
    main()
