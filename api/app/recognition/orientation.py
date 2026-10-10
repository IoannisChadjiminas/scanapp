"""Bounded visual orientation fallback before OCR and candidate reranking."""
from __future__ import annotations

import time
from typing import Any

import numpy as np
from PIL import Image

from app.recognition.embed import top_k


def retrieve_oriented(
    image: Image.Image,
    embedder: Any,
    embeddings: np.ndarray,
    *,
    mode: str,
    keep: np.ndarray | None,
    min_visual: float,
    min_gap: float,
    query_vectors: dict[int, np.ndarray] | None = None,
    alternate_frames: list[tuple[str, Image.Image]] | None = None,
    selection_metadata: dict | None = None,
    retrieval_segments: tuple[int, ...] | None = None,
) -> tuple[Image.Image, np.ndarray, np.ndarray, dict[str, float]]:
    """Only replace the supplied orientation with a materially stronger one.

    Sideways crops try both portrait directions. Weak portrait crops also try
    upside-down. A good portrait has no extra inference cost. No thresholds are
    relaxed, and OCR runs once, on the selected orientation.
    """
    embed_ms = retrieve_ms = 0.0
    embeddings_run = 0

    def retrieve(frame: Image.Image, query: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        nonlocal embed_ms, retrieve_ms, embeddings_run
        embeddings_run += 1
        started = time.perf_counter()
        if query is None:
            query = embedder.embed(frame, mode)
        if query_vectors is not None:
            query_vectors[id(frame)] = query
        embed_ms += (time.perf_counter() - started) * 1000
        started = time.perf_counter()
        indices, scores = top_k(embeddings, query, k=20, keep=keep, segments=retrieval_segments)
        retrieve_ms += (time.perf_counter() - started) * 1000
        return indices, scores

    indices, scores = retrieve(image)
    initial_score = float(scores[0]) if len(scores) else -1.0
    selected = image
    angle = 0
    best_score = initial_score
    selected_profile = 'primary'
    # Missing requested-language vectors must not trigger pointless retries.
    if len(scores):
        turns = (90, 270) if image.width > image.height else (
            (180,) if initial_score < min_visual else ()
        )
        for turn in turns:
            frame = image.rotate(turn, expand=True)
            candidate_indices, candidate_scores = retrieve(frame)
            score = float(candidate_scores[0]) if len(candidate_scores) else -1.0
            if score >= min_visual and score - initial_score >= min_gap and score > best_score:
                selected, indices, scores = frame, candidate_indices, candidate_scores
                best_score, angle = score, turn
    # A geometric detector can select the holder or a text panel. For a weak
    # primary crop, compare a bounded raw/alternate-frame shortlist instead of
    # accepting that crop unconditionally. This selects a retrieval query;
    # neither the score nor four inferred corners prove a printing.
    hypotheses = 0
    if len(scores) and best_score < .88:
        alternates = (alternate_frames or [])[:7]
        # Every alternate is scored whatever the earlier ones return, so they
        # share one model call; the pick below is still made in order.
        started = time.perf_counter()
        embed_many = getattr(embedder, 'embed_many', None)
        queries = (embed_many([frame for _, frame in alternates], mode)
                   if embed_many and len(alternates) > 1 else [None] * len(alternates))
        embed_ms += (time.perf_counter() - started) * 1000 if embed_many and len(alternates) > 1 else 0.
        for (profile, frame), query in zip(alternates, queries):
            candidate_indices, candidate_scores = retrieve(frame, query)
            hypotheses += 1
            score = float(candidate_scores[0]) if len(candidate_scores) else -1.0
            if score >= .65 and score > best_score + .03:
                selected, indices, scores = frame, candidate_indices, candidate_scores
                best_score, angle, selected_profile = score, 0, profile
    if selection_metadata is not None:
        selection_metadata.update(profile=selected_profile, alternate_hypotheses=hypotheses)
    return selected, indices, scores, {
        "embed_ms": embed_ms,
        "retrieve_ms": retrieve_ms,
        "orientation_degrees": float(angle),
        "frame_hypotheses": float(hypotheses),
        "embeddings": float(embeddings_run),
    }
