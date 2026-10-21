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


def test_panel_matches_the_measured_stage1_and_stage1b_answers():
    from app.recognition.local_match import FULL_ART_BOX, FULL_ART_RARITIES, LocalArtworkVerifier
    from app.recognition.stage1_answer import evaluate_stage1
    from app.recognition.stage1_gate import same_card
    from app.scan_summary import parse_quad
    import sqlite3

    rows = [json.loads(line) for line in (PANEL / 'stage0.jsonl').read_text().splitlines()]
    cases = {case['id']: case for case in json.loads((PANEL / 'cases.json').read_text())}
    stage1 = json.loads((PANEL / 'stage1.json').read_text())
    stage1b = json.loads((PANEL / 'stage1b.json').read_text())
    expected_stage1 = {item['id']: item for item in stage1['comparison']['AB']['margin_ge_0.02']['answers']}
    expected_stage1b = {item['id']: item for item in stage1b['answers']}
    assert len(expected_stage1) == 40 and len(expected_stage1b) == 13

    ids = np.load(PANEL / 'kit/vectors/pad/embedding_card_ids.npy', allow_pickle=False).astype(str)
    index = np.asarray(np.load(PANEL / 'kit/vectors/pad/embeddings.npy', mmap_mode='r'), dtype=np.float32)
    index = index / np.clip(np.linalg.norm(index, axis=1, keepdims=True), 1e-8, None)
    catalog = sqlite3.connect(PANEL / 'kit/catalog.sqlite')
    catalog.row_factory = sqlite3.Row
    verifier = LocalArtworkVerifier(PANEL / 'kit')
    verifier.reference_boxes = {
        str(row['id']): FULL_ART_BOX for row in catalog.execute('SELECT id, rarity FROM cards')
        if str(row['rarity'] or '').casefold() in FULL_ART_RARITIES}
    runtime = SimpleNamespace(
        snapshot=SimpleNamespace(embeddings=index, card_ids=ids.tolist()),
        artwork_verifier=verifier)
    settings = SimpleNamespace(stage1b_text_verify=True)

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
        assert spec['correct']
    assert len(got_stage1) + len(got_stage1b) == 53
