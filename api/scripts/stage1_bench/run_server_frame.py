"""Offline stage 1b on the server's own frame, with and without STAGE1B_FRAME_FALLBACK.

Plan 2026-10-26, step 3. For each stored Android manual upload with a known card, this calls the real
``evaluate_stage1`` with no phone embedding (the case that reaches ``_evaluate_server_frame``), the real
server frame finder, the real DINOv2 embedder, and the real local artwork check on the reference images.
Only the frame differs between the two runs: the server frame, or the fallback when the server finds none.

    api/.venv/bin/python api/scripts/stage1_bench/run_server_frame.py --cases <dir> [--fallback] [--out f.json]

Counts and scan ids only go to stdout; photos stay in the scratch folder.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from PIL import Image

API = Path(__file__).resolve().parents[2]
REPO = API.parent
sys.path.insert(0, str(API))
sys.path.insert(0, str(API / 'scripts'))
sys.path.insert(0, str(API / 'scripts' / 'stage1_bench'))

import android_fastpath_replay as replay  # noqa: E402
import run_bench as rb  # noqa: E402
from app.recognition.stage1_answer import evaluate_stage1  # noqa: E402
from app.recognition.stage1_gate import same_card  # noqa: E402
from dataclasses import fields  # noqa: E402

DATA = REPO / 'data' / 'android-embedding-research-20261023'


def scratch_kit(root: Path) -> Path:
    """The layout the replay runtime expects: catalog.sqlite, vectors/pad and reference-images."""
    kit = root / 'kit'
    kit.mkdir(parents=True, exist_ok=True)
    for name, target in (('catalog.sqlite', DATA / 'catalogue' / 'catalog.sqlite'),
                         ('vectors', DATA / 'catalogue' / 'vectors'),
                         ('reference-images', DATA / 'reference-images')):
        link = kit / name
        if not link.exists():
            link.symlink_to(target, target_is_directory=target.is_dir())
    return kit


def settings_for(fallback: bool, family: bool) -> SimpleNamespace:
    staging = rb.staging_options(family)
    values = {'stage1_' + f.name: getattr(staging, f.name) for f in fields(staging)}
    values.update(stage1b_server_frame=True, stage1b_text_verify=True,
                  stage1b_frame_fallback=fallback, stage1_require_confirmation=True)
    return SimpleNamespace(**values)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, default=Path('/tmp/stage1_server_frame'))
    parser.add_argument('--fallback', action='store_true')
    parser.add_argument('--family', action='store_true')
    parser.add_argument('--text', choices=('server', 'oracle'), default='server')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()

    kit = scratch_kit(args.scratch)
    totals = API / 'tests' / 'fixtures' / 'stage1-set-totals-20261022.json'
    runtime, catalog = replay.build_runtime(kit, totals, model=DATA / 'teacher' / 'dinov2_small.onnx')
    settings = settings_for(args.fallback, args.family)
    cases = json.loads((args.cases / 'android_cases.json').read_text())
    rows, counts = [], Counter()
    for case in cases:
        label = rb.OWNER.get((case.get('ocr_name') or case.get('top_name') or '').strip().lower())
        if label is None:
            continue
        name, number = rb.text_of(case, None, 'server')
        if args.text == 'oracle':
            label_row = catalog.execute('select name, collector_number from cards where id=?', (label,)).fetchone()
            if label_row is not None:
                total = rb.TOTAL.get(label)
                name = label_row['name']
                number = f"{label_row['collector_number']}/{total}" if total else label_row['collector_number']
        text = json.dumps({'name': name, 'number': number})
        image_bytes = (args.cases / case['input']).read_bytes()
        decision = evaluate_stage1(settings=settings, runtime=runtime, catalog=catalog, client_text=text,
                                   client_embedding=None, card_quad=None, image_bytes=image_bytes)
        stored = case.get('top')
        row = {'scan': case['scan'], 'label': label, 'reason': decision.reason, 'stage': decision.stage,
               'card': decision.card_id, 'answered': decision.answered}
        if decision.answered:
            row['correct'] = bool(decision.card_id and same_card(decision.card_id, label))
            row['agrees_with_full'] = bool(stored and decision.card_id and same_card(decision.card_id, stored))
            counts['early'] += 1
            counts['early_wrong'] += int(not row['correct'])
            counts['early_disagree_full'] += int(not row['agrees_with_full'])
        else:
            counts['reason:' + decision.reason] += 1
        rows.append(row)
    summary = {'fallback': args.fallback, 'family': args.family, 'text': args.text,
               'labelled_uploads': len(rows), 'counts': dict(counts)}
    print(json.dumps(summary, indent=2, sort_keys=True))
    if args.out:
        args.out.write_text(json.dumps({'summary': summary, 'rows': rows}, indent=2))


if __name__ == '__main__':
    main()
