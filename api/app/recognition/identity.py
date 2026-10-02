"""Independent, confidence-qualified name/number evidence for review-only rescue."""
from __future__ import annotations
import re

from app.recognition.ocr import OcrHit
from app.recognition.rank import accepted_collector_numbers, artwork_evidence_compatible, name_match, normalize_text, number_matches_identifiers


def review_title_agrees(ocr_name: str | None, card_name: str) -> bool:
    """Review-only tolerance for a garbled Latin mechanic suffix after CJK.

    Require the entire localized name stem (at least four characters) exactly.
    Only one or two unreadable CJK glyphs may replace a suffix; a readable
    different mechanic such as GX versus ex is never interchangeable. The
    caller also requires an explicit collector and the OCR-assisted visual
    floor. This does not alter automatic-match name equality.
    """
    expected, observed = normalize_text(card_name), normalize_text(ocr_name)
    mechanic = re.compile(r'(vmax|vstar|ex|gx|v)$')
    expected_mechanic, observed_mechanic = mechanic.search(expected), mechanic.search(observed)
    if expected_mechanic and observed_mechanic and expected_mechanic[1] != observed_mechanic[1]:
        return False
    if name_match(ocr_name, card_name):
        return True
    match = re.fullmatch(r'([\u3040-\u30ff\u4e00-\u9fff]{4,})(?:ex|gx|vmax|vstar|v)', expected)
    if not match or not observed.startswith(match[1]):
        return False
    tail = observed[len(match[1]):]
    return bool(re.fullmatch(r'[\u3040-\u30ff\u4e00-\u9fff]{1,2}', tail))


def likely_identity_agrees(item: dict, *, ocr_name: str | None,
                           name_confidence: float, numbers: list[OcrHit],
                           languages: tuple[str, ...], min_visual: float) -> bool:
    """Offer a reviewable identity when two visual streams and a name agree.

    This is a presentation gate, not proof or a probability. A metadata-only
    guess, unreadable name or contradictory identifier never qualifies.
    """
    name = normalize_text(ocr_name)
    minimum = 2 if any(ord(c) > 0x2E80 for c in name) else 4
    return bool(name_confidence >= .85 and len(name) >= minimum
        and name_match(ocr_name, item['name'])
        and float(item['visual_score']) >= min_visual
        and {'full_card', 'artwork'}.issubset(item.get('retrieved_via', []))
        and float(item.get('artwork_score') or 0.) >= min_visual
        and not any(item.get(k) for k in ('strong_name_conflict',
            'structured_collector_conflict', 'language_conflict'))
        and artwork_evidence_compatible(item, ocr_name=ocr_name,
            name_confidence=name_confidence, numbers=numbers, languages=languages))


def structured_identity_agrees(item: dict, *, ocr_name: str | None,
                               name_confidence: float, numbers: list[OcrHit],
                               languages: tuple[str, ...]) -> bool:
    """Two visible fields can support review, not certify a printing/finish.

    Missing/unknown-region/bare collector numbers do not qualify. Contradictory
    structured observations and known-language conflicts veto this rescue.
    The caller also requires its existing OCR-assisted visual score floor.
    """
    name = normalize_text(ocr_name)
    minimum = 2 if any(ord(c) > 0x2E80 for c in name) else 4
    if name_confidence < .85 or len(name) < minimum or not review_title_agrees(ocr_name,item['name']):
        return False
    if languages and item.get('language') not in languages:
        return False
    if item.get('strong_name_conflict') or item.get('structured_collector_conflict'):
        return False
    reliable = [h for h in numbers if h.region == 'collector' and h.confidence is not None
                and h.confidence >= .85 and ('/' in h.text or any(c.isalpha() for c in h.text))]
    expected = accepted_collector_numbers(item)
    return bool(reliable and expected) and all(number_matches_identifiers([h],expected) is True
                                               for h in reliable)
