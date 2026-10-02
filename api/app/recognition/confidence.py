"""Auditable evidence for clients; cosine/OCR scores are not probabilities."""
from app.schemas import RecognitionConfidence


def confidence_payload(ranked, *, status, name_confidence, numbers,
                       framing_unverified, quality_retake, min_visual,
                       structured_identity, likely_identity):
    top = ranked[0] if ranked else None
    reasons = []
    if quality_retake:
        reasons.append('image_quality_insufficient')
    if framing_unverified:
        reasons.append('framing_unverified')
    conflicts = [key for key in ('strong_name_conflict', 'structured_collector_conflict',
                                'language_conflict') if top and top.get(key)]
    reasons.extend(conflicts)
    if top and float(top['visual_score']) < min_visual:
        reasons.append('below_automatic_visual_threshold')
    if likely_identity:
        reasons.append('visual_streams_and_name_agree_review_only')
    if not structured_identity:
        reasons.append('exact_printing_not_proven_by_name_and_number')
    reasons.append('finish_not_inferred_from_static_photo')
    shown = status in {'matched', 'uncertain', 'printing_ambiguous'}
    collector_scores = [h.confidence for h in numbers
                        if h.region == 'collector' and h.confidence is not None]
    return RecognitionConfidence(
        candidate_card_id=top['card_id'] if top else None,
        visual_similarity=float(top['visual_score']) if top else None,
        artwork_similarity=top.get('artwork_score') if top else None,
        # A negative margin is possible after OCR/geometric reranking.
        visual_margin=(float(top['visual_score']) - float(ranked[1]['visual_score']))
            if len(ranked) > 1 else None,
        name_ocr_confidence=name_confidence or None,
        collector_ocr_confidence=max(collector_scores, default=None),
        identity='conflicting' if conflicts else ('likely' if likely_identity else
            ('supported' if shown else 'unknown')),
        printing='ambiguous' if status == 'printing_ambiguous' else
            ('metadata_supported' if structured_identity and shown else 'unconfirmed'),
        requires_confirmation=True,
        retake_recommended=status in {'retake', 'no_match', 'failed'},
        reasons=reasons,
    )
