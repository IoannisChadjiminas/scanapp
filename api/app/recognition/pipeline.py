from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import cv2
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
from app.recognition.ocr import OcrResult, inverted_card_layout
from app.recognition.ocr_framing import complete_frame_probe_allowed, complete_frame_identity_supported, normalize_complete_frame_footer
from app.recognition.ocr_cache import RequestOcrCache
from app.recognition.ocr_budget import footer_retry_required, VERSION as OCR_BUDGET_VERSION
from app.recognition.stamp_printing import stamp_printing_hint
from app.recognition.grading import VERSION as GRADING_VERSION
from app.recognition.grading_parallel import GradingJob, parallel_grading_scope
from app.recognition.holder_printing import holder_printing_hint
from app.recognition.orientation import retrieve_oriented
from app.recognition.printing import PrintingDecision, assess_printings
from app.recognition.rank import artwork_evidence_compatible, decide_status, extract_collector_candidates, rerank
from app.recognition.rank import name_match
from app.recognition.runtime import Runtime
from app.schemas import (
    Candidate,
    GradingEvidence,
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
    ranked: list[dict] = field(default_factory=list)
    shown: list[dict] = field(default_factory=list)


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
    _input_observer: Callable | None = None,
    _ocr_cache: RequestOcrCache | None = None,
) -> _ScanEvaluation:
    started = time.perf_counter()
    timings: dict[str, float] = {}
    snapshot, embedder, ocr_engine = runtime.require()
    coverage_model = coverage_payload(catalog)

    decoded = decode_image(data, settings.max_image_pixels)
    input_image = apply_crop(decoded.image, crop_x, crop_y, crop_w, crop_h, rotation)
    if _input_observer is not None:
        _input_observer(input_image)
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
        if not detected:
            slab = slab_interior_candidate(input_image)
            if slab is not None:
                alternatives.append(slab)
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
    inferred_frame = frame_selection.get('profile','').startswith(('line_', 'loose_', 'window_', 'slab_', 'aligned_'))
    if frame_selection.get('profile') == 'as_supplied' or inferred_frame:
        detected = False
    timings.update(orientation_timings)
    blur = blur_variance(image)
    too_small = min(image.size) < settings.threshold_min_side
    too_blurry = blur < settings.threshold_blur
    retake = too_small or too_blurry
    artwork_hits = []
    artwork_index = getattr(runtime, "artwork_index", None)
    adaptive_footer = bool(getattr(settings, 'ocr_adaptive_footer', False))
    artwork_image = None
    full_candidates = []
    if adaptive_footer and artwork_index is not None and not retake:
        # Retrieve independent illustration evidence before deciding whether
        # optional collector retries are useful. Initial OCR stays untouched.
        artwork_hits, artwork_timings = artwork_index.search(
            image, embedder, mode=settings.preprocess_config,
            as_supplied_vector=query_vectors[id(image)],
            languages=tuple(requested.search) if requested.reason == "user" else (),
        )
        timings.update(artwork_timings)
        artwork_image = image
        rows = _lookup_cards(catalog, [str(snapshot.card_ids[i]) for i in indices])
        full_candidates = [dict(card_id=str(snapshot.card_ids[i]), name=rows[str(snapshot.card_ids[i])]['name'],
                                visual_score=float(score))
            for i, score in zip(indices, scores) if str(snapshot.card_ids[i]) in rows]
    ocr = OcrResult(failed=True)
    ocr_passes = []
    ocr_cache_hits = []
    def read_card(frame, scope):
        options = {}
        if adaptive_footer and scope == 'selected' and frame is artwork_image:
            options['collector_retry_policy'] = lambda observed: footer_retry_required(
                observed, full_candidates, artwork_hits, image_size=frame.size)
        observed, cached = (_ocr_cache.read(ocr_engine, frame, **options) if _ocr_cache is not None
                            else (ocr_engine.read(frame, **options), False))
        if cached:
            ocr_cache_hits.append(dict(scope=scope, width=frame.width, height=frame.height))
        else:
            ocr_passes.extend(dict(scope=scope, **p) for p in observed.passes)
        return observed
    original_ocr = None
    original_identity_used = False
    mark = time.perf_counter()
    if settings.use_ocr and ocr_engine is not None and not retake:
        if (getattr(settings, 'ocr_complete_frame_first', False)
                and complete_frame_probe_allowed(input_image,
                    profile=frame_selection.get('profile', ''),
                    orientation=timings.get('orientation_degrees', 0))):
            original_ocr = read_card(input_image, 'complete_frame_probe')
            original_ocr, footer_changes = normalize_complete_frame_footer(original_ocr)
            frame_selection['ocr_complete_frame_footer_normalizations'] = footer_changes
            # Use the existing bounded visual shortlist, not only its first
            # three rows: a metadata-clipped crop may bury the right identity.
            leading = _lookup_cards(catalog, [str(snapshot.card_ids[i]) for i in indices])
            original_identity_used = complete_frame_identity_supported(original_ocr,
                [row['name'] for row in leading.values()])
        ocr = original_ocr if original_identity_used else read_card(image, 'selected')
        frame_selection['ocr_complete_frame_used'] = original_identity_used
        if inverted_card_layout(ocr):
            upright=image.rotate(180,expand=True)
            corrected=read_card(upright, 'upright')
            title_conf=max((h.confidence or 0. for h in corrected.hits
                           if h.region=='name' and h.text==corrected.name_text),default=0.)
            if corrected.name_text and title_conf>=.85 and not inverted_card_layout(corrected):
                frame_selection['inverted_layout_corrected']=True
                frame_selection['discarded_inverted_title']=ocr.name_text
                image,ocr=upright,corrected
                snapshot,embedder,_=runtime.require()
                query_vectors[id(image)]=embedder.embed(image,settings.preprocess_config)
                indices,scores=top_k(snapshot.embeddings,query_vectors[id(image)],k=20,keep=keep)
                timings['orientation_degrees']=(timings.get('orientation_degrees',0.)+180.)%360.
        # A retrieval window can cut away the footer even when it exists in
        # the uploaded image. Consult the uncropped input once, only for an
        # agreeing title plus explicit, confidence-qualified identifiers.
        # Supplement, never replace, first-pass evidence; later contradictions
        # remain visible to the normal ranking/printing safety rules.
        if inferred_frame and not ocr.failed and not original_identity_used:
            first_numbers = extract_collector_candidates([], hits=ocr.hits)
            has_explicit = any(h.confidence is not None and h.confidence >= .85
                and ('/' in h.text or any(c.isalpha() for c in h.text)) for h in first_numbers)
            title_conf = max((h.confidence or 0. for h in ocr.hits
                              if h.region == 'name' and h.text == ocr.name_text), default=0.)
            # A clipped title can be weaker than the same visible title on
            # the original upload. Consult that upload for agreeing evidence,
            # never overwrite a confident different title or collector.
            if (not has_explicit and title_conf >= .85) or .50 <= title_conf < .85 or (ocr.name_text is None and not has_explicit):
                raw_ocr = original_ocr if original_ocr is not None else read_card(input_image, 'original')
                raw_title_conf = max((h.confidence or 0. for h in raw_ocr.hits
                    if h.region == 'name' and h.text == raw_ocr.name_text), default=0.)
                holder_hints=[h for h in extract_collector_candidates([],hits=raw_ocr.hits)
                              if h.region == 'holder_collector']
                agreeing_title=bool(ocr.name_text and name_match(raw_ocr.name_text,ocr.name_text))
                printed_language=resolve_search_languages('auto',confident_language_texts(ocr.hits)).detected
                title_has_localized_script=any('\u3040' <= c <= '\u30ff' or '\u4e00' <= c <= '\u9fff'
                    or '\uac00' <= c <= '\ud7a3' for c in raw_ocr.name_text or '')
                holder_title_compatible=printed_language not in {'ja','ko','zh','zh-cn','zh-tw'} or title_has_localized_script
                if raw_title_conf >= .85 and (agreeing_title or
                        (ocr.name_text is None and holder_hints and holder_title_compatible)):
                    if title_conf < .85:
                        ocr.hits.extend(h for h in raw_ocr.hits
                            if h.region == 'name' and h.text == raw_ocr.name_text)
                        ocr.name_text = raw_ocr.name_text
                        ocr.lines.append(raw_ocr.name_text)
                    ocr.hits.extend(holder_hints)
                    extra = [h for h in extract_collector_candidates([], hits=raw_ocr.hits)
                        if h.region == 'collector' and h.confidence is not None and h.confidence >= .85
                        and ('/' in h.text or any(c.isalpha() for c in h.text))]
                    if extra:
                        ocr.hits.extend(extra)
                        ocr.lines.extend(h.text for h in extra)
                        ocr.collector_retry_used = True
                        ocr.collector_retry_contributed = True
    timings["ocr_ms"] = (time.perf_counter() - mark) * 1000
    timings['ocr_passes_count'] = float(len(ocr_passes))
    timings['ocr_footer_retry_skipped'] = float(ocr.collector_retry_skipped)
    if artwork_index is not None and not retake and image is not artwork_image:
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
    title_ids = metadata_index.title_candidates(ocr_name=ocr.name_text,
        name_confidence=name_confidence, numbers=numbers, languages=rank_languages
    ) if metadata_index and not metadata_ids else []
    geometry_ids=metadata_index.geometry_candidates(ocr_name=ocr.name_text,
        name_confidence=name_confidence,numbers=numbers,languages=rank_languages
    ) if metadata_index and not metadata_ids and not title_ids and hasattr(metadata_index,'geometry_candidates') else []
    timings['metadata_retrieve_ms'] = (time.perf_counter() - mark) * 1000
    visual: list[dict[str, Any]] = []
    selected_ids = [str(snapshot.card_ids[i]) for i in indices]
    full_ids = set(selected_ids)
    artwork_by_id = {h.card_id: h for h in artwork_hits}
    selected_ids.extend(h.card_id for h in artwork_hits if h.card_id not in full_ids)
    selected_ids.extend(cid for cid in metadata_ids if cid not in selected_ids)
    selected_ids.extend(cid for cid in title_ids if cid not in selected_ids)
    selected_ids.extend(cid for cid in geometry_ids if cid not in selected_ids)
    cards = _lookup_cards(catalog, selected_ids)
    full_scores = {str(snapshot.card_ids[i]): float(score)
                   for i, score in zip(indices, scores, strict=True)}
    positions = getattr(runtime, 'card_positions', None) or (
        {str(cid): i for i, cid in enumerate(snapshot.card_ids)} if artwork_hits or metadata_ids or title_ids or geometry_ids else {})
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
                                 (["ocr_metadata"] if card_id in metadata_ids else []) +
                                 (["ocr_title"] if card_id in title_ids else []) +
                                 (["ocr_geometry"] if card_id in geometry_ids else []),
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
        or bool(geometry_ids)
        or any(h.region == 'holder_collector' for h in numbers)
        or combined[0].get('retrieved_via') == ['ocr_title']
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
        if geometry_ids:
            geometry_only=[r for r in combined if r['card_id'] in geometry_ids]
            local_order=[*geometry_only[:4],*local_order]
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
            # Keypoint counts certify shared artwork, not which reprint it is.
            # Preserve the OCR/global ranking among verified, compatible
            # candidates instead of using descriptor count as printing proof.
            preferred_ids = {m.card_id for m in eligible or local_matches}
            chosen_id = next(r['card_id'] for r in combined if r['card_id'] in preferred_ids)
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
    get_groups = getattr(runtime, 'listing_groups', None)
    sku_groups = get_groups(catalog) if get_groups else grouped_expansion_skus(catalog)
    for item in combined:
        apply_variants_to_candidate(catalog, item, groups=sku_groups)
    for item in combined:
        live_url = item.get("cardmarket_url")
        if not live_url:
            continue
        item["cardmarket_prices"] = snapshot_prices(catalog, live_url)
    timings["cardmarket_ms"] = (time.perf_counter() - mark) * 1000
    status = decide_status(
        combined,
        enable_matched=settings.enable_matched,
        min_visual=settings.threshold_min_visual,
        min_visual_ocr=settings.threshold_min_visual_ocr,
        min_gap=settings.threshold_min_gap,
        retake=retake,
    )
    if framing_review_supported and status=='no_match':
        # Independently qualified printed name + explicit collector and the
        # existing OCR-assisted visual floor can support a review result even
        # when another visual neighbour prevented automatic acceptance.
        status='uncertain'
    if local_matches:
        status = "uncertain"
    if any(h.region=='holder_name' for h in ocr.hits) and status=='matched':
        status='uncertain'
    if any(h.region == 'holder_collector' for h in numbers) and status == 'matched':
        status = 'uncertain'
    if any(h.region == 'holder_collector' for h in numbers) and not local_matches and not framing_review_supported:
        status = 'retake'
        retake = True
    # Upscaled collector OCR can support a review, never introduce a new
    # automatic claim. It does not add independent pixels or calibrated proof.
    if ocr.collector_retry_contributed and status == 'matched':
        status = 'uncertain'
    if ocr.collector_retry_skipped and status == 'matched':
        status = 'uncertain'
    # A foreground/min-area rectangle is only a retrieval proposal. Even a
    # strong global match on it stays reviewable, never an automatic printing.
    if inferred_frame and status == 'matched':
        status = 'uncertain'
    if combined and combined[0].get('retrieved_via') == ['ocr_metadata'] and status == 'matched':
        status = 'uncertain'
    if combined and combined[0].get('retrieved_via') == ['ocr_title']:
        # Name-only fallback must pass geometry, never automatically confirm.
        if combined[0].get('local_artwork_verified'):
            status = 'uncertain'
        else:
            status = 'retake'
            retake = True
    if combined and 'ocr_geometry' in combined[0].get('retrieved_via',[]):
        # Weak/missing-language OCR proposes pixels only. It must never escape
        # local artwork verification or become an automatic printing claim.
        if combined[0].get('local_artwork_verified'):
            status='uncertain'
        else:
            status='retake'
            retake=True
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
    stamp_hint = None
    if likely_identity_supported and not framing_review_supported and not printing.ambiguous and not retake:
        # Even a single retrieved printing isn't proof that no reprints exist.
        # Require explicit selection using the existing review/feedback contract.
        printing = PrintingDecision(True, reason='likely_identity_printing_unverified',
            members=(combined[0],), candidate_group_id='likely:' + combined[0]['card_id'],
            reference_coverage_complete=False,
            guidance='Likely card identified. Confirm the exact set, collector number and finish, or retake with the full card visible.')
    if printing.ambiguous:
        status = "printing_ambiguous"
        # Geometry verifies shared artwork, not the winning reprint. Once
        # siblings are explicitly retained as ambiguous, use their existing
        # OCR/global scores for display order rather than keypoint survival.
        if local_matches and not .62<=ratio<=.80 and not any(h.region=='collector' and h.confidence is not None
                and h.confidence>=.85 and ('/' in h.text or any(c.isalpha() for c in h.text)) for h in numbers):
            sibling_ids={r['card_id'] for r in printing.members}
            eligible=[r for r in combined if r['card_id'] in sibling_ids
                and artwork_evidence_compatible(r,ocr_name=ocr.name_text,
                    name_confidence=name_confidence,numbers=numbers,languages=rank_languages)]
            if eligible:
                preferred=max(eligible,key=lambda r:float(r['combined_score']))
                combined.sort(key=lambda r:r['card_id']==preferred['card_id'],reverse=True)
                reference_identity=dict(combined[0])
        try:
            stamp_hint = stamp_printing_hint(combined, printing.members, image,
                ocr_name=ocr.name_text, name_confidence=name_confidence,
                numbers=numbers, languages=rank_languages)
            if stamp_hint:
                combined.sort(key=lambda r:r['card_id']==stamp_hint['preferred_card_id'],reverse=True)
                reference_identity = dict(combined[0])
        except (OSError, ValueError, KeyError, cv2.error):
            logging.getLogger(__name__).exception('Optional stamp ordering failed')
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
                "cardmarket_prices": row.get("cardmarket_prices") or snapshot_prices(
                    catalog, row.get("cardmarket_url")
                ),
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
    for record in ocr_passes:
        logging.getLogger('scan.diagnostics').info('card_ocr_pass scan_id=%s scope=%s region=%s reason=%s width=%s height=%s elapsed_ms=%s',
            scan_id, record['scope'], record['region'], record['reason'], record['width'], record['height'], record['ms'])
    versions = runtime.versions()
    versions['presentation'] = 'best-match-v1'
    versions['stamp_ordering'] = 'play-stamp-review-v1'
    versions['ocr_cache'] = 'request-pixels-v1'
    if adaptive_footer:
        versions['ocr_budget'] = OCR_BUDGET_VERSION
    presentation = match_presentation(combined, status=status, printing_review=printing_review,
                                      min_visual=settings.threshold_min_visual_ocr)
    confidence = confidence_payload(combined, status=status,
        name_confidence=name_confidence, numbers=numbers,
        framing_unverified=framing_unverified, quality_retake=too_small or too_blurry,
        min_visual=settings.threshold_min_visual,
        structured_identity=bool(reference_identity and structured_identity_agrees(reference_identity,
            ocr_name=ocr.name_text, name_confidence=name_confidence, numbers=numbers, languages=rank_languages)),
        likely_identity=likely_identity_supported)
    if stamp_hint:
        confidence.reasons.append('stamp_display_hint_printing_unconfirmed')
    if ocr.collector_retry_skipped:
        confidence.reasons.append('optional_footer_retry_skipped_printing_unconfirmed')
    ocr_payload = {
        "name_text": ocr.name_text,
        "collector_text": ocr.collector_text,
        "lines": ocr.lines,
        "failed": ocr.failed,
        "collector_retry_used": ocr.collector_retry_used,
        "collector_retry_contributed": ocr.collector_retry_contributed,
        "collector_retry_skipped": ocr.collector_retry_skipped,
        "passes": ocr_passes,
        "ocr_cache_hits": ocr_cache_hits,
        "stamp_printing_hint": stamp_hint,
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
        "geometry_candidate_ids": geometry_ids,
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
            collector_retry_skipped=ocr.collector_retry_skipped,
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
                           tuple(rank_languages), name_confidence, too_small or too_blurry, ocr_payload,
                           combined, shown)


