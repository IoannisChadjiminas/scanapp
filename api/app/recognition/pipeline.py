from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import numpy as np

from app.config import Settings
from app.card_images import display_image_url
from app.cardmarket import (
    apply_variants_to_candidate,
    grouped_expansion_skus,
    listing_choice_message,
    snapshot_prices,
    url_for_row,
)
from app.db import coverage_payload
from app.recognition.captures import save_scan_capture
from app.recognition.detect import card_frame_candidates, detect_and_rectify
from app.recognition.frame_fallback import line_frame_candidates, loose_frame_candidates, portrait_window_candidates, slab_interior_candidate
from app.recognition.images import apply_crop, blur_variance, decode_image
from app.recognition.embed import top_k
from app.recognition.identity import likely_identity_agrees, structured_identity_agrees
from app.recognition.confidence import confidence_payload
from app.recognition.presentation import match_presentation
from app.recognition.language import confident_language_texts, expand_language, language_label, resolve_search_languages
from app.recognition.ocr import OcrResult
from app.recognition.orientation import retrieve_oriented
from app.recognition.printing import PrintingDecision, assess_printings
from app.recognition.rank import artwork_evidence_compatible, decide_status, extract_collector_candidates, rerank
from app.recognition.rank import name_match
from app.recognition.runtime import Runtime
from app.schemas import (
    Candidate,
    OcrEvidence,
    PrintingReview,
    ScanResponse,
    ScanStatus,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _card_image_url(row: Any) -> str:
    return display_image_url(row) or f"/api/v1/cards/{row['id']}/image"


def _lookup_cards(conn: sqlite3.Connection, card_ids: list[str]) -> dict[str, sqlite3.Row]:
    if not card_ids:
        return {}
    placeholders = ",".join("?" for _ in card_ids)
    rows = conn.execute(
        f"SELECT * FROM cards WHERE id IN ({placeholders})",
        card_ids,
    ).fetchall()
    return {row["id"]: row for row in rows}


@dataclass
class _ScanEvaluation:
    response: ScanResponse
    timings: dict[str, float]
    input_image: Any
    save: Callable[[], None]
    lead: dict | None
    ocr: OcrResult
    numbers: list
    languages: tuple[str, ...]
    name_confidence: float
    quality_retake: bool
    evidence: dict


def _recognize_bytes_once(
    data: bytes,
    *,
    settings: Settings,
    runtime: Runtime,
    catalog: sqlite3.Connection,
    results: sqlite3.Connection,
    session_id: str,
    crop_x: float | None = None,
    crop_y: float | None = None,
    crop_w: float | None = None,
    crop_h: float | None = None,
    rotation: int = 0,
    skip_detect: bool = False,
    language: str = "auto",
    store_capture: bool | None = None,
    _frame_override: tuple[str, Any] | None = None,
) -> _ScanEvaluation:
    started = time.perf_counter()
    timings: dict[str, float] = {}
    snapshot, embedder, ocr_engine = runtime.require()
    coverage_model = coverage_payload(catalog)

    decoded = decode_image(data, settings.max_image_pixels)
    input_image = apply_crop(decoded.image, crop_x, crop_y, crop_w, crop_h, rotation)
    image = input_image
    timings["decode_ms"] = (time.perf_counter() - started) * 1000

    mark = time.perf_counter()
    detected = False
    if _frame_override is not None:
        image = _frame_override[1]
    elif not skip_detect:
        image, detected = detect_and_rectify(image)
    timings["detect_ms"] = (time.perf_counter() - mark) * 1000

    # Respect an explicit language while selecting orientation. Automatic
    # language detection follows OCR on the selected frame.
    requested = resolve_search_languages(language, [])
    keep = None
    if requested.reason == "user" and requested.search and runtime.card_languages is not None:
        keep = np.isin(runtime.card_languages, list(requested.search))
    query_vectors = {}
    frame_selection = {}
    alternatives = []
    mark = time.perf_counter()
    if not skip_detect and _frame_override is None:
        if detected:
            alternatives.append(('as_supplied', input_image))
            slab = slab_interior_candidate(image)
            if slab is not None:
                alternatives.append(slab)
        alternatives.extend((f'frame_{i}', frame) for i, frame in
                            enumerate(card_frame_candidates(input_image, limit=2)[1:], start=1))
        alternatives.extend((f'loose_{i}', frame) for i, frame in
                            enumerate(loose_frame_candidates(input_image, limit=2)))
        alternatives.extend(portrait_window_candidates(input_image))
    timings['frame_proposal_ms'] = (time.perf_counter() - mark) * 1000
    image, indices, scores, orientation_timings = retrieve_oriented(
        image, embedder, snapshot.embeddings,
        mode=settings.preprocess_config, keep=keep,
        min_visual=settings.threshold_min_visual,
        min_gap=settings.threshold_min_gap,
        query_vectors=query_vectors,
        alternate_frames=alternatives,
        selection_metadata=frame_selection,
    )
    if _frame_override is not None:
        frame_selection['profile'] = _frame_override[0]
    inferred_frame = frame_selection.get('profile','').startswith(('line_', 'loose_', 'window_', 'slab_'))
    if frame_selection.get('profile') == 'as_supplied' or inferred_frame:
        detected = False
    timings.update(orientation_timings)
    blur = blur_variance(image)
    too_small = min(image.size) < settings.threshold_min_side
    too_blurry = blur < settings.threshold_blur
    retake = too_small or too_blurry
    artwork_hits = []
    artwork_index = getattr(runtime, "artwork_index", None)
    ocr = OcrResult(failed=True)
    mark = time.perf_counter()
    if settings.use_ocr and ocr_engine is not None and not retake:
        ocr = ocr_engine.read(image)
        # A retrieval window can cut away the footer even when it exists in
        # the uploaded image. Consult the uncropped input once, only for an
        # agreeing title plus explicit, confidence-qualified identifiers.
        # Supplement, never replace, first-pass evidence; later contradictions
        # remain visible to the normal ranking/printing safety rules.
        if inferred_frame and ocr.name_text and not ocr.failed:
            first_numbers = extract_collector_candidates([], hits=ocr.hits)
            has_explicit = any(h.confidence is not None and h.confidence >= .85
                and ('/' in h.text or any(c.isalpha() for c in h.text)) for h in first_numbers)
            title_conf = max((h.confidence or 0. for h in ocr.hits
                              if h.region == 'name' and h.text == ocr.name_text), default=0.)
            if not has_explicit and title_conf >= .85:
                raw_ocr = ocr_engine.read(input_image)
                raw_title_conf = max((h.confidence or 0. for h in raw_ocr.hits
                    if h.region == 'name' and h.text == raw_ocr.name_text), default=0.)
                if raw_title_conf >= .85 and name_match(raw_ocr.name_text, ocr.name_text):
                    extra = [h for h in extract_collector_candidates([], hits=raw_ocr.hits)
                        if h.region == 'collector' and h.confidence is not None and h.confidence >= .85
                        and ('/' in h.text or any(c.isalpha() for c in h.text))]
                    if extra:
                        ocr.hits.extend(extra)
                        ocr.lines.extend(h.text for h in extra)
                        ocr.collector_retry_used = True
                        ocr.collector_retry_contributed = True
    timings["ocr_ms"] = (time.perf_counter() - mark) * 1000
    if artwork_index is not None and not retake:
        artwork_hits, artwork_timings = artwork_index.search(
            image, embedder, mode=settings.preprocess_config,
            as_supplied_vector=query_vectors[id(image)],
            languages=tuple(requested.search) if requested.reason == "user" else (),
        )
        timings.update(artwork_timings)
    query_image = image

    decision = resolve_search_languages(
        language,
        confident_language_texts(ocr.hits),
    )
    numbers = extract_collector_candidates(
        [line for line in [ocr.collector_text, *ocr.lines] if line], hits=ocr.hits)
    rank_languages = decision.search if decision.reason == 'user' else expand_language(decision.detected)
    name_confidence = max((h.confidence or 0.0 for h in ocr.hits
                          if h.text == ocr.name_text and h.region == 'name'), default=0.0)
    mark = time.perf_counter()
    metadata_index = getattr(runtime, 'metadata_index', None)
    metadata_ids = metadata_index.candidates(ocr_name=ocr.name_text,
        name_confidence=name_confidence, numbers=numbers, languages=rank_languages) if metadata_index else []
    timings['metadata_retrieve_ms'] = (time.perf_counter() - mark) * 1000
    visual: list[dict[str, Any]] = []
    selected_ids = [str(snapshot.card_ids[i]) for i in indices]
    full_ids = set(selected_ids)
    artwork_by_id = {h.card_id: h for h in artwork_hits}
    selected_ids.extend(h.card_id for h in artwork_hits if h.card_id not in full_ids)
    selected_ids.extend(cid for cid in metadata_ids if cid not in selected_ids)
    cards = _lookup_cards(catalog, selected_ids)
    full_scores = {str(snapshot.card_ids[i]): float(score)
                   for i, score in zip(indices, scores, strict=True)}
    positions = getattr(runtime, 'card_positions', None) or (
        {str(cid): i for i, cid in enumerate(snapshot.card_ids)} if artwork_hits or metadata_ids else {})
    for card_id in selected_ids:
        score = full_scores.get(card_id)
        if score is None:
            position = positions.get(card_id)
            score = float(snapshot.embeddings[position] @ query_vectors[id(image)]) if position is not None else 0.
        row = cards.get(card_id)
        if row is None:
            continue
        visual.append(
            {
                "card_id": card_id,
                "name": row["name"],
                "set_id": row["set_id"],
                "set_name": row["set_name"],
                "collector_number": row["collector_number"],
                "printed_collector_number": (
                    str(row["printed_collector_number"] or "")
                    if "printed_collector_number" in row.keys()
                    else ""
                ),
                "image_url": _card_image_url(row),
                "visual_score": float(score),
                "combined_score": float(score),
                "ocr_consistent": None,
                "language": str(row["language"] or ""),
                "rarity": str(row["rarity"] or ""),
                "cardmarket_url": url_for_row(row),
                "retrieved_via": (["full_card"] if card_id in full_ids else []) +
                                 (["artwork"] if card_id in artwork_by_id else []) +
                                 (["ocr_metadata"] if card_id in metadata_ids else []),
                "artwork_score": artwork_by_id[card_id].score if card_id in artwork_by_id else None,
                "artwork_profile": artwork_by_id[card_id].reference_profile if card_id in artwork_by_id else None,
            }
        )

    combined = rerank(
        visual,
        ocr.name_text,
        numbers,
        ocr.failed,
        detected_languages=rank_languages,
        name_confidence=name_confidence,
        require_confident_ocr=True,
    )
    # Shortlist-only local verification can recover artwork from a crop. Its
    # feature counts never become embedding scores/probabilities, and a rescued
    # candidate is never automatically accepted as a single printing.
    mark = time.perf_counter()
    local_matches = []
    framing_unverified = False
    verifier = getattr(runtime, "artwork_verifier", None)
    ratio = image.width / image.height
    if combined and not retake and verifier is not None and (
        float(combined[0]["visual_score"]) < settings.threshold_min_visual
        or not .62 <= ratio <= .80
        # A high global score with weak OCR and close visual neighbours can
        # still be unresolved. Verify geometry instead of lowering thresholds
        # or requiring a missing title to become confident identity evidence.
        or (name_confidence < .85 and len(combined) > 1
            and float(combined[0]['visual_score']) - float(combined[1]['visual_score']) < settings.threshold_min_gap)
    ):
        references = []
        seen_printings = set()
        # Reserve verification slots for new artwork candidates so a weak full
        # stream cannot consume all eight slots. No score mixing or confidence
        # boost for agreeing retrieval streams.
        local_order = combined
        if artwork_hits:
            art_only = [r for h in artwork_hits for r in combined
                        if r["card_id"] == h.card_id and r["card_id"] not in full_ids]
            local_order = [*combined[:4], *art_only[:4], *combined[4:]]
        # Geometry can verify art on a sibling with a different collector
        # number; otherwise an older reprint occupying top-K would block the
        # whole family. Name/language constrain identity verification, while
        # collector compatibility constrains the chosen printing below.
        local_order = [r for r in local_order if artwork_evidence_compatible(
            r, ocr_name=ocr.name_text, name_confidence=name_confidence,
            numbers=[], languages=rank_languages)]
        for item in local_order:
            row = cards.get(item["card_id"])
            key = (item["set_name"], item["collector_number"], item["language"])
            if row is not None and key not in seen_printings:
                seen_printings.add(key)
                references.append((item["card_id"], str(row["image_path"] or "")))
        local_matches = verifier.verify(image, references) if references else []
        framing_unverified = not local_matches and (
            not .62 <= ratio <= .80 or
            (not skip_detect and not detected and
             float(combined[0]["visual_score"]) < settings.threshold_min_visual)
        )
        if local_matches:
            verified_ids = {m.card_id for m in local_matches}
            eligible = [m for m in local_matches if artwork_evidence_compatible(
                next(r for r in combined if r["card_id"] == m.card_id),
                ocr_name=ocr.name_text, name_confidence=name_confidence,
                numbers=numbers, languages=rank_languages)]
            # If none resolve the metadata, use only an artwork family seed;
            # below it must expand to review choices or request a retake.
            chosen_id = (eligible or local_matches)[0].card_id
            for item in combined:
                item["local_artwork_verified"] = item["card_id"] in verified_ids
            combined.sort(key=lambda r: (r["card_id"] == chosen_id,
                                        r["card_id"] in verified_ids), reverse=True)
    timings["local_artwork_ms"] = (time.perf_counter() - mark) * 1000
    framing_review_supported = bool(combined and not retake
        and float(combined[0]['visual_score']) >= settings.threshold_min_visual_ocr
        and structured_identity_agrees(combined[0],ocr_name=ocr.name_text,
            name_confidence=name_confidence,numbers=numbers,languages=rank_languages))
    if framing_review_supported:
        combined[0]['ocr_identity_verified'] = True
    likely_identity_supported = bool(combined and not retake
        and float(combined[0]['visual_score']) < settings.threshold_min_visual
        and likely_identity_agrees(combined[0], ocr_name=ocr.name_text,
            name_confidence=name_confidence, numbers=numbers, languages=rank_languages,
            min_visual=settings.threshold_min_visual_ocr))
    if likely_identity_supported:
        combined[0]['likely_identity_supported'] = True
    # Listing display names/variant aliases are presentation, not OCR identity.
    # Preserve catalogue evidence before Cardmarket enrichment mutates rows.
    reference_identity = dict(combined[0]) if combined else None
    mark = time.perf_counter()
    sku_groups = grouped_expansion_skus(catalog)
    for item in combined:
        apply_variants_to_candidate(catalog, item, groups=sku_groups)
    if combined:
        live_url = combined[0].get("cardmarket_url")
        combined[0]["cardmarket_prices"] = (
            snapshot_prices(catalog, live_url) if live_url else []
        )
    timings["cardmarket_ms"] = (time.perf_counter() - mark) * 1000
    status = decide_status(
        combined,
        enable_matched=settings.enable_matched,
        min_visual=settings.threshold_min_visual,
        min_visual_ocr=settings.threshold_min_visual_ocr,
        min_gap=settings.threshold_min_gap,
        retake=retake,
    )
    if local_matches:
        status = "uncertain"
    # Upscaled collector OCR can support a review, never introduce a new
    # automatic claim. It does not add independent pixels or calibrated proof.
    if ocr.collector_retry_contributed and status == 'matched':
        status = 'uncertain'
    # A foreground/min-area rectangle is only a retrieval proposal. Even a
    # strong global match on it stays reviewable, never an automatic printing.
    if inferred_frame and status == 'matched':
        status = 'uncertain'
    if combined and combined[0].get('retrieved_via') == ['ocr_metadata'] and status == 'matched':
        status = 'uncertain'
    if combined and decision.detected in {'ja','ko','zh','zh-cn','zh-tw'} and combined[0].get('language') not in rank_languages:
        status = 'retake'
        retake = True
        framing_unverified = True
    if framing_unverified:
        if framing_review_supported or likely_identity_supported:
            status = 'uncertain'
        else:
            status = "retake"
            retake = True
    mark = time.perf_counter()
    family, incomplete = [], True
    if combined and not retake and (float(combined[0]["visual_score"]) >= settings.threshold_min_visual or local_matches or framing_review_supported or likely_identity_supported):
        index = getattr(runtime, "printing_index", None)
        if index is not None:
            family, incomplete = index.family(catalog, combined[0])
            # A cropped shared illustration can favor a different reprint's
            # reference. Expand EVERY geometrically verified seed, not just the
            # winning reference, so its siblings are not lost outside top-K.
            for match in local_matches:
                seed = next(r for r in combined if r["card_id"] == match.card_id)
                siblings, missing = index.family(catalog, seed)
                family.extend(siblings)
                incomplete = incomplete or missing
    printing = assess_printings(
        combined, family=family, hits=numbers, reference_incomplete=incomplete,
        min_visual=settings.threshold_min_visual, min_gap=settings.threshold_min_gap,
        retake=retake,
    )
    printing_review = None
    if likely_identity_supported and not framing_review_supported and not printing.ambiguous and not retake:
        # Even a single retrieved printing isn't proof that no reprints exist.
        # Require explicit selection using the existing review/feedback contract.
        printing = PrintingDecision(True, reason='likely_identity_printing_unverified',
            members=(combined[0],), candidate_group_id='likely:' + combined[0]['card_id'],
            reference_coverage_complete=False,
            guidance='Likely card identified. Confirm the exact set, collector number and finish, or retake with the full card visible.')
    if printing.ambiguous:
        status = "printing_ambiguous"
        printing_review = PrintingReview(
            reason=printing.reason, candidate_group_id=printing.candidate_group_id,
            reference_coverage_complete=printing.reference_coverage_complete,
            collector_evidence=list(printing.collector_evidence),
            plausible_printings=[{
                "card_id": row["card_id"], "name": row["name"],
                "set_name": row["set_name"], "collector_number": row["collector_number"],
                "language": str(row.get("language") or ""),
                "image_url": row.get("image_url") or _card_image_url(row),
                "cardmarket_url": row.get("cardmarket_url"),
            } for row in printing.members],
            guidance=printing.guidance,
        )
    elif local_matches and not framing_review_supported and not artwork_evidence_compatible(
        combined[0], ocr_name=ocr.name_text, name_confidence=name_confidence,
        numbers=numbers, languages=rank_languages
    ):
        status = "retake"
        retake = True
        framing_unverified = True
    timings["printing_review_ms"] = (time.perf_counter() - mark) * 1000
    shown = [] if status in {"no_match", "retake", "failed"} else combined[:1]
    timings["total_ms"] = (time.perf_counter() - started) * 1000

    message = None
    missing_language = (
        decision.reason == "user"
        and bool(decision.search)
        and keep is not None
        and not bool(np.any(keep))
    )
    if retake and too_blurry:
        message = "The photograph is too blurry for useful recognition. Try again."
    elif retake and too_small:
        message = "Move closer so the card fills more of the frame."
    elif framing_unverified and framing_review_supported:
        message = 'The visible name and collector number agree. Photo framing was not verified; check the exact printing and finish before confirming.'
    elif likely_identity_supported and not retake:
        message = 'Likely card identified from visual and name evidence. The exact printing and finish are unconfirmed; select them explicitly or retake with the bottom number visible.'
    elif framing_unverified:
        message = "This crop could not be verified. Retake with the full card, including its artwork and bottom collector number."
    elif missing_language:
        labels = ", ".join(language_label(code) for code in decision.search)
        message = (
            f"No {labels} cards are indexed. Re-run bootstrap with "
            f"TCGDEX_LANGUAGES including {', '.join(decision.search)}."
        )
    elif status == "matched":
        message = listing_choice_message("matched", shown[0] if shown else None)
    elif status == "uncertain":
        message = listing_choice_message("uncertain", shown[0] if shown else None)
    elif status == "printing_ambiguous":
        message = printing.guidance
    elif status in {"no_match"}:
        message = "This photograph did not match a catalogue card."
    if not detected and not skip_detect and status != "retake":
        extra = " Automatic card detection was unreliable; using the provided crop."
        message = (message or "") + extra

    suggestions = [Candidate.model_validate(item) for item in shown]
    scan_id = str(uuid.uuid4())
    created_at = _now()
    versions = runtime.versions()
    versions['presentation'] = 'best-match-v1'
    presentation = match_presentation(combined, status=status, printing_review=printing_review,
                                      min_visual=settings.threshold_min_visual_ocr)
    confidence = confidence_payload(combined, status=status,
        name_confidence=name_confidence, numbers=numbers,
        framing_unverified=framing_unverified, quality_retake=too_small or too_blurry,
        min_visual=settings.threshold_min_visual,
        structured_identity=bool(reference_identity and structured_identity_agrees(reference_identity,
            ocr_name=ocr.name_text, name_confidence=name_confidence, numbers=numbers, languages=rank_languages)),
        likely_identity=likely_identity_supported)
    ocr_payload = {
        "name_text": ocr.name_text,
        "collector_text": ocr.collector_text,
        "lines": ocr.lines,
        "failed": ocr.failed,
        "collector_retry_used": ocr.collector_retry_used,
        "collector_retry_contributed": ocr.collector_retry_contributed,
        "confidence": confidence.model_dump(mode='json'),
        "match_presentation": presentation.model_dump(mode='json'),
        "hits": [
            {
                "text": hit.text,
                "confidence": hit.confidence,
                "region": hit.region,
            }
            for hit in ocr.hits
        ],
        "detected_language": decision.detected,
        "requested_language": decision.requested,
        "search_languages": list(decision.search),
        "printing_review": printing_review.model_dump(mode="json") if printing_review else None,
        "local_artwork_matches": [vars(m) for m in local_matches],
        "artwork_retrieval": [vars(h) for h in artwork_hits],
        "metadata_candidate_ids": metadata_ids,
        "framing_unverified": framing_unverified,
        "framing_review_supported": framing_review_supported,
        "likely_identity_supported": likely_identity_supported,
        "frame_selection": frame_selection,
        "frame_detected": detected,
        "query_size": list(image.size),
    }
    def save() -> None:
        results.execute(
            """
        INSERT INTO scans (
            id, session_id, created_at, status, preprocessing, model_revision,
            catalogue_version, ocr_version, ranking_version, threshold_config_json,
            ocr_json, visual_ranking_json, combined_ranking_json, timings_json,
            confirmed_card_id, rejected, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL)
            """,
            (
                scan_id,
                session_id,
                created_at,
                status,
                settings.preprocess_config,
                versions["model_revision"],
                versions["catalogue"],
                versions["ocr"],
                versions["ranking"],
                json.dumps(runtime.threshold_config()),
                json.dumps(ocr_payload),
                # Persist the bounded union for verification-miss audits;
                # this never expands the public suggestions.
                json.dumps(visual),
                json.dumps(combined),
                json.dumps(timings),
            ),
        )
        results.commit()
        persist = settings.store_captures if store_capture is None else store_capture
        if persist:
            try:
                save_scan_capture(
                    settings=settings,
                    scan_id=scan_id,
                    session_id=session_id,
                    created_at=created_at,
                    status=status,
                    message=message.strip() if message else None,
                    input_image=input_image,
                    query_image=query_image,
                    request={
                        "crop_x": crop_x,
                        "crop_y": crop_y,
                        "crop_w": crop_w,
                        "crop_h": crop_h,
                        "rotation": rotation,
                        "skip_detect": skip_detect,
                        "language": language,
                    },
                    image_stats={
                        "input_size": list(input_image.size),
                        "query_size": list(query_image.size),
                        "blur": round(float(blur), 2),
                        "detected": detected,
                        "too_small": too_small,
                        "too_blurry": too_blurry,
                    },
                    ocr=ocr_payload,
                    predicted=shown,
                    visual=visual,
                    timings=timings,
                    versions=versions,
                )
            except Exception:  # noqa: BLE001 - capture files must never fail a scan
                pass

    response = ScanResponse(
        id=scan_id,
        status=ScanStatus(status),
        suggestions=suggestions,
        ocr=OcrEvidence(
            name_text=ocr.name_text,
            collector_text=ocr.collector_text,
            lines=ocr.lines,
            failed=ocr.failed,
            collector_retry_used=ocr.collector_retry_used,
            collector_retry_contributed=ocr.collector_retry_contributed,
        ),
        coverage=coverage_model,
        timings_ms={key: round(value, 2) for key, value in timings.items()},
        versions=versions,
        message=message.strip() if message else None,
        detected_language=decision.detected,
        search_languages=list(decision.search),
        printing_review=printing_review,
        confidence=confidence,
        **presentation.model_dump(mode='json'),
    )
    return _ScanEvaluation(response, timings, input_image, save,
                           reference_identity, ocr, numbers,
                           tuple(rank_languages), name_confidence, too_small or too_blurry, ocr_payload)


def recognize_bytes(
    data: bytes,
    *,
    settings: Settings,
    runtime: Runtime,
    catalog: sqlite3.Connection,
    results: sqlite3.Connection,
    session_id: str,
    crop_x: float | None = None,
    crop_y: float | None = None,
    crop_w: float | None = None,
    crop_h: float | None = None,
    rotation: int = 0,
    skip_detect: bool = False,
    language: str = "auto",
    store_capture: bool | None = None,
) -> ScanResponse:
    """Evaluate first, then persist exactly one result and optional capture.

    A failed framing decision may try ONE line-supported frame. Existing useful
    results are never replaced. Recovery uses the same identity/quality guards,
    stays review-only, and cannot discard strong first-pass contradictions.
    Explicit crops and quality retakes do not trigger this extra OCR pass.
    """
    started = time.perf_counter()
    kwargs = dict(settings=settings, runtime=runtime, catalog=catalog,
                  results=results, session_id=session_id, crop_x=crop_x,
                  crop_y=crop_y, crop_w=crop_w, crop_h=crop_h, rotation=rotation,
                  skip_detect=skip_detect, language=language, store_capture=store_capture)
    first = _recognize_bytes_once(data, **kwargs)
    selected = first
    attempted = False
    proposal_ms = embed_ms = 0.
    recovery = {'hypotheses':0,'proposal_profile':None,'proposal_score':None,
                'retry_status':None,'retry_top_id':None,'identity_compatible':None,
                'selection_identity':None}
    if (not skip_detect and all(v is None for v in (crop_x,crop_y,crop_w,crop_h))
            and first.response.status == ScanStatus.retake and not first.quality_retake):
        mark = time.perf_counter()
        # Slab edges can outrank the inner card geometrically. Eight cheap
        # vector probes still lead to at most ONE additional OCR evaluation.
        frames = line_frame_candidates(first.input_image,limit=8)
        recovery['hypotheses'] = len(frames)
        proposal_ms = (time.perf_counter()-mark)*1000
        if frames:
            snapshot, embedder, _ = runtime.require()
            requested = resolve_search_languages(language,[])
            keep = None
            if requested.reason == 'user' and requested.search and runtime.card_languages is not None:
                keep = np.isin(runtime.card_languages,list(requested.search))
            best = None
            guided_position = None
            if (first.lead and first.name_confidence >= .85
                    and name_match(first.ocr.name_text,first.lead['name'])
                    and artwork_evidence_compatible(first.lead,ocr_name=first.ocr.name_text,
                        name_confidence=first.name_confidence,numbers=[],languages=first.languages)):
                positions = getattr(runtime,'card_positions',{}) or {}
                guided_position = positions.get(first.lead['card_id'])
                if guided_position is not None:
                    recovery['selection_identity'] = first.lead['card_id']
            mark = time.perf_counter()
            for i,frame in enumerate(frames):
                vector = embedder.embed(frame,settings.preprocess_config)
                if guided_position is not None:
                    score = float(snapshot.embeddings[guided_position] @ vector)
                else:
                    _,scores = top_k(snapshot.embeddings,vector,k=1,keep=keep)
                    score = float(scores[0]) if len(scores) else -1.
                # Proposal selection is not acceptance. The existing OCR-assisted
                # floor permits a readable number/name to rescue a glare image;
                # the complete evaluation still enforces every evidence guard.
                if score >= settings.threshold_min_visual_ocr and (best is None or score > best[0]+settings.threshold_min_gap):
                    best = (score,i,frame)
            embed_ms = (time.perf_counter()-mark)*1000
            if best is not None:
                attempted = True
                recovery.update(proposal_profile=f'line_{best[1]}',proposal_score=best[0])
                retry = _recognize_bytes_once(data, **kwargs,
                    _frame_override=(f'line_{best[1]}',best[2]))
                compatible = bool(retry.lead and artwork_evidence_compatible(
                    retry.lead,ocr_name=first.ocr.name_text,
                    name_confidence=first.name_confidence,numbers=first.numbers,
                    languages=first.languages))
                recovery.update(retry_status=retry.response.status.value,
                                retry_top_id=retry.lead.get('card_id') if retry.lead else None,
                                identity_compatible=compatible)
                if compatible and retry.response.status in {ScanStatus.uncertain,ScanStatus.printing_ambiguous}:
                    selected = retry
                # Include even a rejected retry's cost; never hide wasted work.
                selected.timings['boundary_retry_ms'] = retry.timings['total_ms']
    if selected is not first:
        selected.timings['first_pass_ms'] = first.timings['total_ms']
    selected.timings.update(boundary_proposal_ms=proposal_ms,
                            boundary_selection_ms=embed_ms,
                            boundary_retry_attempted=float(attempted),
                            boundary_retry_selected=float(selected is not first),
                            total_ms=(time.perf_counter()-started)*1000)
    selected.response.timings_ms = {key:round(value,2) for key,value in selected.timings.items()}
    selected.evidence['boundary_recovery'] = {
        **recovery,
        'attempted': attempted, 'selected': selected is not first,
        'first_status': first.response.status.value,
        'first_top_id': first.lead.get('card_id') if first.lead else None,
        'policy': 'one review-only retry; preserve first-pass identity contradictions',
    }
    selected.save()
    return selected.response
