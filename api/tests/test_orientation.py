from __future__ import annotations

import numpy as np
from PIL import Image

from app.recognition.orientation import retrieve_oriented


class FakeEmbedder:
    def __init__(self, scores):
        self.scores = iter(scores)
        self.calls = []

    def embed(self, image, mode):
        self.calls.append(image.size)
        score = next(self.scores)
        return np.array([score, (1 - score ** 2) ** .5], dtype=np.float32)


def run(image, scores, keep=None):
    embedder = FakeEmbedder(scores)
    result = retrieve_oriented(image, embedder, np.array([[1, 0]], dtype=np.float32),
                              mode="pad", keep=keep, min_visual=.78, min_gap=.04)
    return result, embedder


def test_sideways_chooses_stronger_portrait_direction():
    result, embedder = run(Image.new("RGB", (440, 315)), [.60, .99, .65])
    assert result[0].size == (315, 440)
    assert result[3]["orientation_degrees"] == 90
    assert len(embedder.calls) == 3


def test_other_sideways_direction_is_supported():
    result, _ = run(Image.new("RGB", (440, 315)), [.60, .65, .99])
    assert result[3]["orientation_degrees"] == 270


def test_weak_upside_down_portrait_can_be_corrected():
    result, _ = run(Image.new("RGB", (315, 440)), [.60, .99])
    assert result[3]["orientation_degrees"] == 180


def test_strong_portrait_does_not_add_inference():
    result, embedder = run(Image.new("RGB", (315, 440)), [.99])
    assert result[3]["orientation_degrees"] == 0
    assert len(embedder.calls) == 1


def test_small_gain_or_weak_absolute_score_does_not_rotate():
    for scores in ([.80, .82, .81], [.60, .70, .75]):
        result, _ = run(Image.new("RGB", (440, 315)), scores)
        assert result[3]["orientation_degrees"] == 0


def test_no_language_vectors_does_not_retry():
    result, embedder = run(Image.new("RGB", (440, 315)), [.60], np.array([False]))
    assert len(result[1]) == 0
    assert len(embedder.calls) == 1


def test_weak_detector_crop_can_choose_a_better_inner_frame():
    primary = Image.new('RGB',(500,700))
    alternate = Image.new('RGB',(400,560))
    embedder = FakeEmbedder([.7,.6,.95])
    metadata, vectors = {}, {}
    result = retrieve_oriented(primary,embedder,np.array([[1,0]],dtype=np.float32),
        mode='pad',keep=None,min_visual=.78,min_gap=.04,query_vectors=vectors,
        alternate_frames=[('inner',alternate)],selection_metadata=metadata)
    assert result[0] is alternate
    assert metadata['profile'] == 'inner'
    assert id(alternate) in vectors


def test_strong_primary_does_not_search_alternate_frames():
    embedder = FakeEmbedder([.95])
    result = retrieve_oriented(Image.new('RGB',(500,700)),embedder,np.array([[1,0]],dtype=np.float32),
        mode='pad',keep=None,min_visual=.78,min_gap=.04,
        alternate_frames=[('extra',Image.new('RGB',(300,420)))])
    assert len(embedder.calls) == 1 and result[3]['frame_hypotheses'] == 0


def test_alternate_frame_queries_have_a_hard_bound():
    embedder = FakeEmbedder([.70]*11)
    result = retrieve_oriented(Image.new('RGB',(300,420)),embedder,
        np.array([[1,0]],dtype=np.float32),mode='pad',keep=None,
        min_visual=.78,min_gap=.04,
        alternate_frames=[('window',Image.new('RGB',(300,420))) for _ in range(20)])
    assert len(embedder.calls) == 9  # primary + 180-degree retry + seven frames
    assert result[3]['frame_hypotheses'] == 7
