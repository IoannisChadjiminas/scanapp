"""Conservative printing ambiguity, independent of score gaps and finish choices.

Reference similarity is an abstention signal, not a calibrated probability or
proof of catalogue completeness. No cards, URLs or vectors are merged here.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
from pathlib import Path
from threading import RLock
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from app.recognition.ocr import OcrHit
from app.recognition.rank import accepted_collector_numbers, number_matches_identifiers, normalize_text


ART_BOX = (.12, .19, .88, .46)
# Exposure/registration changes between scans can lower this correlation even
# for repeated artwork. This floor only ADDS review choices; it never accepts a
# printing or asserts a verified artwork family.
MIN_REFERENCE_CORRELATION = .84
MIN_IDENTIFIER_CONFIDENCE = .85


def artwork_thumbnail(image: Image.Image) -> np.ndarray | None:
    """Conventional illustration-window probe; full-art layouts are not certified.

    Keep spatial colour structure, remove global exposure bias. Low-information
    patches cannot establish an artwork relationship. This intentionally only
    discovers conservative candidate groups, not authoritative artwork IDs.
    """
    image = ImageOps.exif_transpose(image).convert("RGB")
    w, h = image.size
    crop = image.crop(tuple(round(v * (w if i % 2 == 0 else h))
                            for i, v in enumerate(ART_BOX)))
    pixels = np.asarray(crop.resize((64, 32), Image.Resampling.BILINEAR), dtype=np.float32)
    if float(pixels.std()) < 12:
        return None
    pixels -= pixels.mean(axis=(0, 1), keepdims=True)
    norm = float(np.linalg.norm(pixels))
    return pixels.reshape(-1) / norm if norm > 0 else None


def printing_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    # Provider aliases of the same catalogue printing do not create a fake
    # choice. Different sets retain distinct IDs; finishes stay in variants.
    return (str(row.get("set_id") or row.get("set_name") or ""),
            str(row.get("set_name") or ""),
            str(row.get("collector_number") or ""),
            str(row.get("language") or ""))


class ReferencePrintingIndex:
    """Bounded, snapshot-local cache of same-name reference-image probes.

    Reads only files below the configured reference-image root. Includes cards
    outside retrieval top-K and unindexed references; missing files are reported
    as incomplete evidence. Never downloads images during a scan.
    """
    def __init__(self, data_dir: Path, max_groups: int = 32, feature_store=None) -> None:
        self.root = (data_dir / "reference-images").resolve()
        self.max_groups = max_groups
        self._groups: OrderedDict[tuple[str, str], list[tuple[dict, np.ndarray | None]]] = OrderedDict()
        self._lock = RLock()
        self.feature_store = feature_store

    def family(self, catalog: Any, top: dict[str, Any]) -> tuple[list[dict], bool]:
        name, language = str(top["name"]), str(top.get("language") or "")
        key = (name, language)
        with self._lock:
            cached = self._groups.get(key)
            if cached is None:
                rows = catalog.execute(
                    "SELECT * FROM cards WHERE name = ? AND language = ? ORDER BY id LIMIT 513",
                    (name, language),
                ).fetchall()
                cached = []
                for row in rows[:512]:
                    card = dict(row)
                    probe = None
                    raw_path = str(card.get("image_path") or "")
                    path = Path(raw_path).resolve()
                    if self.feature_store is not None:
                        probe = self.feature_store.thumbnail(str(card['id']), raw_path)
                    elif path.is_relative_to(self.root) and path.is_file():
                        try:
                            with Image.open(path) as image:
                                probe = artwork_thumbnail(image)
                        except (OSError, ValueError):
                            pass
                    cached.append((card, probe))
                if len(rows) > 512:
                    cached.append(({"id": "uninspected"}, None))
                self._groups[key] = cached
                while len(self._groups) > self.max_groups:
                    self._groups.popitem(last=False)
            self._groups.move_to_end(key)
            anchor = next((p for r, p in cached if r["id"] == top["card_id"]), None)
            incomplete = any(p is None for _, p in cached)
            if anchor is None:
                return [], True
            members = [r for r, p in cached if p is not None and
                       float(anchor @ p) >= MIN_REFERENCE_CORRELATION]
            return members, incomplete


@dataclass(frozen=True)
class PrintingDecision:
    ambiguous: bool
    reason: str | None = None
    members: tuple[dict[str, Any], ...] = ()
    candidate_group_id: str | None = None
    reference_coverage_complete: bool = False
    collector_evidence: tuple[str, ...] = ()
    guidance: str | None = None


def assess_printings(
    ranked: list[dict[str, Any]],
    *,
    family: list[dict[str, Any]],
    hits: list[OcrHit],
    reference_incomplete: bool,
    min_visual: float,
    min_gap: float,
    retake: bool,
) -> PrintingDecision:
    if retake or not ranked or (float(ranked[0]["visual_score"]) < min_visual
        and not ranked[0].get("local_artwork_verified") and not ranked[0].get('ocr_identity_verified')
        and not ranked[0].get('likely_identity_supported')):
        return PrintingDecision(False)
    top = ranked[0]
    # Reference families expand beyond top-K; near-tied same-name retrieval is
    # an additional caution even when reference images cannot be compared.
    nearby = [r for r in ranked if normalize_text(r["name"]) == normalize_text(top["name"])
              and r.get("language") == top.get("language")
              and ((r.get("local_artwork_verified") and top.get("local_artwork_verified")) or
                   (float(r["visual_score"]) >= min_visual and
                    abs(float(r["visual_score"]) - float(top["visual_score"])) < min_gap))]
    members: dict[tuple, dict] = {}
    for row in [*family, *nearby, top]:
        item = dict(row)
        if normalize_text(item["name"]) != normalize_text(top["name"]) or item.get("language") != top.get("language"):
            continue
        item.setdefault("card_id", item.get("id"))
        k = printing_key(item)
        old = members.get(k)
        # Keep the actual visual leader for its printing, preserving its URL.
        if old is None or item["card_id"] == top["card_id"]:
            members[k] = item
    if len(members) < 2:
        return PrintingDecision(False)
    choices = list(members.values())
    top_key = printing_key(top)
    choices.sort(key=lambda r: (printing_key(r) != top_key, str(r["card_id"])))
    # Unknown confidence/location cannot prove a printing. Only strongly read
    # syntactically structured identifiers may disambiguate automatically.
    reliable = [h for h in hits if h.region == "collector" and
                h.confidence is not None and h.confidence >= MIN_IDENTIFIER_CONFIDENCE
                and ("/" in h.text or any(c.isalpha() for c in h.text))]
    matching = [r for r in choices if any(
        number_matches_identifiers([h], accepted_collector_numbers(r)) is True for h in reliable)]
    # Evidence must resolve to the leader, and every reliable observation must
    # agree with it. Shared numbers, unknown siblings and conflicts abstain.
    top_row = next(r for r in choices if printing_key(r) == top_key)
    top_consistent = reliable and all(number_matches_identifiers([h], accepted_collector_numbers(top_row)) is True
                                     for h in reliable)
    if len(matching) == 1 and printing_key(matching[0]) == top_key and top_consistent and not reference_incomplete:
        return PrintingDecision(False)
    reason = "shared_printing_identifier" if len(matching) > 1 else "printing_not_proven"
    ids = sorted(str(r["card_id"]) for r in choices)
    group_id = "reference-group:" + hashlib.sha256("\n".join(ids).encode()).hexdigest()[:16]
    guidance = (
        "These printings may share artwork or printed numbers. Choose the exact set manually, "
        "or retake with all four corners, the collector number and any printing stamps visible."
    )
    return PrintingDecision(True, reason, tuple(choices), group_id,
                            not reference_incomplete, tuple(h.text for h in reliable), guidance)
