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


def title_only_allowed(full_candidates, artwork_hits, family, *, family_incomplete, image_size):
    """Decide before OCR whether the footer strip can change the answer.

    The collector number only separates same-art printings. Skip it only for
    a card-shaped frame whose two visual streams agree on a leader with a
    complete reference family of exactly one printing. Anything else reads
    the footer as before.
    """
    from app.recognition.printing import printing_key
    width, height = image_size
    if (family_incomplete or not family or not .62 <= width / height <= .80
            or len(full_candidates) < 2):
        return False
    first, second = full_candidates[:2]
    if len({printing_key(row) for row in family}) != 1:
        return False
    if not any(str(row.get('id', row.get('card_id'))) == first['card_id'] for row in family):
        return False
    art = next((h for h in artwork_hits if h.card_id == first['card_id']), None)
    return (first['visual_score'] >= .85
            and first['visual_score'] - second['visual_score'] >= .08
            and art is not None and art.score >= .80)


def title_only_confirmed(ocr, expected_name):
    """A title-only read stands only when it confidently names the leader."""
    if ocr.failed or not ocr.name_text or inverted_card_layout(ocr):
        return False
    confidence = max((h.confidence or 0. for h in ocr.hits
                      if h.region == 'name' and h.text == ocr.name_text), default=0.)
    return confidence >= .95 and name_match(ocr.name_text, expected_name)
