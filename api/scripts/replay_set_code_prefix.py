"""Replay the OCR_SET_CODE_PREFIX parser change over stored scans, flag off against on.

Read-only. Nothing is uploaded and no scan is written. Photos and OCR text are never
stored here: the staging cases are fetched into a local scratch folder you choose
(outside git) and the output holds only scan-id prefixes, statuses and card ids.

    # 1. Pull the trimmed stored fields of the report's scans (read-only on the volume):
    python api/scripts/replay_set_code_prefix.py fetch --ids ids.txt --out SCRATCH/cases.json
    # 2. Replay them (rank + status decision on the stored visual top 20):
    python api/scripts/replay_set_code_prefix.py cases --cases SCRATCH/cases.json
    # 3. Replay the frozen 157 panel (number agreement against the labelled card):
    python api/scripts/replay_set_code_prefix.py panel --replay data/latency/stage0-simulation-20261021/replay.jsonl

A "wrong answer" here is: with the flag on, a number reading agrees with a card that is
not the labelled/true one, or a scan becomes `matched` on a card other than the true one, or
the top card moves to one that is not the true card. Exit code 1 when any is found.
The staging replay covers rank + status only (not local artwork or later pipeline steps).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.recognition import rank  # noqa: E402
from app.recognition.identity import structured_identity_agrees  # noqa: E402
from app.recognition.ocr import OcrHit  # noqa: E402

# Identity of the 7 parser-affected scans as established by hand in the report
# (docs/experiments/live-android-uncertain-scans-20261025.md). Card ids only.
TRUTH = {'0c8772bf': 'en:30th-077', '903af2db': 'en:30th-077', '0b28268b': 'en:30th-077',
         '63a29eef': 'en:30th-077', '2e503903': 'en:30th-095', '8fd2e758': 'en:mep-078',
         '94a13d29': 'en:mep-078'}
CONTAINER = 'scanapp-scanapp-z1mwj4-api-1'
REMOTE = r'''
import json, sys
ids = IDS
out = []
for name in sorted(__import__('os').listdir('/data/review/cases')):
    if name[:8] not in ids:
        continue
    d = json.load(open('/data/review/cases/' + name))
    o = d.get('ocr') or {}
    out.append({'scan_id': d['scan_id'], 'status': d.get('status'), 'confirmed_card_id': d.get('confirmed_card_id'),
                'ocr': {k: o.get(k) for k in ('name_text', 'collector_text', 'lines', 'hits', 'failed',
                                              'detected_language', 'search_languages')},
                'visual_top20': d.get('visual_top20')})
print(json.dumps(out))
'''


def fetch(ids_file: Path, out: Path, host: str) -> None:
    ids = [line.strip() for line in ids_file.read_text().split() if line.strip()]
    result = subprocess.run(
        ['ssh', host, 'docker', 'exec', '-i', CONTAINER, 'python3', '-'],
        input=REMOTE.replace('IDS', json.dumps(ids), 1), capture_output=True, text=True, check=True)
    cases = json.loads(result.stdout.strip().splitlines()[-1])
    out.write_text(json.dumps(cases))
    print(f'fetched {len(cases)} of {len(ids)} cases')


def set_and_number(card_id: str) -> tuple[str, str]:
    body = card_id.split(':', 1)[-1]
    set_id, _, number = body.rpartition('-')
    return set_id.lower(), number


def card_row(row: dict) -> dict:
    set_id, number = set_and_number(row['card_id'])
    return {**row, 'set_id': set_id, 'collector_number': row.get('collector_number') or number}


def numbers_for(ocr: dict, on: bool) -> list[OcrHit]:
    rank.set_code_prefix_enabled = lambda: on
    hits = [OcrHit(h['text'], h.get('confidence'), h.get('region', 'unknown')) for h in ocr.get('hits') or []]
    lines = [line for line in [ocr.get('collector_text'), *(ocr.get('lines') or [])] if line]
    return rank.extract_collector_candidates(lines, hits=hits)


def decide(case: dict, on: bool) -> tuple[str, list[dict], list[OcrHit]]:
    settings = get_settings()
    numbers = numbers_for(case['ocr'], on)
    visual = [card_row(r) for r in case['visual_top20']]
    ocr = case['ocr']
    name = ocr.get('name_text')
    name_conf = max((h.get('confidence') or 0.0 for h in ocr.get('hits') or []
                     if h.get('text') == name and h.get('region') == 'name'), default=0.0)
    ranked = rank.rerank(visual, name, numbers, bool(ocr.get('failed')),
                         detected_languages=tuple(ocr.get('search_languages') or ()),
                         name_confidence=name_conf, require_confident_ocr=True)
    status, _ = rank.decide_status_with_reason(
        ranked, enable_matched=settings.enable_matched, min_visual=settings.threshold_min_visual,
        min_visual_ocr=settings.threshold_min_visual_ocr, min_gap=settings.threshold_min_gap, retake=False)
    # The pipeline turns a below-floor no_match into a reviewable `uncertain` when name and an
    # explicit number agree (framing_review_rescue). Local artwork and the other later steps
    # are not replayed, so a replayed `matched` can still end as `uncertain` in production.
    if (status == 'no_match' and ranked and float(ranked[0]['visual_score']) >= settings.threshold_min_visual_ocr
            and structured_identity_agrees(ranked[0], ocr_name=name, name_confidence=name_conf,
                                           numbers=numbers, languages=tuple(ocr.get('search_languages') or ()))):
        status = 'uncertain'
    return status, ranked, numbers


def run_cases(path: Path) -> int:
    cases = json.loads(path.read_text())
    rows, changed, wrong = [], [], []
    for case in cases:
        if not case.get('visual_top20'):
            continue
        before, ranked_off, nums_off = decide(case, False)
        after, ranked_on, nums_on = decide(case, True)
        top_off, top_on = ranked_off[0]['card_id'], ranked_on[0]['card_id']
        row = {'id': case['scan_id'][:8], 'stored_status': case['status'], 'off': before, 'on': after,
               'top_off': top_off, 'top_on': top_on, 'numbers_changed': [h.text for h in nums_off] != [h.text for h in nums_on],
               'conflict_off': bool(ranked_off[0].get('collector_conflict')),
               'conflict_on': bool(ranked_on[0].get('collector_conflict'))}
        rows.append(row)
        if (before, top_off) != (after, top_on):
            changed.append(row)
        # No labels exist for these scans. The visual leader that the report verified is the
        # identity; a top card that moves, or a match on a card whose name disagrees, is flagged.
        truth = TRUTH.get(row['id'])
        row['truth'] = truth
        if after == 'matched' and truth and top_on != truth:
            wrong.append(row)      # automatic answer on the wrong card
        elif after == 'matched' and not truth and before != 'matched':
            wrong.append(row)      # a scan with no known truth newly reaching matched
        elif top_on != top_off and top_on != truth:
            wrong.append(row)      # top card moved to something that is not the true card
    fidelity = sum(r['off'] == r['stored_status'] for r in rows)
    print(json.dumps({'cases': len(rows), 'off_equals_stored_status': fidelity,
                      'numbers_changed': sum(r['numbers_changed'] for r in rows),
                      'conflict_cleared': [r['id'] for r in rows if r['conflict_off'] and not r['conflict_on']],
                      'status_or_top_changed': changed,
                      'wrong_or_unverifiable_changes': wrong}, indent=1))
    return 0 if not wrong else 1


def run_panel(path: Path) -> int:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    different, wrong = [], []
    for row in rows:
        ocr = row.get('ocr') or {}
        off, on = numbers_for(ocr, False), numbers_for(ocr, True)
        if [h.text for h in off] == [h.text for h in on]:
            continue
        cards = [card_row({'card_id': c}) for c in {*(row.get('alternatives') or []), row.get('card_id'), *(row.get('expected') or [])} if c]
        truth = set(row.get('expected') or [])
        verdicts = {}
        for flag, hits in (('off', off), ('on', on)):
            rank.set_code_prefix_enabled = lambda flag=flag: flag == 'on'
            verdicts[flag] = {c['card_id']: rank.number_matches_identifiers(hits, rank.accepted_collector_numbers(c))
                              for c in cards}
        different.append({'id': row['id'], 'off': verdicts['off'], 'on': verdicts['on']})
        for card_id, verdict in verdicts['on'].items():
            if verdict is True and verdicts['off'][card_id] is not True and card_id not in truth:
                wrong.append({'id': row['id'], 'card': card_id})
    print(json.dumps({'photos': len(rows), 'photos_whose_numbers_change': len(different),
                      'changes': different, 'new_agreement_with_a_non_labelled_card': wrong}, indent=1))
    return 0 if not wrong else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)
    f = sub.add_parser('fetch')
    f.add_argument('--ids', type=Path, required=True)
    f.add_argument('--out', type=Path, required=True)
    f.add_argument('--host', default='auctaro-staging')
    c = sub.add_parser('cases')
    c.add_argument('--cases', type=Path, required=True)
    p = sub.add_parser('panel')
    p.add_argument('--replay', type=Path, required=True)
    args = parser.parse_args()
    if args.cmd == 'fetch':
        fetch(args.ids, args.out, args.host)
        return 0
    return run_cases(args.cases) if args.cmd == 'cases' else run_panel(args.replay)


if __name__ == '__main__':
    raise SystemExit(main())
