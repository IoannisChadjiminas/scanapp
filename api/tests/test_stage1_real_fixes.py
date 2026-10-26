"""Real catalogue rows; synthetic vectors are explicitly unit-test evidence."""
import base64
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import numpy as np
import pytest

from app.config import Settings
from app.db import init_catalog, init_results
from app.recognition.stage1_gate import GateOptions, decide, load_catalogue, lookup, number_ok
from app.stage0 import PhoneEvidence, stage0_line

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/stage1-real-scans-20261022.json').read_text())
TOTALS = json.loads((Path(__file__).parent / 'fixtures/stage1-set-totals-20261022.json').read_text())
ON = GateOptions(True, True, True, True, True)


def unit(*values):
    result = np.zeros(384, np.float32)
    result[:len(values)] = values
    return result / np.linalg.norm(result)


@pytest.fixture
def catalog():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    init_catalog(conn)
    for row in FIXTURE['cards']:
        row = {**row, 'provider_id': row['id']}
        keys = list(row)
        conn.execute(f'INSERT INTO cards ({",".join(keys)}) VALUES ({",".join("?" for _ in keys)})',
                     [row[key] for key in keys])
    conn.executemany('INSERT INTO set_totals VALUES (?,?,?,?)',
                     [(r['language'],r['set_id'],r['official_total'],'2026-10-22') for r in TOTALS])
    yield conn
    conn.close()


def gate(catalog, ids, vectors, query, *, name='Ancient Booster Energy Capsule', number='159/182', options=ON):
    by_key, by_id, bare = load_catalogue(catalog, options)
    return decide(query, np.stack(vectors), ids, by_key=by_key, by_id=by_id, bare_ids=bare,
                  name=name, number=number, language=None, quad_ok=True, stage1b=True, options=options)


def test_all_new_flags_default_off_and_are_staging_only():
    off = Settings(_env_file=None)
    # number_repair is on by default (phone number candidates); the rest stay off.
    assert GateOptions.from_settings(off) == GateOptions(number_repair=True)
    repo = Path(__file__).resolve().parents[2]
    staging = (repo / 'compose.dokploy.yaml').read_text()
    # number_repair and fuzzy_name belong to the Android fast-path fixes and have their own flag test.
    # family_vector ships off in staging until the offline benchmark passes (plan 2026-10-26).
    for name in set(GateOptions.__dataclass_fields__) - {'number_repair', 'fuzzy_name', 'family_vector'}:
        key = 'STAGE1_' + name.upper()
        assert f'{key}: ${{{key}:-true}}' in staging
        for production in repo.glob('compose*prod*.yaml'):
            # Production may name a fix only to switch it explicitly off (stage1_twin_guard).
            text = production.read_text()
            assert key not in text or f'{key}: ${{{key}:-false}}' in text


@pytest.mark.parametrize(('name', 'number', 'expected'), [
    ('Pikachu', '35/108', ['en:xy12-35']),
    ('Charmeleon', '24/102', ['en:base1-24']),
    ('Comfey', '077/128', ['en:30th-077']),
])
def test_printed_set_total_and_normalized_duplicates_resolve_exact_rows(catalog, name, number, expected):
    from app.recognition.stage1_gate import collapse_hits
    by_key, _, bare = load_catalogue(catalog, ON)
    assert [r['id'] for r in collapse_hits(lookup(by_key, name, number, None, ON), bare)] == expected


def test_printed_fraction_wins_and_known_different_total_never_matches():
    card = dict(collector_number='035', printed_collector_number=None, set_total=128)
    assert number_ok('35/108', card)  # The old defect is opt-in fixed.
    assert not number_ok('35/108', card, ON)
    assert number_ok('35/128', card, ON)
    assert number_ok('35/108', {**card, 'printed_collector_number': '35/108'}, ON)
    assert not number_ok('35/128', {**card, 'collector_number': '35/128', 'printed_collector_number': '35/108'}, ON)
    assert number_ok('35/128', {**card, 'printed_collector_number': '035'}, ON)
    assert number_ok('35/108', {**card, 'set_total': None}, ON)


