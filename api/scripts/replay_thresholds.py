"""Score match thresholds against the labelled set, without rerunning models.

Each labelled scan's stored ranking goes back through `decide_status` with a
grid of thresholds. A scan counts as a correct match when the replay says
matched and the top card is the one the user chose. Precision is correct
matches over all matches; coverage is matches over all labelled scans.

The replay covers the threshold decision only. Later steps (printing review,
framing review) can still lower a match, so a result here is an upper bound
on coverage, not a promise. Apply a chosen set through THRESHOLD_MIN_VISUAL,
THRESHOLD_MIN_VISUAL_OCR and THRESHOLD_MIN_GAP, then confirm it on staging.

    python scripts/replay_thresholds.py labels.jsonl --precision 0.99
"""
from __future__ import annotations

import argparse
from itertools import product
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.recognition.rank import decide_status  # noqa: E402


def _grid(start: float, stop: float, step: float) -> list[float]:
    values, value = [], start
    while value <= stop + 1e-9:
        values.append(round(value, 4))
        value += step
    return values


def score(labels: list[dict], *, min_visual: float, min_visual_ocr: float, min_gap: float) -> dict:
    matched = correct = 0
    for label in labels:
        ranking = label.get('ranking') or []
        status = decide_status(ranking, enable_matched=True, min_visual=min_visual,
                               min_visual_ocr=min_visual_ocr, min_gap=min_gap,
                               retake=label.get('status') == 'retake')
        if status != 'matched':
            continue
        matched += 1
        if not label.get('rejected') and ranking[0].get('card_id') == label.get('chosen_card_id'):
            correct += 1
    total = len(labels)
    return dict(min_visual=min_visual, min_visual_ocr=min_visual_ocr, min_gap=min_gap,
                matched=matched, correct=correct,
                precision=round(correct / matched, 4) if matched else None,
                coverage=round(matched / total, 4) if total else None)


def sweep(labels: list[dict], *, visual, visual_ocr, gap) -> list[dict]:
    return [score(labels, min_visual=v, min_visual_ocr=o, min_gap=g)
            for v, o, g in product(visual, visual_ocr, gap) if o <= v]


def best(rows: list[dict], precision: float) -> dict | None:
    ok = [r for r in rows if r['precision'] is not None and r['precision'] >= precision]
    return max(ok, key=lambda r: (r['coverage'], r['min_visual'], r['min_gap']), default=None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('labels', type=Path)
    parser.add_argument('--precision', type=float, default=0.99)
    parser.add_argument('--current', default='0.78,0.70,0.04', help='visual,visual_ocr,gap in use today')
    parser.add_argument('--out', type=Path, help='write every grid row as JSON')
    args = parser.parse_args()
    labels = [json.loads(line) for line in args.labels.read_text().splitlines() if line.strip()]
    if not labels:
        sys.exit('No labelled scans yet.')
    v, o, g = (float(x) for x in args.current.split(','))
    current = score(labels, min_visual=v, min_visual_ocr=o, min_gap=g)
    rows = sweep(labels, visual=_grid(.60, .95, .01), visual_ocr=_grid(.55, .90, .01),
                 gap=_grid(0., .10, .01))
    chosen = best(rows, args.precision)
    print(f'{len(labels)} labelled scans')
    print(f'current  {json.dumps(current)}')
    print(f'best at precision >= {args.precision}: {json.dumps(chosen) if chosen else "none reaches it"}')
    if len(labels) < 300:
        print('Fewer than 300 labels: treat this as a hint, not a setting to ship.')
    if args.out:
        args.out.write_text(json.dumps(rows, indent=1))


if __name__ == '__main__':
    main()
