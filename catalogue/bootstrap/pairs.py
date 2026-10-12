"""Trainer-kit artwork pairing. A pair is confirmed only by one identical crop."""

from __future__ import annotations

# Same artwork-family floor as api/app/recognition/printing.py. It sends a
# case to review. It never confirms a twin.
SIMILAR = 0.84
IDENTICAL = 0.999


def decide_pair(scores: list[tuple[str, float]] | None) -> tuple[str, str, str | None]:
    """Return status, reason, and twin id.

    ``scores`` is empty when the trainer kit has no artwork probe. A missing
    probe is a hold, not a rejected twin.
    """
    if not scores:
        return "held", "no_source_image", None
    identical = [card_id for card_id, score in scores if score >= IDENTICAL]
    if len(identical) == 1:
        return "paired", "crop_probe_identical", identical[0]
    if len(identical) > 1:
        return "review", "multiple_identical_artwork", None
    if any(score >= SIMILAR for _, score in scores):
        return "review", "similar_artwork_not_identical", None
    return "held", "artwork_not_proven", None