def test_current_charmeleon_aliases_already_collapse_with_old_rule(catalog):
    _, _, bare = load_catalogue(catalog)
    assert 'base1-24' in bare  # No field differed in the actual staging rows.


def test_aliases_normalize_set_namespace_zeroes_and_optional_printed_number(catalog):
    catalog.execute("UPDATE cards SET set_id='en:base1', collector_number='024', printed_collector_number='24/102' WHERE id='en:base1-24'")
    assert 'base1-24' not in load_catalogue(catalog)[2]
    assert 'base1-24' in load_catalogue(catalog, ON)[2]
    catalog.execute("UPDATE cards SET name='Charmeleon V' WHERE id='en:base1-24'")
    assert 'base1-24' not in load_catalogue(catalog, ON)[2]


@pytest.mark.parametrize('query', [unit(1, 0, 0), unit(.9763, .2164, 0)])
def test_prize_pack_leader_returns_base_with_mandatory_printing_choice(catalog, query):
    ids = ['en:sv04-159', 'en:PPS5-PAR-159', 'en:xy12-35']
    vectors = [unit(1, 0, 0), unit(.9763, .2164, 0), unit(0, 0, 1)]
    result = gate(catalog, ids, vectors, query)
    assert result.answered and result.card_id == 'en:sv04-159'
    assert result.printing_ids == ('en:sv04-159', 'en:PPS5-PAR-159')
    assert not gate(catalog, ids, vectors, query, options=GateOptions()).answered


def test_low_reference_similarity_and_an_unrelated_leader_still_abstain(catalog):
    ids = ['en:sv04-159', 'en:PPS5-PAR-159', 'en:xy12-35']
    low = [unit(1, 0, 0), unit(.94, .3412, 0), unit(0, 0, 1)]
    assert gate(catalog, ids, low, low[0]).reason == 'ambiguous_text'
    high = [unit(1, 0, 0), unit(.9763, .2164, 0), unit(0, 0, 1)]
    result = gate(catalog, ids, high, high[2])
    assert result.reason == 'visual_contradiction'
    assert result.contradicting_card == 'en:xy12-35' and result.contradiction_gap >= .05


def test_catalogue_reprint_link_can_group_without_reference_similarity(catalog):
    catalog.execute('ALTER TABLE cards ADD COLUMN reprint_of TEXT')
    catalog.execute("UPDATE cards SET reprint_of='en:sv04-159' WHERE id='en:PPS5-PAR-159'")
    ids = ['en:sv04-159', 'en:PPS5-PAR-159', 'en:xy12-35']
    vectors = [unit(1, 0, 0), unit(0, 1, 0), unit(0, 0, 1)]
    result = gate(catalog, ids, vectors, vectors[1])
    assert result.card_id == 'en:sv04-159' and result.printing_ids


def test_bare_number_must_not_drop_base_and_auto_choose_prize_pack(catalog):
    ids = ['en:sv04-159', 'en:PPS5-PAR-159', 'en:xy12-35']
    vectors = [unit(1, 0, 0), unit(.9763, .2164, 0), unit(0, 0, 1)]
    result = gate(catalog, ids, vectors, vectors[1], number='159')
    assert result.card_id == 'en:sv04-159' and result.printing_ids


def test_a_lone_prize_pack_cannot_be_automatically_selected(catalog):
    catalog.execute("DELETE FROM cards WHERE id='en:sv04-159'")
    ids = ['en:PPS5-PAR-159', 'en:xy12-35']
    vectors = [unit(1, 0), unit(0, 1)]
    result = gate(catalog, ids, vectors, vectors[0])
    assert not result.answered and result.reason == 'printing_base_missing'


