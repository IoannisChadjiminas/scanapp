"""Tests for the Phase 0 instant-recognition index and metric code (api/scripts/instant)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts' / 'instant'


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


index_formats = _load('index_formats')
metrics = _load('metrics')


def _vectors(seed: int, count: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(size=(count, index_formats.DIM)).astype(np.float32)


def _unit(vector: np.ndarray) -> np.ndarray:
    return vector / np.linalg.norm(vector)


# --- index formats -------------------------------------------------------

def test_normalize_rows_rejects_wrong_shape_and_zero_rows():
    with pytest.raises(ValueError):
        index_formats.normalize_rows(np.zeros((2, 10), dtype=np.float32))
    with pytest.raises(ValueError):
        index_formats.normalize_rows(np.zeros((1, index_formats.DIM), dtype=np.float32))


def test_build_index_rejects_unknown_format_and_length_mismatch():
    vectors = _vectors(1, 3)
    with pytest.raises(ValueError):
        index_formats.build_index('int4', vectors, ['a', 'b', 'c'], ['a', 'b', 'c'])
    with pytest.raises(ValueError):
        index_formats.build_index('fp32', vectors, ['a', 'b'], ['a', 'b', 'c'])


def test_formats_store_expected_dtypes_and_sizes():
    vectors = _vectors(2, 50)
    ids = [f'c{i}' for i in range(50)]
    groups = ids
    fp32 = index_formats.build_index('fp32', vectors, ids, groups)
    fp16 = index_formats.build_index('fp16', vectors, ids, groups)
    int8 = index_formats.build_index('int8', vectors, ids, groups)
    assert fp32.matrix.dtype == np.float32
    assert fp16.matrix.dtype == np.float16
    assert int8.matrix.dtype == np.int8 and int8.row_scales.dtype == np.float32
    assert fp32.nbytes() == 50 * 384 * 4
    assert fp16.nbytes() == 50 * 384 * 2
    assert int8.nbytes() == 50 * 384 + 50 * 4


def test_int8_rows_round_trip_within_quantization_step():
    vectors = _vectors(3, 20)
    index = index_formats.build_index('int8', vectors, [str(i) for i in range(20)], [str(i) for i in range(20)])
    restored = index.matrix.astype(np.float32) * index.row_scales[:, None]
    unit = index_formats.normalize_rows(vectors)
    assert np.max(np.abs(restored - unit)) <= np.max(index.row_scales) / 2 + 1e-7


def test_search_returns_the_planted_card_first_in_every_format():
    vectors = _vectors(4, 300)
    ids = [f'card-{i}' for i in range(300)]
    query = _unit(vectors[137] + 0.05 * _vectors(5, 1)[0])
    for fmt in index_formats.FORMATS:
        index = index_formats.build_index(fmt, vectors, ids, ids)
        hits = index_formats.search(index, query, k=5)
        assert hits[0].group == 'card-137', fmt
        assert len(hits) == 5


def test_int8_scores_track_fp32_scores():
    vectors = _vectors(6, 500)
    ids = [str(i) for i in range(500)]
    query = _unit(_vectors(7, 1)[0])
    exact = index_formats.row_scores(index_formats.build_index('fp32', vectors, ids, ids), query)
    quantized = index_formats.row_scores(index_formats.build_index('int8', vectors, ids, ids), query)
    assert np.max(np.abs(exact - quantized)) < 0.02


def test_duplicate_rows_collapse_to_one_group():
    vectors = _vectors(8, 4)
    vectors[1] = vectors[0]  # bare id and en: id of the same card
    ids = ['base1-1', 'en:base1-1', 'other-a', 'other-b']
    groups = ['base1-1', 'base1-1', 'other-a', 'other-b']
    index = index_formats.build_index('fp32', vectors, ids, groups)
    hits = index_formats.search(index, vectors[0], k=3)
    assert [h.group for h in hits][0] == 'base1-1'
    assert len({h.group for h in hits}) == len(hits) == 3
    assert hits[0].row in (0, 1)


def test_margin_is_top1_minus_best_other_group():
    hits = [
        index_formats.Hit('a', 0, 0.91),
        index_formats.Hit('a', 1, 0.90),  # same group, must not count as the rival
        index_formats.Hit('b', 2, 0.85),
    ]
    assert index_formats.margin(hits[::2]) == pytest.approx(0.06)
    assert index_formats.margin(hits[:1]) == float('inf')
    assert index_formats.margin([]) == 0.0


def test_rank_groups_falls_back_to_full_sort_when_pool_is_all_duplicates():
    count = 200
    vectors = np.tile(_vectors(9, 1), (count, 1))  # every row is the same card
    vectors[-1] = _vectors(10, 1)[0]
    ids = [f'row{i}' for i in range(count)]
    groups = ['dup'] * (count - 1) + ['unique']
    index = index_formats.build_index('fp32', vectors, ids, groups)
    hits = index_formats.search(index, vectors[-1], k=2)
    assert [h.group for h in hits] == ['unique', 'dup']


# --- metrics -------------------------------------------------------------

def _record(label, frames, top5=None, family=None, category='unique'):
    return metrics.PhotoRecord(
        photo_id='p', label=label, category=category,
        family=frozenset(family or {label}),
        top5=tuple(top5 or [frames[0][0]]),
        frames=tuple(frames),
    )


def test_wilson_interval_matches_known_values():
    low, high = metrics.wilson_interval(0, 10)
    assert low == 0.0
    assert high == pytest.approx(0.2775, abs=1e-3)
    low, high = metrics.wilson_interval(50, 100)
    assert low == pytest.approx(0.404, abs=1e-3) and high == pytest.approx(0.596, abs=1e-3)
    assert metrics.wilson_interval(0, 0) == (0.0, 1.0)


def test_likely_frame_needs_consecutive_stable_frames_above_margin():
    frames = [('a', 0.05), ('a', 0.01), ('a', 0.05), ('a', 0.05), ('b', 0.09)]
    assert metrics.likely_frame(frames, 0.03, 1) == ('a', 0)
    assert metrics.likely_frame(frames, 0.03, 2) == ('a', 3)
    assert metrics.likely_frame(frames, 0.03, 3) is None  # frames 2-4 change group
    assert metrics.likely_frame(frames, 0.10, 1) is None
    with pytest.raises(ValueError):
        metrics.likely_frame(frames, 0.03, 0)


def test_evaluate_rule_separates_printing_confusion_from_wrong_card():
    records = [
        _record('x', [('x', 0.05)] * 2),  # right, shown
        _record('x', [('x-reprint', 0.05)] * 2, family={'x', 'x-reprint'}),  # printing confusion
        _record('x', [('y', 0.05)] * 2),  # wrong card
        _record('x', [('y', 0.01)] * 2),  # wrong but below margin: not shown
    ]
    result = metrics.evaluate_rule(records, margin_min=0.02, stable_frames=1)
    assert result.shown == 3
    assert result.wrong_shown == 2
    assert result.wrong_card_shown == 1
    assert result.shown_rate == pytest.approx(0.75)
    assert result.wrong_rate == pytest.approx(2 / 3)


def test_smallest_risk_rule_prefers_most_shown_under_the_wrong_limit():
    records = [_record('x', [('x', 0.05)] * 3) for _ in range(199)] + [_record('x', [('y', 0.2)] * 3)]
    results = metrics.scan_rules(records, margins=[0.0, 0.1], stable_frame_options=[1, 2])
    best = metrics.smallest_risk_rule(results, max_wrong_rate=0.01)
    assert best is not None
    assert best.wrong_shown == 0 or best.wrong_rate < 0.01
    assert best.shown_rate == max(r.shown_rate for r in results if r.wrong_rate < 0.01)
    assert metrics.smallest_risk_rule([metrics.evaluate_rule(records, 0.0, 1)], max_wrong_rate=0.0) is None


def test_accuracy_counts_top1_family_and_top5():
    records = [
        _record('x', [('x', 0.1)], top5=['x', 'y']),
        _record('x', [('x-r', 0.1)], top5=['x-r', 'x'], family={'x', 'x-r'}),
        _record('x', [('z', 0.1)], top5=['z', 'w']),
    ]
    summary = metrics.accuracy(records)
    assert summary['top1'] == 1
    assert summary['top1_family_rate'] == pytest.approx(2 / 3)
    assert summary['top5'] == 2
    assert summary['top5_rate'] == pytest.approx(2 / 3)


def test_margin_distribution_ignores_infinite_margins():
    distribution = metrics.margin_distribution([0.0, 0.01, 0.02, float('inf')])
    assert distribution['n'] == 3
    assert distribution['max'] == 0.02
    assert metrics.margin_distribution([])['n'] == 0
