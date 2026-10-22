"""The stage 1 gate, on the simulated phone fields, matches the measured 40 + 13 answers."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

PANEL = Path(__file__).resolve().parents[2] / 'data/latency/stage0-simulation-20261021'

pytestmark = pytest.mark.skipif(
    not (PANEL / 'stage0.jsonl').is_file() or not (PANEL / 'kit/vectors/pad/embeddings.npy').is_file(),
    reason='stage 0 simulation panel is not in this checkout')


@pytest.mark.parametrize('real_fixes', [False, True], ids=['flags-off', 'real-fixes-on'])
def test_panel_matches_the_measured_stage1_and_stage1b_answers(real_fixes):
    from app.recognition.local_match import FULL_ART_BOX, FULL_ART_RARITIES, LocalArtworkVerifier
    from app.recognition.stage1_answer import evaluate_stage1
    from app.recognition.stage1_gate import GateOptions, same_card
    from app.scan_summary import parse_quad
    import sqlite3

    rows = [json.loads(line) for line in (PANEL / 'stage0.jsonl').read_text().splitlines()]
    cases = {case['id']: case for case in json.loads((PANEL / 'cases.json').read_text())}
    stage1 = json.loads((PANEL / 'stage1.json').read_text())
    stage1b = json.loads((PANEL / 'stage1b.json').read_text())
    expected_stage1 = {item['id']: item for item in stage1['comparison']['AB']['margin_ge_0.02']['answers']}
    expected_stage1b = {item['id']: item for item in stage1b['answers']}
    assert len(expected_stage1) == 40 and len(expected_stage1b) == 13
    if real_fixes:
        expected_stage1.update({key: {'card': card, 'correct': True} for key, card in (
            ('fresh100_196431506881', 'en:pop9-15'),
            ('fresh100_227337115305', 'en:base5-21'),
            ('fresh100_196323744191', 'en:base1-6'))})
        expected_stage1b.update({key: {'card': card, 'correct': True} for key, card in (
            ('holdout4_080', 'en:base1-68'),
            ('phone_5085926a-1afb-4505-88a9-c2f23fae34ba', 'en:base1-24'))})

    ids = np.load(PANEL / 'kit/vectors/pad/embedding_card_ids.npy', allow_pickle=False).astype(str)
    index = np.asarray(np.load(PANEL / 'kit/vectors/pad/embeddings.npy', mmap_mode='r'), dtype=np.float32)
    index = index / np.clip(np.linalg.norm(index, axis=1, keepdims=True), 1e-8, None)
    source = sqlite3.connect(f'file:{PANEL / "kit/catalog.sqlite"}?mode=ro', uri=True)
    catalog = sqlite3.connect(':memory:')
    source.backup(catalog)
    source.close()
    catalog.row_factory = sqlite3.Row
    totals = json.loads((Path(__file__).parent / 'fixtures/stage1-set-totals-20261022.json').read_text())
    catalog.executemany('INSERT OR REPLACE INTO set_totals(language,set_id,official_total,fetched_at) VALUES (?,?,?,?)',
                       [(r['language'],r['set_id'],r['official_total'],'2026-10-22') for r in totals])
    verifier = LocalArtworkVerifier(PANEL / 'kit')
    verifier.reference_boxes = {
        str(row['id']): FULL_ART_BOX for row in catalog.execute('SELECT id, rarity FROM cards')
        if str(row['rarity'] or '').casefold() in FULL_ART_RARITIES}
    runtime = SimpleNamespace(
        snapshot=SimpleNamespace(embeddings=index, card_ids=ids.tolist()),
        artwork_verifier=verifier)
    settings = SimpleNamespace(stage1b_text_verify=True,
        **{'stage1_' + name: real_fixes for name in GateOptions.__dataclass_fields__})

    got_stage1 = {}
    got_stage1b = {}
    for row in rows:
        photo = (PANEL / 'panel' / cases[row['id']]['photo_file']).read_bytes()
        decision = evaluate_stage1(
            settings=settings, runtime=runtime, catalog=catalog,
            client_text=row.get('client_text'), client_embedding=row.get('client_embedding'),
            card_quad=parse_quad(row.get('card_quad')), image_bytes=photo)
        if not decision.answered:
            continue
        target = got_stage1 if decision.stage == '1' else got_stage1b
        target[row['id']] = decision

    assert set(got_stage1) == set(expected_stage1)
    assert set(got_stage1b) == set(expected_stage1b)
    for photo_id, decision in {**got_stage1, **got_stage1b}.items():
        spec = expected_stage1.get(photo_id) or expected_stage1b[photo_id]
        assert decision.card_id and same_card(decision.card_id, spec['card'])
        assert any(same_card(decision.card_id, truth) for truth in cases[photo_id]['expected_card_ids'])
        assert spec['correct']
    assert len(got_stage1) + len(got_stage1b) == (58 if real_fixes else 53)