@pytest.mark.parametrize(('set_id', 'prefix'), [('svp', 'SVP'), ('swshp', 'SWSH'), ('smp', 'SM')])
def test_promo_aliases_are_promo_scoped_and_not_guessed_across_sets(catalog, set_id, prefix):
    row = dict(id='en:' + set_id + '-053', name='Promo fixture', view_title=None,
               collector_number='053', printed_collector_number=None, language='en',
               set_id=set_id, set_name='Black Star Promos', image_path=None, provider_id='fixture')
    keys = list(row)
    catalog.execute(f'INSERT OR REPLACE INTO cards ({",".join(keys)}) VALUES ({",".join("?" for _ in keys)})', list(row.values()))
    by_key, _, _ = load_catalogue(catalog, ON)
    assert [r['id'] for r in lookup(by_key, 'Promo fixture', prefix + ' 053', None, ON)] == [row['id']]
    assert lookup(load_catalogue(catalog)[0], 'Promo fixture', prefix + '053', None) == []
    catalog.execute("UPDATE cards SET set_id='ordinary', set_name='Ordinary Expansion' WHERE id=?", (row['id'],))
    assert lookup(load_catalogue(catalog, ON)[0], 'Promo fixture', prefix + '053', None, ON) == []


def test_toxel_bare_promo_lookup_already_worked_and_remains_unique(catalog):
    for options in [GateOptions(), ON]:
        by_key, _, _ = load_catalogue(catalog, options)
        assert [r['id'] for r in lookup(by_key, 'Toxel', '078', None, options)] == ['en:mep-078']
    scan = next(row for row in FIXTURE['scans'] if row['id'] == 'b3ac26f2')
    assert scan['client_text'] is None  # Server OCR must not be relabelled phone OCR.


def test_two_promos_with_same_name_and_number_do_not_make_a_unique_card(catalog):
    catalog.execute("INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,language) VALUES ('en:svp-078','fixture','Toxel','svp','Black Star Promos','078','en')")
    ids = ['en:mep-078', 'en:svp-078']
    result = gate(catalog, ids, [unit(1, 0), unit(1, 0)], unit(1, 0), name='Toxel', number='078')
    assert not result.answered and result.reason == 'ambiguous_text'


def test_printing_response_persists_the_offered_choices_even_if_confirmation_flag_is_off(catalog):
    from app.recognition.stage1_answer import answer_stage1
    ids = ['en:sv04-159', 'en:PPS5-PAR-159', 'en:xy12-35']
    vectors = [unit(1, 0, 0), unit(.9763, .2164, 0), unit(0, 0, 1)]
    decision = gate(catalog, ids, vectors, vectors[1])
    results = sqlite3.connect(':memory:')
    init_results(results)
    settings = Settings(_env_file=None, stage1_require_confirmation=False)
    response = answer_stage1(decision=decision, settings=settings, runtime=SimpleNamespace(),
        catalog=catalog, results=results, session_id='fixture',
        client_text=json.dumps({'name':'Ancient Booster Energy Capsule','number':'159/182'}), graded=False, image_bytes=b'')
    assert response.status.value == 'printing_ambiguous'
    assert response.best_match.card_id == 'en:sv04-159'
    assert response.confidence.requires_confirmation and response.confidence.printing == 'ambiguous'
    assert {p.card_id for p in response.printing_review.plausible_printings} == set(ids[:2])
    saved = json.loads(results.execute('SELECT ocr_json FROM scans').fetchone()[0])
    assert {p['card_id'] for p in saved['printing_review']['plausible_printings']} == set(ids[:2])
    results.close()


