"""Spend optional footer OCR only when identity still needs more evidence."""
from app.recognition.ocr import inverted_card_layout
from app.recognition.rank import extract_collector_candidates, name_match, normalize_text

VERSION = 'supported-identity-footer-v1'


def footer_retry_required(ocr, full_candidates, artwork_hits, *, image_size):
    """Missing text may leave printing unknown, never become printing proof.

    Only skip after untouched initial OCR and two agreeing visual streams.
    Do not prune a weak/partial frame, an observed number (even a weak one),
    a different readable name, or a near-tied full-card shortlist. Catalogue
    identity proposes no expected OCR text and contributes no OCR confidence.
    """
    width, height = image_size
    if (ocr.failed or not .62 <= width / height <= .80
            or inverted_card_layout(ocr) or len(full_candidates) < 2):
        return True
    name = normalize_text(ocr.name_text)
    if len(name) < (2 if any(ord(c) > 0x2E80 for c in name) else 4):
        return True
    confidence = max((h.confidence or 0. for h in ocr.hits
                      if h.region == 'name' and h.text == ocr.name_text), default=0.)
    if confidence < .95 or extract_collector_candidates([], hits=ocr.hits):
        return True
    first, second = full_candidates[:2]
    art = next((h for h in artwork_hits if h.card_id == first['card_id']), None)
    return not (name_match(ocr.name_text, first['name'])
        and first['visual_score'] >= .85
        and first['visual_score'] - second['visual_score'] >= .08
        and art is not None and art.score >= .80)
