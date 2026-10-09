"""Keep printed identity outside an artwork-only retrieval window."""
from dataclasses import replace
import re
import time
from app.recognition.ocr import OcrHit, _region, inverted_card_layout
from app.recognition.rank import (accepted_collector_numbers, extract_collector_candidates,
                                  name_match, number_matches_identifiers)


def complete_frame_probe_allowed(image, *, profile, orientation):
    # Only a centered window on an upright, already card-shaped request.
    # A landscape desk/slab, detected inner frame, or explicit rotated query
    # must keep the established OCR path. No inferred corners prove identity.
    return (profile.startswith('window_') and orientation == 0
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


WIDE_FOOTER_TOP = .60
_FRACTION_RE = re.compile(r'\d{1,4}\s*/\s*\d{1,4}')


def wide_footer_allowed(image):
    # A photo wider than a card has room around the card, so the card's
    # footer sits above the bottom strip the normal read looks at.
    return image.width / image.height > .74 and min(image.size) >= 450


def wide_footer_fractions(engine, image, name_text, candidates):
    """Collector fractions from the lower part of an upload wider than a card.

    The text is read as printed, never taken from a candidate. A fraction is
    kept only when it is the printed number of a candidate carrying the title
    that was read, so a neighbouring card in the photo adds nothing. Returns
    the hits and the pass record, or no record when the engine cannot read a
    patch.
    """
    run = getattr(engine, '_run', None)
    if not callable(run) or not name_text:
        return [], None
    patch = _region(image, WIDE_FOOTER_TOP, 1.)
    started = time.perf_counter()
    try:
        texts, scores = run(patch)
    finally:
        record = dict(region='collector', reason='wide_footer', width=patch.width,
                      height=patch.height, ms=round((time.perf_counter() - started) * 1000, 2))
    named = [dict(row) for row in candidates if name_match(name_text, row['name'])]
    hits = []
    for text, score in zip(texts, scores):
        text = (text or '').strip()
        if score is None or score < .85 or not _FRACTION_RE.fullmatch(text):
            continue
        hit = OcrHit(text, float(score), 'collector')
        if any(number_matches_identifiers([hit], accepted_collector_numbers(row)) is True
               for row in named) and all(text != kept.text for kept in hits):
            hits.append(hit)
    return hits, record
