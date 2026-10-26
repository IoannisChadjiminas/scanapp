"""Offline stage 1 benchmark on stored Android manual uploads (plan 2026-10-26, step 1).

For each stored upload whose card is known from the owner's list, this builds the
phone's inputs the way the app does for a manual photo: the vector of a whole-card
crop (the guide, which the fixed outline gives), and the text as the server read it.
It then runs the real ``decide`` gate with the staging flag set from the compose file,
and reports early answers, wrong early answers, disagreements with the stored
full-pipeline answer, and the stage 1b candidates (those still need the artwork check,
which this benchmark does not run).

    api/.venv/bin/python api/scripts/stage1_bench/run_bench.py \\
        --cases <folder with android_cases.json and images/> \\
        --data data/android-embedding-research-20261023 \\
        [--family] [--out result.json]

Photos and results stay in the scratch folder; print only counts and scan ids.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import fields
import json
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
from PIL import Image

API = Path(__file__).resolve().parents[2]
REPO = API.parent
sys.path.insert(0, str(API))
sys.path.insert(0, str(API / 'scripts' / 'instant'))

from app.recognition.stage1_gate import GateOptions, decide, load_catalogue, same_card  # noqa: E402
import index_formats as idx  # noqa: E402
from embedder import OnnxEmbedder  # noqa: E402

# The owner's cards, by the name the server reads (the owner's list, 2026-10-25/26).
OWNER = {
    'comfey': 'en:30th-077', 'zorua': 'en:30th-095', 'toxel': 'en:mep-078',
    'ancient booster energy capsule': 'en:sv04-159', 'brute bonnet': 'en:sv04-123',
    'charmander': 'en:xy12-9', 'charmeleon': 'base1-24', 'pikachu': 'en:xy12-35',
}
# Printed set totals of the owner's cards (the footer reads "35/108"). The oracle text needs them:
# a bare number matches several sets, and the gate correctly refuses to choose between them.
TOTAL = {'en:30th-077': 128, 'en:30th-095': 128, 'en:xy12-35': 108, 'en:xy12-9': 108,
         'base1-24': 102, 'en:sv04-159': 182, 'en:sv04-123': 182}
NUMBER = re.compile(r'(\d{1,3})\s*/\s*(\d{1,3})')
FLAG = re.compile(r'^\s*(STAGE1_[A-Z_]+):\s*\$\{[A-Z0-9_]+:-(true|false)\}', re.M)


def staging_options(family: bool) -> GateOptions:
    """The gate flags staging runs with, read from compose.dokploy.yaml."""
    flags = {key: value == 'true' for key, value in FLAG.findall((REPO / 'compose.dokploy.yaml').read_text())}
    values = {}
    for field in fields(GateOptions):
        values[field.name] = flags.get('STAGE1_' + field.name.upper(), False)
    values['family_vector'] = family
    return GateOptions(**values)


def whole_card(image: Image.Image) -> Image.Image:
    """The guide crop as the fixed outline gives it: the card fills the photo."""
    w, h = image.size
    return image.crop((int(w * .01), int(h * .012), int(w * .99), int(h * .988)))


def text_of(case: dict, label_row: dict | None, mode: str) -> tuple[str | None, str | None]:
    """The text the gate gets. ``server``: the server's own read (a lower bound on what the phone sends).
    ``oracle``: the labelled card's name and collector number, read correctly (what good text would give).
    The oracle mode is the safety test for the family rule: a right printing from the text, with a
    same-name reprint leading the artwork."""
    if mode == 'oracle' and label_row is not None:
        return label_row['name'], label_row['number']
    name = (case.get('ocr_name') or case.get('top_name') or '').strip() or None
    match = NUMBER.search(str(case.get('ocr_number') or ''))
    return name, (f'{match.group(1)}/{match.group(2)}' if match else None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--data', type=Path, default=REPO / 'data/android-embedding-research-20261023')
    parser.add_argument('--family', action='store_true', help='turn STAGE1_FAMILY_VECTOR on')
    parser.add_argument('--text', choices=('server', 'oracle'), default='server')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()

    vec_dir = args.data / 'catalogue' / 'vectors' / 'pad'
    ids = [str(x) for x in np.load(vec_dir / 'embedding_card_ids.npy', allow_pickle=True).tolist()]
    raw = np.load(vec_dir / 'embeddings.npy').astype(np.float32)
    embeddings = raw / np.linalg.norm(raw, axis=1, keepdims=True)
    # The research kit's set_totals table is empty; the frozen public snapshot the replay uses fills it.
    source = sqlite3.connect(f"file:{args.data / 'catalogue' / 'catalog.sqlite'}?mode=ro", uri=True)
    conn = sqlite3.connect(':memory:')
    source.backup(conn)
    source.close()
    conn.row_factory = sqlite3.Row
    conn.executemany(
        'INSERT OR REPLACE INTO set_totals(language,set_id,official_total,fetched_at) VALUES (?,?,?,?)',
        [(r['language'], r['set_id'], r['official_total'], '2026-10-22')
         for r in json.loads((API / 'tests' / 'fixtures' / 'stage1-set-totals-20261022.json').read_text())])
    options = staging_options(args.family)
    by_key, by_id, bare_ids = load_catalogue(conn, options)
    embedder = OnnxEmbedder(args.data / 'teacher' / 'dinov2_small.onnx')

    cases = json.loads((args.cases / 'android_cases.json').read_text())
    rows, counts = [], Counter()
    for case in cases:
        label = OWNER.get((case.get('ocr_name') or case.get('top_name') or '').strip().lower())
        if label is None:
            continue
        image = Image.open(args.cases / case['input']).convert('RGB')
        vector = embedder.embed_image(whole_card(image))
        if not np.all(np.isfinite(vector)):
            counts['bad_vector'] += 1
            continue
        label_row = None
        if args.text == 'oracle':
            label_id = label if label in by_id else label.removeprefix('en:')
            label_row = by_id.get(label) or by_id.get('en:' + label.removeprefix('en:'))
            if label_row is not None:
                total = TOTAL.get(label)
                number = str(label_row['collector_number'])
                label_row = {'name': label_row['name'], 'number': f'{number}/{total}' if total else number}
        name, number = text_of(case, label_row, args.text)
        # The owner's cards are English; the app sends the language it read (stage 1 narrows by it).
        decision = decide(vector, embeddings, ids, by_key=by_key, by_id=by_id, bare_ids=bare_ids,
                          name=name, number=number, language='en', quad_ok=True, stage1b=True,
                          label=False, options=options)
        stored = case.get('top')  # the stored full-pipeline top card
        row = {'scan': case['scan'], 'label': label, 'stage': decision.stage, 'reason': decision.reason,
               'card': decision.card_id, 'margin': None if decision.margin is None else round(decision.margin, 3)}
        if decision.stage == '1' and decision.answered:
            row['path'] = decision.reason
            row['correct'] = bool(decision.card_id and same_card(decision.card_id, label))
            row['agrees_with_full'] = bool(stored and decision.card_id and same_card(decision.card_id, stored))
            counts['early'] += 1
            counts['early_wrong'] += int(not row['correct'])
            counts['early_disagree_full'] += int(not row['agrees_with_full'])
        elif decision.stage == '1b_pending':
            row['correct'] = bool(decision.card_id and same_card(decision.card_id, label))
            counts['1b_candidates'] += 1
            counts['1b_wrong'] += int(not row['correct'])
        else:
            counts['abstain:' + decision.reason] += 1
        rows.append(row)

    summary = {'flags': {f.name: getattr(options, f.name) for f in fields(GateOptions)},
               'text': args.text, 'labelled_uploads': len(rows), 'counts': dict(counts)}
    print(json.dumps(summary, indent=2))
    if args.out:
        args.out.write_text(json.dumps({'summary': summary, 'rows': rows}, indent=2))


if __name__ == '__main__':
    main()
