"""Replay VINTAGE_NAME_CHOICES on stored scans: which scans would offer extra cards,
and whether the card the collector confirmed is among them.

    cd api && .venv/bin/python scripts/stored_scan_replay/replay_vintage_name.py \
        <work>/cases.jsonl --catalog <export>/catalog.sqlite

The switch only adds choices to scans that already need confirmation; the card shown
first and the status never change, so there is no first-card diff to review. What to
check: each listed scan, and above all any 'offered_but_confirmed_other' (noise shown
to a collector) and 'confirmed_offered' (the card the collector wanted). Cases from an
export without 'confirmed' count as unknown. Prints card ids and names only.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.recognition.ocr import OcrHit
from app.recognition.rank import extract_collector_candidates
from app.recognition.vintage_name import vintage_name_choices


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cases')
    ap.add_argument('--catalog', required=True)
    args = ap.parse_args()
    catalog = sqlite3.connect(f'file:{args.catalog}?mode=ro', uri=True)
    catalog.row_factory = sqlite3.Row
    names = lambda ids: {r['id']: r['name'] for r in catalog.execute(
        f"SELECT id, name FROM cards WHERE id IN ({','.join('?' for _ in ids)})", ids)} if ids else {}

    reasons, outcomes = Counter(), Counter()
    for line in open(args.cases):
        case = json.loads(line)
        if '_settings' in case or case.get('status') not in {'uncertain', 'printing_ambiguous'}:
            continue
        hits = [OcrHit(h['text'], h.get('confidence'), h.get('region') or 'unknown')
                for h in case.get('hits') or [] if h.get('text')]
        numbers = extract_collector_candidates(
            [x for x in [case.get('collector'), *(case.get('lines') or [])] if x], hits=hits)
        shown = (case.get('pred') or [{}])[0].get('card_id')
        ids, reason = vintage_name_choices(catalog, hits=hits, numbers=numbers,
                                           languages=(case['lang'],) if case.get('lang') else (),
                                           exclude={shown, *(case.get('review') or [])} - {None})
        reasons[reason] += 1
        if not ids:
            continue
        confirmed = case.get('confirmed')
        outcome = ('unknown' if 'confirmed' not in case else 'not_confirmed' if not confirmed
                   else 'confirmed_offered' if confirmed in ids
                   else 'confirmed_shown' if confirmed == shown
                   else 'offered_but_confirmed_other')
        outcomes[outcome] += 1
        label = names([shown, *ids, *([confirmed] if confirmed else [])] if shown else ids)
        print(json.dumps({'scan': (case.get('id') or '')[:8], 'date': case.get('created'),
                          'status': case['status'], 'shown': [shown, label.get(shown)],
                          'offered': [[i, label.get(i)] for i in ids],
                          'confirmed': [confirmed, label.get(confirmed)] if confirmed else None,
                          'outcome': outcome}, ensure_ascii=False))
    print(json.dumps({'reasons': reasons, 'offered_outcomes': outcomes}))


if __name__ == '__main__':
    main()
