"""Artwork-family verification: choose between different artworks by local inliers.

Behind RANK_FAMILY_VERIFY. The shortlist's candidates are grouped into artwork families (the
same illustration: reprints and other-language prints). One reference per family is checked
with the local artwork verifier, without the OCR name/number filter that the shortlist check
uses, because a blurry vintage photo's misread title must not remove the right artwork before
geometry can look at it. A family is chosen only when it leads every other family clearly.

Inliers certify shared artwork, never which reprint it is: the chosen family moves up as a
whole and keeps the existing order inside it (number, name, language, visual). A scan decided
this way is never matched, only reviewed.
"""
from __future__ import annotations

from typing import Callable, Iterable

import numpy as np

from app.recognition.rank import normalize_text

TWIN_COSINE = 0.95
MIN_INLIERS = 12
MARGIN = 1.5


def artwork_title(row: dict) -> str:
    return normalize_text(str(row.get("view_title") or row.get("name") or ""))


def artwork_families(rows: Iterable[dict], vector: Callable[[str], np.ndarray | None],
                     twin: float = TWIN_COSINE) -> list[list[dict]]:
    """Group rows, best first, into families of the same artwork.

    Two rows share a family when their full-card vectors are twins or their (English) titles
    are equal. A row joins the first family it matches; the family order is its best row's.
    """
    families: list[tuple[set[str], list[np.ndarray], list[dict]]] = []
    for row in rows:
        title = artwork_title(row)
        vec = vector(row["card_id"])
        home = None
        for titles, vectors, members in families:
            if (title and title in titles) or (vec is not None and any(float(v @ vec) >= twin for v in vectors)):
                home = (titles, vectors, members)
                break
        if home is None:
            families.append((set(), [], []))
            home = families[-1]
        if title:
            home[0].add(title)
        if vec is not None:
            home[1].append(vec)
        home[2].append(row)
    return [members for _, _, members in families]


def decisive_family(families: list[list[dict]], inliers: dict[str, int],
                    min_inliers: int = MIN_INLIERS, margin: float = MARGIN) -> int | None:
    """Index of the family whose best verified member clearly leads every other family."""
    scores = sorted(((max((inliers.get(r["card_id"], 0) for r in members), default=0), i)
                     for i, members in enumerate(families)), reverse=True)
    if not scores or scores[0][0] < min_inliers:
        return None
    runner_up = scores[1][0] if len(scores) > 1 else 0
    return scores[0][1] if scores[0][0] >= margin * max(runner_up, 1) else None


def promote_family(combined: list[dict], members: list[dict], order: list[str]) -> None:
    """Move the family to the top. Inside it, `order` (the ranking before verification) decides;
    the rest keeps its current order."""
    rank = {card_id: i for i, card_id in enumerate(order)}
    ids = {r["card_id"] for r in members}
    combined.sort(key=lambda r: (r["card_id"] not in ids, rank.get(r["card_id"], len(rank)) if r["card_id"] in ids else 0))


def verify_families(verifier, image, combined: list[dict], cards: dict, vector, limit: int):
    """Check one reference per family. Returns (decided family or None, its matches, diagnostics)."""
    families = artwork_families(combined, vector)[:limit]
    references = []
    for members in families:
        for row in members:
            card = cards.get(row["card_id"])
            if card is not None and card["image_path"]:
                references.append((row["card_id"], str(card["image_path"])))
                break
    found = verifier.verify(image, references, len(references)) if references else []
    inliers = {m.card_id: m.artwork_inliers for m in found}
    lead = decisive_family(families, inliers)
    diagnostics = {"families": len(families), "references": len(references),
                   "verified": [[m.card_id, m.artwork_inliers] for m in found],
                   "decided": None if lead is None else [r["card_id"] for r in families[lead]]}
    if lead is None:
        return None, [], diagnostics
    ids = {r["card_id"] for r in families[lead]}
    return families[lead], [m for m in found if m.card_id in ids], diagnostics
