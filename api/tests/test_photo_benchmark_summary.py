import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location('photo_summary',
    Path(__file__).resolve().parents[1] / 'scripts/summarize_photo_benchmark.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def probe(recalled, *, automatic=False, wrong=False, latency=100):
    return {'top_correct': recalled, 'candidate_recalled': recalled,
        'automatic_claim': automatic, 'automatic_wrong_printing': wrong,
        'full_shortlist_printing_recall': recalled, 'artwork_shortlist_printing_recall': False,
        'status': 'matched' if automatic else 'retake',
        'timings_ms': {'total_ms': latency}}


def test_rollup_does_not_count_rank_one_as_returned_recall():
    before = probe(False)
    before['top_correct'] = True
    after = probe(True, automatic=True, latency=200)
    metrics = module.rollup([{'name': 'photo', 'before': before, 'after': after}])
    assert metrics['before']['top_correct'] == 1
    assert metrics['before']['candidate_recalled'] == 0
    assert metrics['recall_gains'] == ['photo']
    assert metrics['after']['latency_ms']['sample_p95_nearest_rank'] == 200


def test_rollup_reports_wrong_automatic_claim_and_regression():
    metrics = module.rollup([{'name': 'photo', 'before': probe(True),
        'after': probe(False, automatic=True, wrong=True)}])
    assert metrics['after']['automatic_wrong_printing'] == 1
    assert metrics['recall_regressions'] == ['photo']


def test_empty_stratum_has_no_fabricated_latency():
    assert module.rollup([])['after']['latency_ms']['median'] is None


def test_summary_rejects_partial_and_missing_runs():
    with pytest.raises(ValueError, match='completed'):
        module.summarize([])
    with pytest.raises(ValueError, match='Missing'):
        module.summarize([{'summary': {'sample': {'photos': 50}}}])


def test_complete_report_keeps_uncertain_failure_and_removes_rule_text():
    before = probe(False)
    after = probe(False)
    after['status'] = 'uncertain'
    for row in (before, after):
        row.update(ocr={'name_text': 'Supporter', 'lines': ['printed rules']},
                   top_id='wrong', message='Review', local_artwork_matches=[])
    case = {'name': 'photo', 'group': 'physical_photo', 'condition': 'raw_photo',
        'expected_id': 'truth', 'truth_in_artwork_pilot': False,
        'provenance': {'layout': 'trainer_full_art', 'language': 'en', 'conditions': []},
        'before': before, 'after': after}
    report = module.summarize([{'case': case}, {'summary': {'sample': {'photos': 1}}}])
    assert report['failures'][0]['status'] == 'uncertain'
    assert 'lines' not in report['cases'][0]['after']['ocr']
    assert 'lines' not in report['failures'][0]['ocr']
    assert report['overall']['after']['candidate_recalled'] == 0
