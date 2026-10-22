"""Offline gate replay, using the frozen PR #65 panel and its full-pipeline answers.

No scan uploads, result writes or network access. A base-card response requiring
printing selection is correct only when the true printing is actually offered.
Missing real phone payloads remain skipped, never replaced with server vectors.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.recognition.local_match import FULL_ART_BOX, FULL_ART_RARITIES, LocalArtworkVerifier
from app.recognition.stage1_answer import evaluate_stage1
from app.recognition.stage1_gate import GateOptions, collapse_hits, load_catalogue, lookup, printing_group, same_card
from app.scan_summary import parse_quad


def replay(panel: Path, real_fixture: Path) -> dict:
    rows = [json.loads(line) for line in (panel / 'stage0.jsonl').read_text().splitlines()]
    cases = {row['id']: row for row in json.loads((panel / 'cases.json').read_text())}
    full = {row['id']: row for row in map(json.loads, (panel / 'replay.jsonl').read_text().splitlines())}
    ids = np.load(panel / 'kit/vectors/pad/embedding_card_ids.npy', allow_pickle=False).astype(str).tolist()
    embeddings = np.asarray(np.load(panel / 'kit/vectors/pad/embeddings.npy'), dtype=np.float32)
    embeddings /= np.clip(np.linalg.norm(embeddings, axis=1, keepdims=True), 1e-8, None)
    source = sqlite3.connect(f'file:{panel / "kit/catalog.sqlite"}?mode=ro', uri=True)
    catalog = sqlite3.connect(':memory:')
    source.backup(catalog)
    source.close()
    catalog.row_factory = sqlite3.Row
    # The PR #65 pack omitted operational set_totals (its table has zero rows).
    # Replay against a frozen, public-only read of staging's printed totals;
    # never modify the kit or fetch catalogue data while replaying.
    totals = json.loads(real_fixture.with_name('stage1-set-totals-20261022.json').read_text())
    catalog.executemany('INSERT OR REPLACE INTO set_totals(language,set_id,official_total,fetched_at) VALUES (?,?,?,?)',
                       [(row['language'],row['set_id'],row['official_total'],'2026-10-22') for row in totals])
    verifier = LocalArtworkVerifier(panel / 'kit')
    verifier.reference_boxes = {row['id']: FULL_ART_BOX for row in catalog.execute('SELECT id,rarity FROM cards')
                                if str(row['rarity'] or '').casefold() in FULL_ART_RARITIES}
    runtime = SimpleNamespace(snapshot=SimpleNamespace(embeddings=embeddings, card_ids=ids), artwork_verifier=verifier)
    results = {}
    for mode in ('before', 'after'):
        settings = SimpleNamespace(stage1b_text_verify=True,
            **{'stage1_' + key: mode == 'after' for key in GateOptions.__dataclass_fields__})
        found = {}
        for row in rows:
            case = cases[row['id']]
            decision = evaluate_stage1(settings=settings, runtime=runtime, catalog=catalog,
                client_text=row.get('client_text'), client_embedding=row.get('client_embedding'),
                card_quad=parse_quad(row.get('card_quad')), image_bytes=(panel / 'panel' / case['photo_file']).read_bytes())
            correct = None
            if decision.answered:
                offered = decision.printing_ids or (decision.card_id,)
                correct = any(same_card(card, expected) for card in offered for expected in case['expected_card_ids'])
            found[row['id']] = {**asdict(decision), 'correct': correct,
                'final_card': decision.card_id if decision.answered else full[row['id']]['card_id']}
        results[mode] = found
    before, after = results['before'], results['after']
    baseline = {row['id']: row for row in json.loads((panel / 'stage1.json').read_text())['comparison']['AB']['margin_ge_0.02']['answers']}
    baseline.update({row['id']: row for row in json.loads((panel / 'stage1b.json').read_text())['answers']})
    assert {key for key, value in before.items() if value['answered']} == set(baseline), 'baseline panel drift'
    assert len(baseline) == 53
    for key, spec in baseline.items():
        assert same_card(before[key]['card_id'], spec['card']) and spec['correct']
    for mode in results:
        assert all(row['correct'] is not False for row in results[mode].values()), f'{mode}: wrong early answer'
    for key, row in before.items():
        if row['answered']:
            assert after[key]['answered'] and same_card(row['card_id'], after[key]['card_id']), 'an original early answer changed'
            assert row['stage'] == after[key]['stage'], 'an original early-answer stage changed'
    unaffected_changes = [key for key in after if not after[key]['answered'] and
                          not same_card(before[key]['final_card'], after[key]['final_card']) and
                          before[key]['final_card'] != after[key]['final_card']]
    assert not unaffected_changes, 'a fallback answer changed'
    summary = {
        'photos': len(rows),
        'before_answers': sum(row['answered'] for row in before.values()),
        'after_answers': sum(row['answered'] for row in after.values()),
        'after_stages': dict(Counter(row['stage'] for row in after.values() if row['answered'])),
        'wrong': sum(row['correct'] is False for row in after.values()),
        'added': [key for key in after if after[key]['answered'] and not before[key]['answered']],
        'lost': [key for key in before if before[key]['answered'] and not after[key]['answered']],
        'printing_choice_photos': [key for key in after if after[key]['answered'] and after[key]['printing_ids']],
        'unchanged_fallback_answers': sum(not row['answered'] for row in after.values()),
        'unaffected_answer_changes': unaffected_changes,
    }
    options = GateOptions(True, True, True, True, True)
    position = {card_id: i for i, card_id in enumerate(ids)}
    fixture = json.loads(real_fixture.read_text())
    real_catalog = sqlite3.connect(':memory:')
    real_catalog.row_factory = sqlite3.Row
    fields = list(fixture['cards'][0])
    real_catalog.execute('CREATE TABLE cards (' + ','.join(key + ' TEXT' for key in fields) + ')')
    real_catalog.executemany('INSERT INTO cards VALUES ('+','.join('?' for _ in fields)+')',
                            [[card.get(key) for key in fields] for card in fixture['cards']])
    real_catalog.execute('CREATE TABLE set_totals(language TEXT,set_id TEXT,official_total INTEGER)')
    real_catalog.executemany('INSERT INTO set_totals VALUES (?,?,?)',
                            [(row['language'],row['set_id'],row['official_total']) for row in totals])
    by_key, by_id, bare = load_catalogue(real_catalog, options)
    real = []
    for scan in fixture['scans']:
        text = scan['client_text'] or {}
        hits = collapse_hits(lookup(by_key, text.get('name'), text.get('number'), None, options), bare)
        base, printings = printing_group(hits, embeddings, position)
        real.append({'id': scan['id'], 'before_reason': scan['before_reason'],
            'text_candidates_after': [card['id'] for card in hits],
            'text_identity_after': base['id'] if base else hits[0]['id'] if len(hits) == 1 else None,
            'printing_choices': printings,
            'gate_replay': 'skipped_missing_phone_vector_and_corners' if scan['embedding_observed'] else 'no_embedding',
            'actual_phone_text_present': scan['client_text'] is not None})
    a, b = embeddings[position['en:sv04-159']], embeddings[position['en:PPS5-PAR-159']]
    summary['energy_reference_cosine'] = float(a @ b)
    catalog.close()
    real_catalog.close()
    return {'summary': summary, 'panel': results, 'real_scans': real,
            'set_total_snapshot_rows': len(totals),
            'real_scan_limit': 'Six observed vectors and all numeric quads were not retained. User confirmed no saved requests. No real-vector success claim.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[2]
    parser.add_argument('--panel', type=Path, default=root / 'data/latency/stage0-simulation-20261021')
    parser.add_argument('--real-fixture', type=Path, default=root / 'api/tests/fixtures/stage1-real-scans-20261022.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = replay(args.panel, args.real_fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result['summary'], indent=2))
    print(json.dumps(result['real_scans'], indent=2))


if __name__ == '__main__':
    main()
