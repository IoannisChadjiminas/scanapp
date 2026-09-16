from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any

COLLECTOR_RE = re.compile(
    r"\b([A-Z]{0,4}\d{1,4}(?:/\d{1,4})?)\b",
    re.IGNORECASE,
)


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def similar(a: str, b: str) -> float:
    left = normalize_text(a)
    right = normalize_text(b)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def extract_collector_candidates(lines: list[str]) -> list[str]:
    found: list[str] = []
    for line in lines:
        for match in COLLECTOR_RE.findall(line.replace(" ", "")):
            token = match.upper()
            if token not in found:
                found.append(token)
        compact = normalize_text(line)
        if compact and compact not in found:
            found.append(compact.upper())
    return found


def name_match(ocr_name: str | None, card_name: str) -> bool:
    if not ocr_name:
        return False
    score = similar(ocr_name, card_name)
    left = normalize_text(ocr_name)
    right = normalize_text(card_name)
    return score >= 0.72 or (left and left in right) or (right and right in left)


def number_match(ocr_numbers: list[str], collector_number: str) -> bool | None:
    expected = normalize_text(collector_number)
    if not expected:
        return None
    if not ocr_numbers:
        return None
    for token in ocr_numbers:
        if normalize_text(token) == expected:
            return True
        if expected in normalize_text(token) or normalize_text(token) in expected:
            return True
    return False


def rerank(
    visual: list[dict[str, Any]],
    ocr_name: str | None,
    ocr_numbers: list[str],
    ocr_failed: bool,
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for item in visual:
        combined = float(item["visual_score"])
        consistent: bool | None = None
        name_ok = name_match(ocr_name, item["name"])
        number_ok = number_match(ocr_numbers, item["collector_number"])
        if ocr_failed:
            consistent = None
        elif name_ok or number_ok is True:
            consistent = True
            if name_ok:
                combined += 0.06
            if number_ok is True:
                combined += 0.08
        elif number_ok is False and ocr_numbers:
            consistent = False
            combined -= 0.12
        elif ocr_name and not name_ok:
            consistent = False if similar(ocr_name, item["name"]) < 0.4 else None
            if consistent is False:
                combined -= 0.04
        ranked.append({**item, "combined_score": combined, "ocr_consistent": consistent})
    ranked.sort(key=lambda row: row["combined_score"], reverse=True)
    return ranked


def decide_status(
    suggestions: list[dict[str, Any]],
    *,
    enable_matched: bool,
    min_visual: float,
    min_gap: float,
    retake: bool,
) -> str:
    if retake:
        return "retake"
    if not suggestions:
        return "no_match"
    if not enable_matched:
        return "no_match"
    top = suggestions[0]
    second = suggestions[1]["combined_score"] if len(suggestions) > 1 else 0.0
    gap = float(top["combined_score"]) - float(second)
    if float(top["visual_score"]) >= min_visual and gap >= min_gap:
        return "matched"
    return "no_match"
