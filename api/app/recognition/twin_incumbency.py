"""RANK_TWIN_INCUMBENCY: a newly released card never displaces its served vector twin.

When the leader belongs to the newest vector release (the last TWIN_INCUMBENCY_NEW_SEGMENTS
retrieval segments) and a candidate already served before it is its vector twin (full-card cosine
>= 0.95) in the same language, the incumbent goes first and the new card stays right behind it as
a printing choice. The release builders already apply the same 0.95 rule against the indexed
cards; this keeps the order safe for twins that predate that rule or slip under it at build time.
"""
from __future__ import annotations

from typing import Any

import numpy as np

TWIN = 0.95


def new_release_start(segments: tuple[int, ...] | None, count: int, new_segments: int) -> int | None:
    """Row index where the newest release begins, or None when the lineage is unknown."""
    if not segments or new_segments <= 0 or new_segments >= len(segments):
        return None
    return count - sum(segments[-new_segments:])


def incumbent_first(combined: list[dict[str, Any]], positions: dict[str, int], embeddings: np.ndarray,
                    new_start: int | None, languages: tuple[str, ...], twin: float = TWIN) -> str | None:
    """Move the served twin of a new leader to the top. Returns its card id, or None."""
    if not combined or new_start is None:
        return None
    lead = combined[0]
    i = positions.get(lead["card_id"])
    language = lead.get("language")
    if i is None or i < new_start or (languages and language not in languages):
        return None
    for row in combined[1:]:
        j = positions.get(row["card_id"])
        if j is None or j >= new_start or row.get("language") != language:
            continue
        if float(embeddings[i] @ embeddings[j]) >= twin:
            combined.remove(row)
            combined.insert(0, row)
            return row["card_id"]
    return None
