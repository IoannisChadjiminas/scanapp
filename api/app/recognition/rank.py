from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any
import unicodedata

COLLECTOR_RE = re.compile(
    r"\b([A-Z]{0,4}\d{1,4}(?:/\d{1,4})?)\b",
    re.IGNORECASE,
)


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in text if char.isalnum())


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
        if compact and any(char.isdigit() for char in compact) and compact not in found:
            found.append(compact.upper())
    return found


def name_match(ocr_name: str | None, card_name: str) -> bool:
    if not ocr_name:
        return False
    score = similar(ocr_name, card_name)
    left = normalize_text(ocr_name)
    right = normalize_text(card_name)
    if score >= 0.72:
        return True
    cjk = any(ord(char) > 0x2E80 for char in left)
    min_len = 2 if cjk else 4
    if left and right and len(left) >= min_len and (left in right or right in left):
        return True
    return False


def _norm_digits(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if not digits:
        return ""
    return digits.lstrip("0") or "0"


def _collector_left(value: str) -> str:
    for part in re.split(r"[^\d]+", value.strip()):
        if part:
            return part
    return ""


def _collector_fraction(value: str) -> tuple[str, str | None]:
    compact = (value or "").replace(" ", "")
    match = re.search(r"(?:[A-Z]{0,4})(\d{1,4})/(\d{1,4})", compact, re.IGNORECASE)
    if match:
        return _norm_digits(match.group(1)), _norm_digits(match.group(2))
    left = _norm_digits(_collector_left(value))
    return left, None


def number_match(ocr_numbers: list[str], collector_number: str) -> bool | None:
    expected_left, expected_right = _collector_fraction(collector_number)
    if not expected_left:
        return None
    fractions: list[tuple[str, str]] = []
    lefts: list[str] = []
    for token in ocr_numbers:
        left, right = _collector_fraction(token)
        if left and right:
            fractions.append((left, right))
        elif left:
            lefts.append(left)
    if not fractions and not lefts:
        return None
    if fractions:
        if expected_right:
            return (expected_left, expected_right) in fractions
        return any(left == expected_left for left, _right in fractions)
    expected_full = _norm_digits(collector_number)
    for got in lefts:
        if got == expected_left or (expected_full and got == expected_full):
            return True
        if len(got) < 2:
            continue
        if (
            expected_left
            and len(expected_left) >= 2
            and got.startswith(expected_left)
            and len(got) > len(expected_left)
        ):
            return True
        if len(got) >= 3 and expected_left.startswith(got):
            return True
    return False


def rerank(
    visual: list[dict[str, Any]],
    ocr_name: str | None,
    ocr_numbers: list[str],
    ocr_failed: bool,
    detected_languages: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for item in visual:
        combined = float(item["visual_score"])
        consistent: bool | None = None
        name_ok = name_match(ocr_name, item["name"])
        number_ok = number_match(ocr_numbers, item["collector_number"])
        language = str(item.get("language") or "")
        if detected_languages:
            if language in detected_languages:
                combined += 0.05
            elif language:
                combined -= 0.04
        if ocr_failed:
            consistent = None
        elif number_ok is False and ocr_numbers:
            consistent = False
            combined -= 0.12
        elif name_ok or number_ok is True:
            consistent = True
            if name_ok:
                combined += 0.06
            if number_ok is True:
                combined += 0.08
        elif ocr_name and not name_ok:
            consistent = False if similar(ocr_name, item["name"]) < 0.4 else None
            if consistent is False:
                combined -= 0.04
        ranked.append({**item, "combined_score": combined, "ocr_consistent": consistent})
    ranked.sort(key=lambda row: row["combined_score"], reverse=True)
    ranked = _prefer_language_print(ranked, detected_languages)
    return _keep_visual_leader(ranked)


def _prefer_language_print(
    ranked: list[dict[str, Any]],
    languages: tuple[str, ...],
    max_drop: float = 0.10,
) -> list[dict[str, Any]]:
    if not languages or len(ranked) < 2:
        return ranked
    matching = [row for row in ranked if row.get("language") in languages]
    if not matching:
        return ranked
    if ranked[0].get("language") in languages:
        return ranked
    best = max(matching, key=lambda row: float(row["visual_score"]))
    visual_best = max(ranked, key=lambda row: float(row["visual_score"]))
    drop = float(visual_best["visual_score"]) - float(best["visual_score"])
    if drop > max_drop:
        return ranked
    rest = [row for row in ranked if row["card_id"] != best["card_id"]]
    return [best, *rest]


def _keep_visual_leader(
    ranked: list[dict[str, Any]],
    *,
    min_visual: float = 0.78,
    min_gap: float = 0.04,
) -> list[dict[str, Any]]:
    if len(ranked) < 2:
        return ranked
    visual = sorted(ranked, key=lambda row: float(row["visual_score"]), reverse=True)
    lead = visual[0]
    gap = float(lead["visual_score"]) - float(visual[1]["visual_score"])
    if float(lead["visual_score"]) < min_visual or gap < min_gap:
        return ranked
    rest = [row for row in ranked if row["card_id"] != lead["card_id"]]
    return [lead, *rest]


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
    top = suggestions[0]
    language = str(top.get("language") or "")
    peers = (
        [row for row in suggestions if str(row.get("language") or "") == language]
        if language
        else suggestions
    )
    second = 0.0
    for row in sorted(peers, key=lambda item: float(item["visual_score"]), reverse=True):
        if row["card_id"] != top["card_id"]:
            second = float(row["visual_score"])
            break
    gap = float(top["visual_score"]) - second
    if float(top["visual_score"]) >= min_visual and (second <= 0.0 or gap >= min_gap):
        return "matched"
    if float(top["visual_score"]) >= min_visual and top.get("ocr_consistent") is True:
        twins = [
            row
            for row in peers
            if abs(float(row["visual_score"]) - float(top["visual_score"])) < min_gap
        ]
        others = [row for row in twins if row["card_id"] != top["card_id"]]
        if others and all(row.get("ocr_consistent") is False for row in others):
            return "matched"
    return "no_match"
