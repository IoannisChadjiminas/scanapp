from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Any
import unicodedata

from app.recognition.ocr import OcrHit

COLLECTOR_RE = re.compile(
    r"\b((?:[A-Z]{1,4})?\d{1,4}(?:[A-Z])?(?:/\d{1,4})?)\b",
    re.IGNORECASE,
)
COLLECTOR_PARTS_RE = re.compile(
    r"^([A-Z]{1,4})?(\d{1,4})(?:[A-Z])?(?:/(\d{1,4}))?$",
    re.IGNORECASE,
)
RELIABLE_COLLECTOR_CONF = 0.55


@dataclass(frozen=True)
class CollectorParts:
    prefix: str
    number: str
    denominator: str | None
    raw: str


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


def parse_collector(value: str | None) -> CollectorParts | None:
    compact = (value or "").replace(" ", "").upper()
    if not compact:
        return None
    match = COLLECTOR_PARTS_RE.fullmatch(compact)
    if not match:
        fraction = re.search(r"^([A-Z]{1,4})?(\d{1,4})/(\d{1,4})$", compact)
        if not fraction:
            return None
        match = fraction
    prefix = (match.group(1) or "").upper()
    number = (match.group(2) or "").lstrip("0") or "0"
    denom_raw = match.group(3) if match.lastindex and match.lastindex >= 3 else None
    denominator = None
    if denom_raw:
        denominator = denom_raw.lstrip("0") or "0"
    return CollectorParts(prefix=prefix, number=number, denominator=denominator, raw=compact)


def extract_collector_candidates(
    lines: list[str],
    hits: list[OcrHit] | None = None,
) -> list[OcrHit]:
    found: list[OcrHit] = []
    seen: set[str] = set()

    def add(item: OcrHit) -> None:
        token = item.text.upper().replace(" ", "")
        if not token or token in seen:
            return
        if parse_collector(token) is None:
            return
        seen.add(token)
        found.append(OcrHit(text=token, confidence=item.confidence, region=item.region))

    for hit in hits or []:
        for match in COLLECTOR_RE.findall(hit.text.replace(" ", "")):
            add(OcrHit(text=match, confidence=hit.confidence, region=hit.region))
    for line in lines:
        for match in COLLECTOR_RE.findall(line.replace(" ", "")):
            add(OcrHit(text=match, region="unknown"))
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


def number_match(
    ocr_numbers: list[str] | list[OcrHit],
    collector_number: str,
) -> bool | None:
    expected = parse_collector(collector_number)
    if expected is None:
        return None
    parsed: list[CollectorParts] = []
    for token in ocr_numbers:
        text = token.text if isinstance(token, OcrHit) else str(token)
        parts = parse_collector(text)
        if parts:
            parsed.append(parts)
    if not parsed:
        return None
    for got in parsed:
        if got.prefix != expected.prefix:
            continue
        if got.number != expected.number:
            continue
        if got.denominator and expected.denominator and got.denominator != expected.denominator:
            continue
        return True
    return False


def _has_reliable_conflict(ocr_numbers: list[OcrHit] | list[str], collector_number: str) -> bool:
    hits = [
        item
        for item in ocr_numbers
        if isinstance(item, OcrHit) and item.reliable
    ]
    if not hits:
        return False
    return number_match(hits, collector_number) is False


def rerank(
    visual: list[dict[str, Any]],
    ocr_name: str | None,
    ocr_numbers: list[str] | list[OcrHit],
    ocr_failed: bool,
    detected_languages: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for item in visual:
        combined = float(item["visual_score"])
        consistent: bool | None = None
        name_ok = name_match(ocr_name, item["name"])
        number_ok = number_match(ocr_numbers, item["collector_number"])
        collector_conflict = _has_reliable_conflict(ocr_numbers, item["collector_number"])
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
            if collector_conflict:
                combined -= 0.08
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
        ranked.append(
            {
                **item,
                "combined_score": combined,
                "ocr_consistent": consistent,
                "collector_conflict": collector_conflict,
            }
        )
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
    if best.get("collector_conflict"):
        return ranked
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
    if lead.get("collector_conflict"):
        return ranked
    gap = float(lead["visual_score"]) - float(visual[1]["visual_score"])
    if float(lead["visual_score"]) < min_visual or gap < min_gap:
        return ranked
    rest = [row for row in ranked if row["card_id"] != lead["card_id"]]
    return [lead, *rest]


def _visual_second(suggestions: list[dict[str, Any]], top_id: str) -> float:
    second = 0.0
    for row in sorted(suggestions, key=lambda item: float(item["visual_score"]), reverse=True):
        if row["card_id"] != top_id:
            return float(row["visual_score"])
    return second


def _finish_twins(
    suggestions: list[dict[str, Any]], top: dict[str, Any], min_gap: float
) -> list[dict[str, Any]]:
    twins = []
    for row in suggestions:
        if row["card_id"] == top["card_id"]:
            continue
        if row.get("name") != top.get("name"):
            continue
        if row.get("collector_number") != top.get("collector_number"):
            continue
        if row.get("language") != top.get("language"):
            continue
        if abs(float(row["visual_score"]) - float(top["visual_score"])) >= min_gap:
            continue
        twins.append(row)
    return twins


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
    visual_lead = max(suggestions, key=lambda row: float(row["visual_score"]))
    if visual_lead.get("collector_conflict") or top.get("collector_conflict"):
        return "uncertain"
    second = _visual_second(suggestions, top["card_id"])
    gap = float(top["visual_score"]) - second
    visual_ok = float(top["visual_score"]) >= min_visual and (second <= 0.0 or gap >= min_gap)
    if _finish_twins(suggestions, top, min_gap):
        return "uncertain"
    if visual_ok:
        if not enable_matched:
            return "uncertain"
        return "matched"
    if float(top["visual_score"]) >= min_visual and top.get("ocr_consistent") is True:
        twins = [
            row
            for row in suggestions
            if abs(float(row["visual_score"]) - float(top["visual_score"])) < min_gap
        ]
        others = [row for row in twins if row["card_id"] != top["card_id"]]
        if others and all(row.get("ocr_consistent") is False for row in others):
            if not enable_matched:
                return "uncertain"
            return "matched"
        if others:
            return "uncertain"
    return "no_match"
