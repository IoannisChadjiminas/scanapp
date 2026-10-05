"""Keep printed identity outside an artwork-only retrieval window."""
from dataclasses import replace
import re
from app.recognition.ocr import OcrHit, inverted_card_layout
from app.recognition.rank import extract_collector_candidates, name_match


def original_footer_supports_skip(selected, original, candidates):
    """Do not spend enlarged-footer reads on a metadata-clipped proposal.

    This only prunes optional retries. Initial observations survive and the
    pipeline marks the printing unconfirmed. A bare digit, holder label,
    different title, weak read or contradictory identifier never qualifies.
    """
    from app.recognition.identity import structured_identity_agrees
    if selected.failed or original.failed or inverted_card_layout(original):
        return False
    def confidence(result):
        return max((h.confidence or 0 for h in result.hits
                    if h.region == 'name' and h.text == result.name_text), default=0)
    if (min(confidence(selected), confidence(original)) < .95
            or not selected.name_text or not original.name_text
            or selected.name_text.strip().casefold() != original.name_text.strip().casefold()
            or extract_collector_candidates([], hits=selected.hits)):
        return False
    numbers = extract_collector_candidates([], hits=original.hits)
    explicit = [h for h in numbers if h.region == 'collector' and h.confidence is not None
                and h.confidence >= .95 and ('/' in h.text or any(c.isalpha() for c in h.text))]
    return bool(explicit) and any(structured_identity_agrees(dict(row),
        ocr_name=original.name_text, name_confidence=confidence(original),
        numbers=numbers, languages=()) for row in candidates)


def complete_frame_probe_allowed(image, *, profile, orientation):
    # Windows and loose contour proposals can both clip the printed header
    # and footer. Prefer a literal probe of an upright, card-shaped upload.
    # A landscape desk/slab, detected inner frame, or explicit rotated query
    # must keep the established OCR path. No inferred corners prove identity.
    return (profile.startswith(('window_', 'loose_')) and orientation == 0
            and .69 <= image.width/image.height <= .74 and min(image.size) >= 450)


def complete_frame_identity_supported(ocr, visual_names):
    if ocr.failed or inverted_card_layout(ocr):
        return False
    confidence = max((h.confidence or 0 for h in ocr.hits
                      if h.region == 'name' and h.text == ocr.name_text), default=0)
    numbers = extract_collector_candidates([], hits=ocr.hits)
    explicit = any(h.region == 'collector' and h.confidence is not None
                   and h.confidence >= .85 and '/' in h.text for h in numbers)
    # Read literal image text; never substitute a candidate's expected title
    # or number. This gate changes the OCR frame, not printing certainty.
    return confidence >= .90 and explicit and any(name_match(ocr.name_text, name) for name in visual_names)


def complete_frame_title_supported(ocr, visual_names):
    """Reuse a clear original title instead of reading an artwork crop again.

    This is only OCR frame selection. Without a reliable printed identifier,
    callers must keep printing review; title evidence never proves a reprint.
    """
    if ocr.failed or inverted_card_layout(ocr) or not ocr.name_text:
        return False
    confidence = max((h.confidence or 0 for h in ocr.hits
                      if h.region == 'name' and h.text == ocr.name_text), default=0)
    return confidence >= .95 and any(name_match(ocr.name_text, name) for name in visual_names)


def normalize_complete_frame_footer(ocr):
    """Separate one adjacent set/rarity glyph from an observed fraction.

    Never repair digits or denominators. Restrict this to a complete isolated
    footer hit with measured high confidence. Raw lines remain in diagnostics.
    Generic catalogue parsers and weak/holder observations stay unchanged.
    """
    hits=[]
    changes=[]
    for hit in ocr.hits:
        match=re.fullmatch(r'((?:TG|GG)?\d{1,4}\s*/\s*(?:TG|GG)?\d{1,4})([A-Z★☆●◆■])',hit.text.strip(),re.I)
        if (hit.region=='collector' and hit.confidence is not None
                and hit.confidence>=.85 and match):
            hits.append(OcrHit(match[1],hit.confidence,hit.region))
            changes.append(dict(observed=hit.text, fraction=match[1], confidence=hit.confidence))
        else:
            hits.append(hit)
    return replace(ocr,hits=hits), changes
