"""Accuracy, margin and 'likely' rule metrics for the Phase 0 measurements.

A photo is scored by its catalogue group (duplicate rows already collapsed).
`family` lists the groups that share the label's name and collector number
(twins and reprints). A top-1 inside `family` but not equal to the label is a
printing confusion; anything else is a wrong card.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Iterable, Sequence


@dataclass(frozen=True)
class PhotoRecord:
    photo_id: str
    label: str
    category: str  # "unique", "twin-en-ja", "twin-other", "reprint"
    family: frozenset[str]  # label plus every group sharing name and number
    top5: tuple[str, ...]  # frame 0 ranking, best first
    frames: tuple[tuple[str, float], ...]  # per frame: (top-1 group, margin)


@dataclass(frozen=True)
class RuleResult:
    margin_min: float
    stable_frames: int
    photos: int
    shown: int
    wrong_shown: int
    wrong_card_shown: int  # wrong and not a twin/reprint printing confusion
    shown_rate: float
    wrong_rate: float
    wrong_rate_upper95: float


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 1.0
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - spread), min(1.0, centre + spread)


def rate(successes: int, total: int) -> float:
    return successes / total if total else 0.0


def top1_correct(record: PhotoRecord) -> bool:
    return record.frames[0][0] == record.label


def top1_in_family(record: PhotoRecord) -> bool:
    return record.frames[0][0] in record.family


def top5_contains_label(record: PhotoRecord) -> bool:
    return record.label in record.top5


def accuracy(records: Sequence[PhotoRecord]) -> dict[str, float | int]:
    total = len(records)
    top1 = sum(top1_correct(r) for r in records)
    top1_family = sum(top1_in_family(r) for r in records)
    top5 = sum(top5_contains_label(r) for r in records)
    return {
        "photos": total,
        "top1": top1,
        "top1_rate": rate(top1, total),
        "top1_family_rate": rate(top1_family, total),
        "top5": top5,
        "top5_rate": rate(top5, total),
        "top5_lower95": wilson_interval(top5, total)[0],
    }


def margin_distribution(values: Iterable[float]) -> dict[str, float | int]:
    ordered = sorted(v for v in values if math.isfinite(v))
    if not ordered:
        return {"n": 0}

    def pick(q: float) -> float:
        return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]

    return {
        "n": len(ordered),
        "min": ordered[0],
        "p05": pick(0.05),
        "p25": pick(0.25),
        "median": median(ordered),
        "p75": pick(0.75),
        "p95": pick(0.95),
        "max": ordered[-1],
    }


def likely_frame(frames: Sequence[tuple[str, float]], margin_min: float, stable_frames: int) -> tuple[str, int] | None:
    """First frame where the same group is top-1 with margin >= margin_min for N frames in a row."""
    if stable_frames < 1:
        raise ValueError("stable_frames must be at least 1")
    for end in range(stable_frames - 1, len(frames)):
        window = frames[end - stable_frames + 1:end + 1]
        group = window[0][0]
        if all(g == group and m >= margin_min for g, m in window):
            return group, end
    return None


def evaluate_rule(records: Sequence[PhotoRecord], margin_min: float, stable_frames: int) -> RuleResult:
    shown = wrong = wrong_card = 0
    for record in records:
        fired = likely_frame(record.frames, margin_min, stable_frames)
        if fired is None:
            continue
        shown += 1
        group = fired[0]
        if group != record.label:
            wrong += 1
            if group not in record.family:
                wrong_card += 1
    total = len(records)
    return RuleResult(
        margin_min=margin_min,
        stable_frames=stable_frames,
        photos=total,
        shown=shown,
        wrong_shown=wrong,
        wrong_card_shown=wrong_card,
        shown_rate=rate(shown, total),
        wrong_rate=rate(wrong, shown),
        wrong_rate_upper95=wilson_interval(wrong, shown)[1] if shown else 1.0,
    )


def scan_rules(
    records: Sequence[PhotoRecord],
    margins: Sequence[float],
    stable_frame_options: Sequence[int],
) -> list[RuleResult]:
    return [
        evaluate_rule(records, margin_min, stable)
        for stable in stable_frame_options
        for margin_min in margins
    ]


def smallest_risk_rule(results: Sequence[RuleResult], max_wrong_rate: float = 0.01) -> RuleResult | None:
    """Among rules whose observed wrong-likely rate is under the limit, the one showing the most likelies.

    Ties go to the larger margin (more conservative), then the larger stable window.
    """
    eligible = [r for r in results if r.shown > 0 and r.wrong_rate < max_wrong_rate]
    if not eligible:
        return None
    return max(eligible, key=lambda r: (r.shown_rate, r.margin_min, r.stable_frames))
