"""Batched alternate-frame embeddings must not change what is selected."""
from __future__ import annotations

import numpy as np
from PIL import Image

from app.recognition.embed import DinoEmbedder
from app.recognition.orientation import retrieve_oriented


class _Session:
    def __init__(self, batch_dim=None, fail_batches=False):
        self.batch_dim = batch_dim
        self.fail_batches = fail_batches
        self.runs: list[int] = []

    def get_inputs(self):
        return [type('I', (), {'name': 'x', 'shape': [self.batch_dim, 3, 224, 224]})()]

    def run(self, _names, feeds):
        batch = feeds['x']
        if self.fail_batches and batch.shape[0] > 1:
            raise RuntimeError('fixed batch')
        self.runs.append(batch.shape[0])
        # One vector per image, derived from its mean so rows differ.
        return [np.stack([[batch[i].mean() + 1., 2., 3., 4.] for i in range(batch.shape[0])]).astype(np.float32)]


def _embedder(session):
    embedder = DinoEmbedder.__new__(DinoEmbedder)
    embedder.session = session
    first = session.get_inputs()[0]
    embedder.input_name = first.name
    embedder.batchable = not (isinstance(first.shape[0], int) and first.shape[0] == 1)
    return embedder


def _frames(n):
    return [Image.new('RGB', (40, 60), (i * 20, 10, 10)) for i in range(n)]


def test_embed_many_matches_one_by_one_in_a_single_call() -> None:
    session = _Session()
    embedder = _embedder(session)
    frames = _frames(4)
    batched = embedder.embed_many(frames, 'pad')
    assert session.runs == [4]
    single = [embedder.embed(frame, 'pad') for frame in frames]
    for a, b in zip(batched, single):
        assert np.allclose(a, b, atol=1e-6)


def test_embed_many_falls_back_when_the_graph_is_fixed_to_one() -> None:
    session = _Session(batch_dim=1)
    embedder = _embedder(session)
    assert len(embedder.embed_many(_frames(3), 'pad')) == 3
    assert session.runs == [1, 1, 1]


def test_embed_many_falls_back_when_the_batch_call_fails() -> None:
    session = _Session(fail_batches=True)
    embedder = _embedder(session)
    assert len(embedder.embed_many(_frames(3), 'pad')) == 3
    assert embedder.batchable is False


class _Counting:
    def __init__(self, many: bool):
        self.single = 0
        self.many_calls = 0
        if many:
            self.embed_many = self._many

    def _vec(self, image):
        v = np.zeros(4, dtype=np.float32)
        v[image.width % 4] = 1.
        return v

    def embed(self, image, mode):
        self.single += 1
        return self._vec(image)

    def _many(self, images, mode):
        self.many_calls += 1
        return [self._vec(i) for i in images]


def _run(embedder):
    catalogue = np.array([[0., 0., 0., 1.]], dtype=np.float32)
    alternates = [('a', Image.new('RGB', (41, 60))), ('b', Image.new('RGB', (42, 60))),
                  ('c', Image.new('RGB', (43, 60)))]
    # A weak primary (score 0, below .88) so the alternates are tried.
    return retrieve_oriented(Image.new('RGB', (40, 60)), embedder, catalogue, mode='pad', keep=None,
                             min_visual=.78, min_gap=.04, alternate_frames=alternates,
                             selection_metadata={})


def test_orientation_uses_one_call_for_alternates_and_picks_the_same_frame() -> None:
    plain, batched = _Counting(many=False), _Counting(many=True)
    a, b = _run(plain), _run(batched)
    assert batched.many_calls == 1 and batched.single == 2  # primary and the upside-down try
    assert plain.single == 5
    assert a[3]['embeddings'] == b[3]['embeddings']
    assert a[0].width == b[0].width == 43  # the strongest alternate wins either way
