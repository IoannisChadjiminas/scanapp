import numpy as np
import pytest

from app.recognition.embed import top_k


def test_appended_ties_preserve_exact_parent_order_and_scores():
    rng = np.random.default_rng(5)
    parent = rng.normal(size=(107, 8)).astype(np.float32)
    parent[1:8] = parent[0]
    query = parent[0]
    before, scores = top_k(parent, query, k=20)
    delta = np.zeros((5, 8), dtype=np.float32)
    after, current = top_k(np.concatenate([parent, delta]), query, k=20, segments=(107, 5))
    assert np.array_equal(before, after)
    assert np.array_equal(scores, current)


def test_stronger_new_reference_wins_without_reordering_parent_ties():
    parent = np.ones((30, 3), dtype=np.float32)
    query = np.ones(3, dtype=np.float32)
    before, _ = top_k(parent, query, k=10)
    combined = np.concatenate([parent, np.full((1, 3), 2, dtype=np.float32)])
    after, _ = top_k(combined, query, k=10, segments=(30, 1))
    assert after[0] == 30
    assert np.array_equal(after[1:], before[:9])


def test_segment_lineage_survives_multiple_releases_and_language_mask():
    parent = np.ones((30, 3), dtype=np.float32)
    query = np.ones(3, dtype=np.float32)
    first = np.concatenate([parent, parent[:2]])
    mask = np.ones(32, dtype=bool); mask[2:5] = False
    before, scores = top_k(first, query, k=10, keep=mask, segments=(30, 2))
    next_release = np.concatenate([first, parent[:3]])
    after, current = top_k(next_release, query, k=10,
        keep=np.concatenate([mask, np.ones(3, dtype=bool)]), segments=(30, 2, 3))
    assert np.array_equal(before, after) and np.array_equal(scores, current)
    assert not set(after).intersection({2, 3, 4})


@pytest.mark.parametrize('segments', [(29,), (0, 30), (True, 29), (-1, 31)])
def test_invalid_lineage_fails_closed(segments):
    with pytest.raises(ValueError):
        top_k(np.ones((30, 3), dtype=np.float32), np.ones(3), segments=segments)


def test_runtime_rejects_invalid_lineage_before_model_loading(monkeypatch):
    from app.config import Settings
    from app.recognition.artifacts import ArtifactSnapshot
    from app.recognition.runtime import Runtime

    snapshot = object.__new__(ArtifactSnapshot)
    snapshot.embeddings = np.ones((30, 3), dtype=np.float32)
    snapshot.manifest = {'retrieval_segments': [29]}
    monkeypatch.setattr('app.recognition.runtime.DinoEmbedder',
                        lambda *args: pytest.fail('Invalid lineage must not load a model'))
    runtime = Runtime(Settings(_env_file=None))
    runtime.load(cloud_snapshot=snapshot)
    assert not runtime.ready
    assert runtime.error == 'Invalid immutable retrieval segment lineage'