def test_stage1b_preserves_diagnostics_and_printing_choices_after_artwork(catalog, monkeypatch):
    from app.recognition import stage1_answer
    ids = ['en:sv04-159', 'en:PPS5-PAR-159', 'en:xy12-35']
    vectors = np.stack([unit(1, 0, 0), unit(.9763, .2164, 0), unit(.999, 0, .04)])
    runtime = SimpleNamespace(snapshot=SimpleNamespace(embeddings=vectors, card_ids=ids))
    # Every fix on, except the twin guard: this is the baseline the guard is measured against.
    settings = SimpleNamespace(stage1b_text_verify=True, **{'stage1_' + key: key != 'twin_guard'
                                                             for key in GateOptions.__dataclass_fields__})
    wire = json.dumps({'model':'2ddf6ec79e37/coreml-pal8','vector':base64.b64encode(vectors[0].astype('<f2').tobytes()).decode()})
    monkeypatch.setattr(stage1_answer, '_artwork', lambda *_a: 10)
    result = stage1_answer.evaluate_stage1(settings=settings,runtime=runtime,catalog=catalog,
        client_text=json.dumps({'name':'Ancient Booster Energy Capsule','number':'159/182'}),
        client_embedding=wire,card_quad=[(0,0),(1,0),(1,1),(0,1)],image_bytes=b'')
    assert result.answered and result.stage == '1b' and result.inliers == 10
    assert result.printing_ids and result.vector_top and result.text_candidate_count == 2
    monkeypatch.setattr(stage1_answer, '_artwork', lambda *_a: None)
    miss = stage1_answer.evaluate_stage1(settings=settings,runtime=runtime,catalog=catalog,
        client_text=json.dumps({'name':'Ancient Booster Energy Capsule','number':'159/182'}),
        client_embedding=wire,card_quad=[(0,0),(1,0),(1,1),(0,1)],image_bytes=b'')
    assert not miss.answered and miss.reason == 'artwork_miss' and miss.vector_top
    # With the guard on, the same twins never reach the artwork check: the full pipeline answers.
    settings.stage1_twin_guard = True
    monkeypatch.setattr(stage1_answer, '_artwork', lambda *_a: pytest.fail('artwork must not run on twins'))
    guarded = stage1_answer.evaluate_stage1(settings=settings,runtime=runtime,catalog=catalog,
        client_text=json.dumps({'name':'Ancient Booster Energy Capsule','number':'159/182'}),
        client_embedding=wire,card_quad=[(0,0),(1,0),(1,1),(0,1)],image_bytes=b'')
    assert not guarded.answered and guarded.reason == 'printing_twins' and guarded.stage is None


def test_gate_logging_reports_vector_text_and_contradiction_without_ocr_or_vectors(catalog):
    ids = ['en:30th-077', 'en:xy12-35', 'en:sv04-159']
    vectors = [unit(.9, .43589), unit(1, 0), unit(.99, .141067)]
    decision = gate(catalog, ids, vectors, vectors[1], name='Comfey', number='077/128')
    assert decision.reason == 'visual_contradiction'
    assert decision.margin < .02 and decision.contradiction_gap > .09
    line = stage0_line(SimpleNamespace(id='fixture',suggestions=[]), trace='t',source=None,
                       evidence=PhoneEvidence(),stage1='abstained',gate=decision)
    assert 'vector_top=en:xy12-35' in line and 'vector_top_score=1.0000' in line
    assert 'text_candidates=en:30th-077 text_candidate_count=1' in line
    assert 'contradicting_card=en:xy12-35' in line and 'contradiction_gap=0.1000' in line
    assert 'Comfey' not in line and 'vector=' not in line
    many = replace(decision, text_candidates=tuple('en:set-'+str(i) for i in range(9)), text_candidate_count=9)
    bounded = stage0_line(SimpleNamespace(id='fixture',suggestions=[]),trace='t',source=None,evidence=PhoneEvidence(),gate=many)
    assert 'text_candidate_count=9' in bounded and 'en:set-4' in bounded and 'en:set-5' not in bounded


@pytest.mark.parametrize('scan', FIXTURE['scans'], ids=lambda scan: scan['id'])
def test_recorded_real_payload_gate_replay(catalog, scan):
    if scan['embedding_observed']:
        pytest.skip(scan['replay_skip'])
    from app.recognition.stage1_answer import evaluate_stage1
    result = evaluate_stage1(settings=Settings(_env_file=None),runtime=SimpleNamespace(),catalog=catalog,
        client_text=json.dumps(scan['client_text']),client_embedding=scan['client_embedding'],
        card_quad=scan['card_quad'],image_bytes=b'')
    assert not result.answered and result.reason == scan['before_reason'] == 'no_embedding'
