"""Artwork-family verification: choose between different artworks by local inliers.

Behind RANK_FAMILY_VERIFY. The shortlist's candidates are grouped into artwork families (the
same illustration: reprints and other-language prints). One reference per family is checked
with the local artwork verifier, without the OCR name/number filter that the shortlist check
uses, because a blurry vintage photo's misread title must not remove the right artwork before
geometry can look at it. A family is chosen only when it leads every other family clearly.

A shared title is never artwork evidence on its own (every Charizard has the same title).
Before verification two rows share a family only when their full-card vectors are twins, or
their titles are equal and their reference artwork thumbnails correlate (the printing index's
own same-artwork floor). After verification, two families whose best members both verified
against this photo and share a title are one artwork: two different illustrations cannot both
pass the geometric check on the same photo.

Inliers certify shared artwork, never which reprint it is: the chosen family moves up as a
whole and keeps the existing order inside it (number, name, language, visual). A scan decided
this way is never matched, only reviewed.
"""
from __future__ import annotations

from typing import Callable, Iterable

import numpy as np

from app.recognition.printing import MIN_REFERENCE_CORRELATION
from app.recognition.rank import normalize_text

TWIN_COSINE = 0.95
MIN_INLIERS = 12
MARGIN = 1.5

Lookup = Callable[[str], "np.ndarray | None"]


def artwork_title(row: dict) -> str:
    return normalize_text(str(row.get("view_title") or row.get("name") or ""))


def _same_artwork(a: dict, b: dict, vector: Lookup, thumbnail: Lookup, twin: float) -> bool:
    va, vb = vector(a["card_id"]), vector(b["card_id"])
    if va is not None and vb is not None and float(va @ vb) >= twin:
        return True
    if not artwork_title(a) or artwork_title(a) != artwork_title(b):
        return False
    ta, tb = thumbnail(a["card_id"]), thumbnail(b["card_id"])
    return ta is not None and tb is not None and float(ta @ tb) >= MIN_REFERENCE_CORRELATION


def artwork_families(rows: Iterable[dict], vector: Lookup, thumbnail: Lookup,
                     twin: float = TWIN_COSINE) -> list[list[dict]]:
    """Group rows, best first, into families of the same artwork.

    A row joins the first family holding a row it shares artwork with (see the module note);
    the family order is its best row's.
    """
    families: list[list[dict]] = []
    for row in rows:
        home = next((f for f in families if any(_same_artwork(row, m, vector, thumbnail, twin) for m in f)), None)
        if home is None:
            families.append([row])
        else:
            home.append(row)
    return families


def merge_verified(families: list[list[dict]], inliers: dict[str, int]) -> list[list[dict]]:
    """Join families whose verified members share a title: both passed geometry on this photo."""
    merged: list[list[dict]] = []
    titles: list[set[str]] = []
    for members in families:
        verified = {artwork_title(r) for r in members if inliers.get(r["card_id"], 0) > 0} - {""}
        home = next((i for i, t in enumerate(titles) if verified and t & verified), None)
        if home is None:
            merged.append(list(members))
            titles.append(verified)
        else:
            merged[home].extend(members)
            titles[home] |= verified
    return merged


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


def verify_families(verifier, image, candidates: list[dict], cards: dict, vector: Lookup,
                    thumbnail: Lookup, limit: int, prepared: dict | None = None):
    """Check one reference per family. Returns (decided family or None, its matches, diagnostics).

    `candidates` is the shortlist followed by any deeper retrieval rows, best first.
    """
    families = artwork_families(candidates, vector, thumbnail)[:limit]
    references = []
    for members in families:
        for row in members:
            card = cards.get(row["card_id"])
            if card is not None and card["image_path"]:
                references.append((row["card_id"], str(card["image_path"])))
                break
    found = verifier.verify(image, references, len(references), prepared=prepared) if references else []
    inliers = {m.card_id: m.artwork_inliers for m in found}
    families = merge_verified(families, inliers)
    lead = decisive_family(families, inliers)
    diagnostics = {"families": len(families), "references": len(references),
                   "verified": [[m.card_id, m.artwork_inliers] for m in found],
                   "decided": None if lead is None else [r["card_id"] for r in families[lead]]}
    if lead is None:
        return None, [], diagnostics
    ids = {r["card_id"] for r in families[lead]}
    return families[lead], [m for m in found if m.card_id in ids], diagnostics