@parallel_grading_scope
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
    _grading_job: GradingJob | None = None,
) -> ScanResponse:
    """Evaluate first, then persist exactly one result and optional capture.

    A failed framing decision may try ONE line-supported frame. Existing useful
    results are never replaced. Recovery uses the same identity/quality guards,
    stays review-only, and cannot discard strong first-pass contradictions.
    Explicit crops and quality retakes do not trigger this extra OCR pass.
    """
    started = time.perf_counter()
    ocr_cache = RequestOcrCache()
    kwargs = dict(settings=settings, runtime=runtime, catalog=catalog,
                  results=results, session_id=session_id, crop_x=crop_x,
                  crop_y=crop_y, crop_w=crop_w, crop_h=crop_h, rotation=rotation,
                  skip_detect=skip_detect, language=language, store_capture=store_capture)
    kwargs['_ocr_cache'] = ocr_cache
    if _grading_job is not None:
        kwargs['_input_observer'] = _grading_job.start
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
        # Slab edges can outrank the inner card geometrically. Eight line
        # probes plus one artwork-aligned proposal still lead to at most ONE
        # additional OCR evaluation.
        frames = line_frame_candidates(first.input_image,limit=8)
        profiles=[f'line_{i}' for i in range(len(frames))]
        verifier=getattr(runtime,'artwork_verifier',None)
        if first.lead and hasattr(verifier,'propose_frame'):
            row=catalog.execute('SELECT image_path FROM cards WHERE id=?',(first.lead['card_id'],)).fetchone()
            if row and row['image_path']:
                aligned=verifier.propose_frame(first.input_image,(first.lead['card_id'],str(row['image_path'])))
                if aligned is not None:
                    frames=[*frames,aligned]
                    profiles=[*profiles,'aligned_reference']
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
                # Compare retrieval hypotheses by their maximum score. A
                # confidence gap belongs to final printing decisions, not
                # between crops: first-proposal order must not lock in a
                # lower-scoring holder crop and hide a better card interior.
                if score >= settings.threshold_min_visual_ocr and (best is None or score > best[0]):
                    best = (score,i,frame)
            embed_ms = (time.perf_counter()-mark)*1000
            if best is not None:
                attempted = True
                recovery.update(proposal_profile=profiles[best[1]],proposal_score=best[0])
                retry = _recognize_bytes_once(data, **kwargs,
                    _frame_override=(profiles[best[1]],best[2]))
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
    # Holder labels belong to this photographed copy, not the catalogue card.
    # Read only once, after frame recovery, on the original request frame
    # (respecting any explicit user crop/rotation), before saving that result.
    # Numeric grading stays separate from card identity. A separate literal
    # holder read may only order existing ambiguous choices with independently
    # supported artwork or printed name + collector evidence.
    mark = time.perf_counter()
    deadline = getattr(settings, 'grading_at_card_deadline', False)
    grading = (GradingEvidence(is_graded=False, grading_status='ungraded') if deadline
               else GradingEvidence(warnings=['grading_detection_disabled']))
    grading_ready = bool(_grading_job is not None and _grading_job.future is not None
                         and _grading_job.future.done())
    if getattr(settings, 'use_grading', True) and getattr(settings, 'use_ocr', True):
        _, _, label_engine = runtime.require()
        if deadline:
            if grading_ready:
                try:
                    observed = _grading_job.result()
                    if observed.company is not None:
                        grading = observed
                except Exception:  # noqa: BLE001 - return Raw for manual confirmation
                    logging.getLogger(__name__).exception('Optional grading failed for scan %s', selected.response.id)
            elif _grading_job is not None:
                _grading_job.stop()
        elif (_grading_job is not None and _grading_job.future is not None
                or label_engine is not None and hasattr(label_engine, 'read_grading')):
            try:
                grading = (_grading_job.result() if _grading_job is not None
                           and _grading_job.future is not None
                           else label_engine.read_grading(first.input_image))
            except Exception:  # noqa: BLE001 - preserve otherwise successful scans
                logging.getLogger(__name__).exception('Grading OCR failed for scan %s', selected.response.id)
                grading = GradingEvidence(warnings=['grading_ocr_failed'])
        else:
            grading = GradingEvidence(warnings=['grading_ocr_unavailable'])
    selected.response.grading = grading
    selected.evidence['grading'] = grading.model_dump(mode='json')
    selected.evidence['grading_version'] = GRADING_VERSION
    if hasattr(selected.response, 'versions'):
        selected.response.versions['grading'] = GRADING_VERSION
    grading_wait_ms = (time.perf_counter() - mark) * 1000
    if _grading_job is not None and _grading_job.future is not None:
        selected.timings['grading_ms'] = (_grading_job.elapsed_ms if _grading_job.future.done()
            else (time.perf_counter()-_grading_job.started_at)*1000)
        selected.timings['grading_wait_ms'] = grading_wait_ms
        selected.timings['grading_parallel'] = 1.
    else:
        selected.timings['grading_ms'] = grading_wait_ms
    if deadline:
        selected.timings['grading_ready_at_card_deadline'] = float(grading_ready)
    mark = time.perf_counter()
    if (selected.response.status == ScanStatus.printing_ambiguous
            and grading.slab_detected and grading.company
            and (selected.evidence.get('local_artwork_matches')
                 or selected.evidence.get('framing_review_supported'))
            and selected.ranked and selected.response.printing_review
            and hasattr(label_engine, 'read_holder_identity')):
        try:
            lines = label_engine.read_holder_identity(first.input_image)
            family_ids = {r.card_id for r in selected.response.printing_review.plausible_printings}
            eligible = [r for r in selected.ranked if r['card_id'] in family_ids
                        and artwork_evidence_compatible(r, ocr_name=selected.ocr.name_text,
                            name_confidence=selected.name_confidence, numbers=selected.numbers,
                            languages=selected.languages)]
            preferred = holder_printing_hint(eligible, lines,
                printed_name=selected.ocr.name_text, printed_name_confidence=selected.name_confidence,
                printed_numbers=selected.numbers, language=selected.response.detected_language)
            selected.evidence['holder_printing_hint'] = {
                'preferred_card_id': preferred, 'policy': 'display order only; printing remains ambiguous',
                'lines': [dict(text=l.text, confidence=l.confidence, box=l.box) for l in lines],
            }
            if preferred and preferred != selected.ranked[0]['card_id']:
                selected.ranked.sort(key=lambda r: r['card_id'] == preferred, reverse=True)
                selected.lead = dict(selected.ranked[0])
                selected.shown[:] = selected.ranked[:1]
                selected.response.suggestions = [Candidate.model_validate(r) for r in selected.shown]
                presentation = match_presentation(selected.ranked, status='printing_ambiguous',
                    printing_review=selected.response.printing_review,
                    min_visual=settings.threshold_min_visual_ocr)
                selected.response.best_match = presentation.best_match
                selected.response.alternatives = presentation.alternatives
                selected.response.match_state = presentation.match_state
                confidence = confidence_payload(selected.ranked, status='printing_ambiguous',
                    name_confidence=selected.name_confidence, numbers=selected.numbers,
                    framing_unverified=selected.evidence.get('framing_unverified', False),
                    quality_retake=selected.quality_retake, min_visual=settings.threshold_min_visual,
                    structured_identity=False, likely_identity=False)
                confidence.reasons.append('holder_label_printing_hint_review_only')
                selected.response.confidence = confidence
                selected.evidence['confidence'] = confidence.model_dump(mode='json')
                selected.evidence['match_presentation'] = presentation.model_dump(mode='json')
        except Exception:  # noqa: BLE001 - an optional hint must not erase the visual result
            logging.getLogger(__name__).exception('Holder printing hint failed for scan %s', selected.response.id)
    selected.timings['holder_hint_ms'] = (time.perf_counter() - mark) * 1000
    selected.timings.update(boundary_proposal_ms=proposal_ms,
                            boundary_selection_ms=embed_ms,
                            boundary_retry_attempted=float(attempted),
                            boundary_retry_selected=float(selected is not first),
                            total_ms=(time.perf_counter()-started)*1000)
    selected.timings['ocr_cache_hits'] = float(ocr_cache.hits)
    selected.timings['ocr_unique_reads'] = float(ocr_cache.reads)
    selected.response.timings_ms = {key:round(value,2) for key,value in selected.timings.items()}
    selected.evidence['boundary_recovery'] = {
        **recovery,
        'attempted': attempted, 'selected': selected is not first,
        'first_status': first.response.status.value,
        'first_top_id': first.lead.get('card_id') if first.lead else None,
        'policy': 'one review-only retry; preserve first-pass identity contradictions',
    }
    selected.evidence['ocr_request_summary'] = {
        'unique_reads': ocr_cache.reads, 'cache_hits': ocr_cache.hits,
        'first_pass_region_reads': first.evidence.get('passes', []),
        'selected_pass_region_reads': selected.evidence.get('passes', []) if selected is not first else [],
        'policy': 'identical request pixels only; pristine cloned observations, no cross-upload cache',
    }
    selected.save()
    return selected.response
