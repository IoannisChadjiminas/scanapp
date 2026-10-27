from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
import uuid
from copy import deepcopy
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
    url_for_row,
)
from app.price_sources import scan_finishes, scan_prices
from app.catalogue_titles import stored_view_title
from app.physical_cards import is_tcg_pocket_card
from app.set_totals import set_total
from app.db import coverage_payload
from app.recognition.captures import save_scan_capture
from app.recognition.client_text import (OCR_MODES as CLIENT_TEXT_OCR_MODES, VERSION as CLIENT_TEXT_VERSION,
                                         ClientText, client_text_line, fast_path_decision, ocr_skip_decision,
                                         phone_read, server_read_agrees, with_phone_number)
from app.recognition.detect import (card_frame_candidates, client_quad_rect, detect_and_rectify,
                                    quads_agree, server_frame_rect, warp_to_rect)
from app.recognition.frame_fallback import line_frame_candidates, loose_frame_candidates, portrait_window_candidates, slab_interior_candidate
from app.recognition.images import apply_crop, blur_variance, decode_image
from app.recognition.embed import top_k
from app.recognition.identity import layout_identity_agrees, likely_identity_agrees, structured_identity_agrees
from app.recognition.confidence import confidence_payload
from app.recognition.presentation import match_presentation
from app.recognition.language import (confident_language_texts, language_label, locale_languages,
                                         order_preview_ids, ranking_languages,
                                         resolve_search_languages)
from app.recognition.ocr import OcrHit, OcrResult, inverted_card_layout
from app.recognition.ocr_framing import complete_frame_probe_allowed, complete_frame_identity_supported, normalize_complete_frame_footer, wide_footer_allowed, wide_footer_fractions
from app.recognition.ocr_cache import RequestOcrCache
from app.recognition.ocr_budget import (footer_retry_required, title_only_allowed,
    title_only_confirmed, VERSION as OCR_BUDGET_VERSION)
from app.recognition.stamp_printing import stamp_printing_hint
from app.recognition.grading import VERSION as GRADING_VERSION
from app.recognition.grading_parallel import GradingJob, grading_requested, parallel_grading_scope
from app.recognition.holder_printing import holder_printing_hint
from app.recognition.orientation import retrieve_oriented
from app.recognition.printing import PrintingDecision, assess_printings
from app.recognition.rank import artwork_evidence_compatible, decide_status_with_reason, damaged_footer_named_printing, extract_collector_candidates, fraction_named_printing, rerank
from app.recognition.rank import name_match, normalize_text
from app.recognition.runtime import Runtime
from app.recognition.title_retry import read_conflicting_title, title_retry_allowed
from app.recognition.text_identity import (VERSION as TEXT_IDENTITY_VERSION, confident_fractions, name_agrees,
                                           name_tokens, read_whole_image, text_identity_candidates)
from app.recognition.label_identity import (VERSION as LABEL_IDENTITY_VERSION, label_identity_candidates,
                                            label_language, label_lines, read_label_half)
from app.schemas import (
    Candidate,
    GradingEvidence,
    OcrEvidence,
    PrintingReview,
    ScanResponse,
    ScanStatus,
)

# With SLAB_LABEL_IDENTITY, text candidates are also tried up to this far above the automatic
# visual floor when the visual leader agrees with no name read on the card or its label.
LEADER_CONFLICT_MARGIN = .07

# Scan lanes share one results connection; keep each scan's insert and commit together.
_results_write = threading.Lock()


def _scan_keep(runtime, requested) -> np.ndarray | None:
    """Language choice plus the physical-card mask. Pocket rows never match."""
    keep = None
    if requested.reason == "user" and requested.search and runtime.card_languages is not None:
        keep = np.isin(runtime.card_languages, list(requested.search))
    physical = getattr(runtime, "physical_cards", None)
    if physical is None:
        return keep
    return physical if keep is None else keep & physical


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _card_image_url(row: Any) -> str:
    return display_image_url(row) or f"/api/v1/cards/{row['id']}/image"


def prefer_unproven_visual_match(ranked: list[dict[str, Any]], members, *, min_gap: float = 0.04) -> None:
    """Show the closest image when a printing group is still unproven.

    A small visual gap stays with the current display order. A clear gap is
    the picture itself, so the closest image in the group replaces a
    combined-score leader that has no collector number and no stamp.
    """
    if len(ranked) < 2 or ranked[0].get("visual_score") is None:
        return
    member_ids = {row.get("card_id") for row in members}
    eligible = [row for row in ranked if row.get("card_id") in member_ids
                and row.get("visual_score") is not None]
    if len(eligible) < 2:
        return
    preferred = max(eligible, key=lambda row: float(row["visual_score"]))
    if preferred.get("card_id") == ranked[0].get("card_id"):
        return
    if float(preferred["visual_score"]) - float(ranked[0]["visual_score"]) < min_gap:
        return
    ranked.sort(key=lambda row: row.get("card_id") == preferred.get("card_id"), reverse=True)


def _printing_order(row: dict[str, Any]) -> tuple:
    def natural(value: Any) -> tuple:
        return tuple((0, int(part), '') if part.isdigit() else (1, 0, part)
                     for part in re.findall(r'\d+|\D+', str(value or '').lower()))
    card_id = str(row.get('card_id') or '')
    return (natural(row.get('set_id') or card_id.split(':')[-1].rsplit('-', 1)[0]),
            natural(row.get('collector_number')), card_id)


def settle_unproven_twins(ranked: list[dict[str, Any]], members, *, min_gap: float = 0.04) -> None:
    """Show the same printing every time when nothing separates the leaders.

    Printings that share artwork score within noise of each other, so which
    one led changed from photo to photo. Among group members within `min_gap`
    of the shown card on both the image and the combined score, and with the
    same OCR verdict, the first by set and collector number is shown. Order
    only; the printing stays unproven.
    """
    if len(ranked) < 2 or ranked[0].get('visual_score') is None:
        return
    shown = ranked[0]
    member_ids = {row.get('card_id') for row in members}
    if shown.get('card_id') not in member_ids:
        return

    def near(row: dict[str, Any], key: str) -> bool:
        return (row.get(key) is not None and shown.get(key) is not None
                and abs(float(row[key]) - float(shown[key])) < min_gap)

    twins = [row for row in ranked if row.get('card_id') in member_ids
             and row.get('name') == shown.get('name')
             and (row.get('language') or '') == (shown.get('language') or '')
             and near(row, 'visual_score') and near(row, 'combined_score')
             and all(row.get(flag) == shown.get(flag) for flag in
                     ('ocr_consistent', 'collector_conflict', 'structured_collector_conflict'))]
    if len(twins) < 2:
        return
    preferred = min(twins, key=_printing_order)
    if preferred.get('card_id') != shown.get('card_id'):
        ranked.sort(key=lambda row: row.get('card_id') == preferred.get('card_id'), reverse=True)


def _lookup_cards(conn: sqlite3.Connection, card_ids: list[str]) -> dict[str, sqlite3.Row]:
    if not card_ids:
        return {}
    placeholders = ",".join("?" for _ in card_ids)
    rows = conn.execute(
        f"SELECT * FROM cards WHERE id IN ({placeholders})",
        card_ids,
    ).fetchall()
    return {row["id"]: row for row in rows}


def _supports_first_edition(row: sqlite3.Row | dict) -> bool:
    """Read TCGdex's firstEdition capability flag from the stored variants."""
    raw = row.get("variants_json") if isinstance(row, dict) else row["variants_json"]
    try:
        variants = json.loads(raw or "{}") if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return False
    return isinstance(variants, dict) and variants.get("firstEdition") is True


def _preview_candidates(conn: sqlite3.Connection, card_ids: list[str]) -> list[dict]:
    """Early guesses for the phone: set, number and a stored price let the tile
    fill at once. Everything is read from local tables, never from the network."""
    rows = _lookup_cards(conn, card_ids)
    return [dict(card_id=cid, name=rows[cid]['name'],
                 view_title=stored_view_title(rows[cid]),
                 image_url=_card_image_url(rows[cid]),
                 set_name=rows[cid]['set_name'],
                 collector_number=rows[cid]['collector_number'],
                 set_total=set_total(conn, rows[cid]['language'], rows[cid]['set_id']),
                 language=str(rows[cid]['language'] or ''),
                 cardmarket_url=rows[cid]['cardmarket_url'],
                 supports_first_edition=_supports_first_edition(rows[cid]),
                 cardmarket_prices=scan_prices(conn, cid, rows[cid]['cardmarket_url']),
                 **scan_finishes(conn, cid))
            for cid in card_ids if cid in rows]


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
    query_image: Any = None
    # 'verified' (one locally verified number+name candidate), 'unverified', or None.
    text_identity: str | None = None


def _detect_with_client_quad(image, fractions) -> tuple[Any, bool, str]:
    """The server's own detection decides; the phone's corners fill in when it finds nothing.

    A disagreement keeps today's behaviour. A phone quad is only used alone when it
    also passes the detector's card-shape rules, and visual retrieval still compares
    it against the alternative frames afterwards.
    """
    server = server_frame_rect(image)
    client = client_quad_rect(image, fractions)
    if client is None:
        note = 'client_quad_rejected'
    elif server is None:
        return warp_to_rect(image, client), True, 'client_quad_only'
    else:
        note = 'client_quad_agrees' if quads_agree(server, client) else 'client_quad_disagrees'
    if server is None:
        return image, False, note
    return warp_to_rect(image, server), True, note


def _text_named_card(runtime, catalog, client_text, settings) -> str | None:
    """The one catalogue card the phone's own name and number name, with set totals applied.

    Used only to order a printing_ambiguous result. It never confirms a printing.
    """
    name = getattr(client_text, 'name', None)
    number = getattr(client_text, 'number', None)
    if not name or not number:
        return None
    from app.recognition.stage1_gate import GateOptions, collapse_hits, load_catalogue, lookup, set_total_conflicts
    options = GateOptions(set_totals=True, normalize_duplicates=True, promo_numbers=True)
    cached = getattr(runtime, 'printing_text_catalogue', None)
    if cached is None:
        cached = load_catalogue(catalog, options)
        runtime.printing_text_catalogue = cached
    by_key, _by_id, bare_ids = cached
    hits = [row for row in collapse_hits(lookup(by_key, name, number, None, options), bare_ids)
            if not set_total_conflicts(number, row, options)]
    return str(hits[0]['id']) if len(hits) == 1 else None


def _recognize_bytes_once(
    data: bytes,
    *,
    phone_inputs: dict | None = None,
    settings: Settings,
    runtime: Runtime,
    catalog: sqlite3.Connection,
    results: sqlite3.Connection | None,
    session_id: str,
    crop_x: float | None = None,
    crop_y: float | None = None,
    crop_w: float | None = None,
    crop_h: float | None = None,
    rotation: int = 0,
    skip_detect: bool = False,
    language: str = "auto",
    store_capture: bool | None = None,
    locale: str | None = None,
    card_quad: list[tuple[float, float]] | None = None,
    _frame_override: tuple[str, Any] | None = None,
    _frame_detected_override: bool = False,
    _input_observer: Callable | None = None,
    _progress_observer: Callable | None = None,
    _ocr_cache: RequestOcrCache | None = None,
    _title_retry_ocr: OcrResult | None = None,
    client_text: ClientText | None = None,
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
    quad_notes: list[str] = []
    if _frame_override is not None:
        image = _frame_override[1]
        detected = _frame_detected_override
    elif not skip_detect:
        if (card_quad and settings.use_client_quad and rotation == 0
                and all(v is None for v in (crop_x, crop_y, crop_w, crop_h))):
            image, detected, quad_note = _detect_with_client_quad(image, card_quad)
            quad_notes.append(quad_note)
        else:
            image, detected = detect_and_rectify(image)
    timings["detect_ms"] = (time.perf_counter() - mark) * 1000

    # Respect an explicit language while selecting orientation. Automatic
    # language detection follows OCR on the selected frame.
    requested = resolve_search_languages(language, [])
    keep = _scan_keep(runtime, requested)
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
        retrieval_segments=getattr(snapshot, "retrieval_segments", None),
    )
    if _frame_override is not None:
        frame_selection['profile'] = _frame_override[0]
    inferred_frame = frame_selection.get('profile','').startswith(('line_', 'loose_', 'window_', 'slab_', 'aligned_'))
    if frame_selection.get('profile') == 'as_supplied' or inferred_frame:
        detected = False
    timings.update(orientation_timings)
    blur = blur_variance(image, settings.threshold_blur_edge)
    too_small = min(image.size) < settings.threshold_min_side
    too_blurry = blur < settings.threshold_blur
    if too_blurry and image is not input_image:
        # A soft patch of card art or a mis-chosen frame must not condemn a
        # photo that is sharp as a whole.
        if blur_variance(input_image, settings.threshold_blur_edge) >= settings.threshold_blur:
            too_blurry = False
    retake = too_small or too_blurry
    if (_progress_observer is not None and not retake and len(scores)
            and float(scores[0]) >= settings.threshold_min_visual):
        # Weak visual neighbours must wait for the OCR-assisted rescue. A
        # preview is not a way to expose below-threshold guesses as a match.
        shortlist = [(str(snapshot.card_ids[i]), float(score)) for i, score in zip(indices, scores)
                     if float(score) >= settings.threshold_min_visual_ocr]
        preview_ids = [cid for cid, _ in shortlist]
        if settings.preview_language_order and shortlist:
            # Order only: near-tied printings show the reader's language first.
            rows = _lookup_cards(catalog, preview_ids)
            preference = ((tuple(requested.search) if requested.reason == 'user' else ())
                          + locale_languages(locale) + ('en',))
            preview_ids = order_preview_ids(
                preview_ids, [score for _, score in shortlist],
                {cid: str(row['language'] or '') for cid, row in rows.items()},
                preference, settings.threshold_min_gap)
        preview_ids = preview_ids[:3]
        previews = _preview_candidates(catalog, preview_ids)
        if previews:
            try:
                _progress_observer(dict(candidates=previews, provisional=True,
                    printing_confirmed=False, requires_confirmation=True,
                    elapsed_ms=round((time.perf_counter()-started)*1000, 2)))
            except Exception as error:
                # Optional UI progress cannot change recognition or its evidence.
                logging.getLogger('scan.diagnostics').warning(
                    'scan_preview_failed error_type=%s', type(error).__name__)
    artwork_hits = []
    artwork_index = getattr(runtime, "artwork_index", None)
    adaptive_footer = bool(getattr(settings, 'ocr_adaptive_footer', False))
    artwork_image = None
    full_candidates = []
    ocr_mode = getattr(settings, 'client_text_ocr', 'off')
    ocr_mode = ocr_mode if ocr_mode in CLIENT_TEXT_OCR_MODES else 'off'
    fast_path_wanted = bool(client_text is not None and _frame_override is None
                            and (getattr(settings, 'client_text_fast_path', False) or ocr_mode != 'off'))
    if (adaptive_footer or fast_path_wanted) and artwork_index is not None and not retake:
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
                                visual_score=float(score),
                                language=str(rows[str(snapshot.card_ids[i])]['language'] or ''))
            for i, score in zip(indices, scores) if str(snapshot.card_ids[i]) in rows]
    title_only = False
    printing_index = getattr(runtime, 'printing_index', None)
    title_only_enabled = bool(getattr(settings, 'ocr_title_only_single_printing', False))
    if adaptive_footer and full_candidates and printing_index is not None and title_only_enabled:
        # Same-art reprints are the only reason to read the collector number
        # for identity. A lone, complete printing with strong agreeing visual
        # evidence reads its title only; any doubt reads the footer as before.
        lead = dict(rows[full_candidates[0]['card_id']])
        lead['card_id'] = full_candidates[0]['card_id']
        lead_family, lead_incomplete = printing_index.family(catalog, lead)
        title_only = title_only_allowed(full_candidates, artwork_hits, lead_family,
            family_incomplete=lead_incomplete, image_size=image.size)
    if title_only_enabled:
        frame_selection['ocr_title_only'] = 'skipped_footer' if title_only else 'not_eligible'
    fast_path = False
    client_text_skipped = []
    phone_ocr = None  # 'footer' or 'all' once the phone's read may stand in for server OCR
    lead = None
    if fast_path_wanted:
        # The phone's text may only confirm the server's own pixel answer; then
        # the optional OCR re-reads are left out. It never ranks or selects.
        if full_candidates:
            lead = dict(rows[full_candidates[0]['card_id']])
            lead['card_id'] = full_candidates[0]['card_id']
            lead['set_total'] = set_total(catalog, lead['language'], lead['set_id'])
        min_confidence = float(getattr(settings, 'client_text_min_confidence', .9))
        if getattr(settings, 'client_text_fast_path', False):
            try:
                fast_path, fast_reason = fast_path_decision(client_text, full_candidates, lead, artwork_hits,
                    catalog, image_size=image.size, min_confidence=min_confidence)
            except Exception:  # noqa: BLE001 - an optional hint keeps the full path
                logging.getLogger(__name__).exception('Client text decision failed')
                fast_path, fast_reason = False, 'error'
            frame_selection['client_text_fast_path'] = fast_reason
        if ocr_mode != 'off':
            def lead_for(card_id):
                if card_id not in rows:
                    return None
                row = dict(rows[card_id])
                row['card_id'] = card_id
                row['set_total'] = set_total(catalog, row['language'], row['set_id'])
                return row
            try:
                allowed, _, ocr_reason = ocr_skip_decision(client_text, full_candidates, lead_for, catalog,
                    mode=ocr_mode, image_size=image.size, min_confidence=min_confidence,
                    min_visual=settings.threshold_min_visual, min_gap=settings.threshold_min_gap)
            except Exception:  # noqa: BLE001 - an optional hint keeps the full path
                logging.getLogger(__name__).exception('Client text OCR decision failed')
                allowed, ocr_reason = False, 'error'
            frame_selection['client_text_ocr'] = ocr_reason
            phone_ocr = ocr_mode if allowed else None
    ocr = OcrResult(failed=True)
    ocr_passes = []
    ocr_cache_hits = []
    title_retry_used = []
    def read_card(frame, scope):
        if (_title_retry_ocr is not None and _frame_override is not None
                and frame is _frame_override[1]):
            title_retry_used.append(scope)
            return deepcopy(_title_retry_ocr)
        options = {}
        if phone_ocr == 'all' and scope == 'selected' and frame is artwork_image:
            return phone_read(client_text)
        if phone_ocr == 'footer' and scope == 'selected' and frame is artwork_image:
            # The server reads the title itself; the phone's number completes it
            # only when that title confidently agrees with the phone.
            observed = read_card_with(frame, scope, read_footer=False)
            if server_read_agrees(client_text, observed, require_title=True):
                return with_phone_number(observed, client_text)
            frame_selection['client_text_ocr'] = 'title_disagrees'
        if adaptive_footer and scope == 'selected' and frame is artwork_image:
            if title_only:
                observed = read_card_with(frame, scope, read_footer=False)
                if title_only_confirmed(observed, full_candidates[0]['name']):
                    return observed
                # The title disagrees or is weak: gather complete evidence.
                frame_selection['ocr_title_only'] = 'footer_fallback'
            options['collector_retry_policy'] = lambda observed: footer_retry_required(
                observed, full_candidates, artwork_hits, image_size=frame.size)
        if fast_path and scope == 'selected' and frame is artwork_image:
            options['optional_retry_gate'] = lambda observed: server_read_agrees(
                client_text, observed, require_title=fast_reason == 'eligible_title_required')
        return read_card_with(frame, scope, **options)
    def read_card_with(frame, scope, **options):
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
        if (getattr(settings, 'ocr_complete_frame_first', False) and phone_ocr != 'all'
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
                indices,scores=top_k(snapshot.embeddings,query_vectors[id(image)],k=20,keep=keep,segments=getattr(snapshot, 'retrieval_segments', None))
                timings['orientation_degrees']=(timings.get('orientation_degrees',0.)+180.)%360.
        # A retrieval window can cut away the footer even when it exists in
        # the uploaded image. Consult the uncropped input once, only for an
        # agreeing title plus explicit, confidence-qualified identifiers.
        # Supplement, never replace, first-pass evidence; later contradictions
        # remain visible to the normal ranking/printing safety rules.
        if (fast_path and inferred_frame and not ocr.failed and not original_identity_used
                and ocr.client_text_gate and server_read_agrees(
                    client_text, ocr, require_title=fast_reason == 'eligible_title_required')):
            client_text_skipped.append('original')
        elif inferred_frame and not ocr.failed and not original_identity_used:
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
                    if not extra and wide_footer_allowed(input_image):
                        # The card does not fill the upload, so its number is
                        # above the footer strip that was just read.
                        try:
                            extra, wide_pass = wide_footer_fractions(
                                ocr_engine, input_image, ocr.name_text,
                                _lookup_cards(catalog, [str(snapshot.card_ids[i]) for i in indices]).values())
                            if wide_pass:
                                ocr_passes.append(dict(scope='original', **wide_pass))
                        except Exception:  # noqa: BLE001 - keep the evidence already read
                            logging.getLogger(__name__).exception('Optional wide footer read failed')
                            extra = []
                    if extra:
                        ocr.hits.extend(extra)
                        ocr.lines.extend(h.text for h in extra)
                        ocr.collector_retry_used = True
                        ocr.collector_retry_contributed = True
    timings["ocr_ms"] = (time.perf_counter() - mark) * 1000
    timings['ocr_passes_count'] = float(len(ocr_passes))
    timings['ocr_footer_retry_skipped'] = float(ocr.collector_retry_skipped)
    timings['ocr_footer_skipped'] = float(ocr.footer_skipped)
    if fast_path_wanted:
        frame_selection['client_text_gate'] = ocr.client_text_gate
        frame_selection['client_text_skipped_reads'] = client_text_skipped
        timings['client_text_fast_path'] = float(bool(ocr.client_text_gate or client_text_skipped))
        timings['client_text_ocr'] = float(ocr.client_text_used is not None)
    if artwork_index is not None and not retake and image is not artwork_image:
        artwork_hits, artwork_timings = artwork_index.search(
            image, embedder, mode=settings.preprocess_config,
            as_supplied_vector=query_vectors[id(image)],
            languages=tuple(requested.search) if requested.reason == "user" else (),
        )
        timings.update(artwork_timings)
    query_image = image

    language_texts = confident_language_texts(ocr.hits)
    decision = resolve_search_languages(language, language_texts)
    numbers = extract_collector_candidates(
        [line for line in [ocr.collector_text, *ocr.lines] if line], hits=ocr.hits)
    leader_id = str(snapshot.card_ids[indices[0]]) if len(indices) else None
    leader = _lookup_cards(catalog, [leader_id]).get(leader_id) if leader_id else None
    rank_languages = ranking_languages(decision, language_texts,
                                       str(leader['language'] or '') if leader is not None else None)
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
    text_ids: list[str] = []
    text_reason = None
    label_ids: list[str] = []
    label_reason = None
    text_conflict = False
    full_fallback = None
    recovery = bool(getattr(settings, 'slab_text_recovery', False))
    slab_label = bool(getattr(settings, 'slab_label_identity', False))
    top_visual = float(scores[0]) if len(scores) else 0.
    if (getattr(settings, 'text_identity_candidates', False) and metadata_index is not None
            and not retake and not ocr.failed
            and (top_visual < settings.threshold_min_visual
                 or (slab_label and top_visual < settings.threshold_min_visual + LEADER_CONFLICT_MARGIN))):
        mark = time.perf_counter()
        try:
            text_ids, text_reason = text_identity_candidates(metadata_index, catalog,
                hits=ocr.hits, numbers=numbers, languages=rank_languages, numerator_fallback=recovery)
            if slab_label:
                label_ids, label_reason = label_identity_candidates(metadata_index, catalog,
                    hits=ocr.hits, languages=rank_languages, recovery=recovery)
                if (label_reason == 'no_label_number' and not text_ids
                        and callable(getattr(ocr_engine, '_run', None))):
                    # The title strip caught only the label's header. One read of the
                    # upload's upper half for the label's set line and number.
                    label_hits, label_pass = read_label_half(ocr_engine, input_image)
                    ocr_passes.append(dict(scope='slab_label', **label_pass))
                    label_ids, label_reason = label_identity_candidates(metadata_index, catalog,
                        hits=[*ocr.hits, *label_hits], languages=rank_languages, recovery=recovery)
                text_ids = (list(dict.fromkeys([*label_ids, *text_ids])) if recovery
                            else sorted({*text_ids, *label_ids}))
                if recovery:
                    # A label that names the card's language ("2023 POKÉMON JP") decides it,
                    # even when the label's card name is Latin ("LUGIA EX").
                    label_language_code = label_language(label_lines(ocr.hits, recovery), recovery)
                    if label_language_code:
                        rows = _lookup_cards(catalog, text_ids)
                        in_language = [c for c in text_ids if c in rows
                                       and str(rows[c]['language'] or '') == label_language_code]
                        if in_language:
                            text_ids = in_language
                        rank_languages = (label_language_code,)
                        frame_selection['label_language'] = label_language_code
                if len(text_ids) > 3:
                    text_ids, text_reason = [], 'too_many_candidates'
            whole_frame = image.width * image.height >= .85 * input_image.width * input_image.height
            if (getattr(settings, 'full_image_text_fallback', False) and not text_ids
                    and not detected and whole_frame
                    and not confident_fractions(numbers) and callable(getattr(ocr_engine, '_run', None))):
                # No card frame was found and the strips read no printed number: on a
                # screenshot they hold the phone's status and browser bars. One read of
                # the whole upload feeds the same number+name and label paths.
                full_hits, full_pass = read_whole_image(ocr_engine, input_image)
                ocr_passes.append(dict(scope='full_image_text', **full_pass))
                full_fallback = dict(lines=len(full_hits), ms=full_pass['ms'])
                full_numbers = extract_collector_candidates([], hits=full_hits)
                full_texts = confident_language_texts([*ocr.hits, *full_hits])
                full_languages = ranking_languages(resolve_search_languages(language, full_texts),
                                                   full_texts, None)
                found, found_reason = text_identity_candidates(metadata_index, catalog,
                    hits=full_hits, numbers=full_numbers, languages=full_languages, any_fraction=True,
                    numerator_fallback=recovery)
                if slab_label and not found:
                    label_hits = [OcrHit(h.text, h.confidence, 'name') for h in full_hits]
                    found, found_reason = label_identity_candidates(metadata_index, catalog,
                        hits=label_hits, languages=full_languages, recovery=recovery)
                full_fallback.update(candidate_ids=found, reason=found_reason)
                if found:
                    # The whole-image read becomes evidence for this scan: its language
                    # decides ranking, its lines join the OCR record (region 'full_image',
                    # never a footer collector or a title).
                    text_ids, text_reason = found, f'full_image:{found_reason}'
                    ocr.hits.extend(OcrHit(h.text, h.confidence, 'full_image') for h in full_hits)
                    ocr.lines.extend(h.text for h in full_hits)
                    language_texts = full_texts
                    decision = resolve_search_languages(language, language_texts)
                    rank_languages = full_languages
                    numbers = extract_collector_candidates(
                        [line for line in [ocr.collector_text, *ocr.lines] if line], hits=ocr.hits)
        except Exception:  # noqa: BLE001 - optional candidates keep the established path
            logging.getLogger(__name__).exception('Text identity candidates failed')
            text_ids, text_reason = [], 'error'
        if text_ids and top_visual >= settings.threshold_min_visual:
            # Only below the automatic visual floor, unless the visual leader agrees with
            # neither the card's printed name nor the label: text never overrides a
            # picture that the card's own text supports.
            leader = _lookup_cards(catalog, [str(snapshot.card_ids[indices[0]])]).get(
                str(snapshot.card_ids[indices[0]]))
            tokens = name_tokens(ocr.hits)
            text_conflict = bool(leader is not None and leader['id'] not in text_ids and tokens
                and not name_agrees(tokens, leader['name'], str(leader['view_title'] or '')))
            if not text_conflict:
                text_ids, text_reason = [], 'visual_leader_supported'
        elif text_ids and recovery and len(indices):
            # Below the floor too: a visual guess that no read name supports must not
            # outrank the label's own card when neither verifies.
            leader = _lookup_cards(catalog, [str(snapshot.card_ids[indices[0]])]).get(
                str(snapshot.card_ids[indices[0]]))
            tokens = name_tokens(ocr.hits)
            text_conflict = bool(leader is not None and leader['id'] not in text_ids and tokens
                and not name_agrees(tokens, leader['name'], str(leader['view_title'] or '')))
        timings['text_identity_ms'] = (time.perf_counter() - mark) * 1000
    visual: list[dict[str, Any]] = []
    selected_ids = [str(snapshot.card_ids[i]) for i in indices]
    full_ids = set(selected_ids)
    artwork_by_id = {h.card_id: h for h in artwork_hits}
    selected_ids.extend(h.card_id for h in artwork_hits if h.card_id not in full_ids)
    selected_ids.extend(cid for cid in metadata_ids if cid not in selected_ids)
    selected_ids.extend(cid for cid in title_ids if cid not in selected_ids)
    selected_ids.extend(cid for cid in geometry_ids if cid not in selected_ids)
    selected_ids.extend(cid for cid in text_ids if cid not in selected_ids)
    cards = _lookup_cards(catalog, selected_ids)
    full_scores = {str(snapshot.card_ids[i]): float(score)
                   for i, score in zip(indices, scores, strict=True)}
    positions = getattr(runtime, 'card_positions', None) or (
        {str(cid): i for i, cid in enumerate(snapshot.card_ids)} if artwork_hits or metadata_ids or title_ids or geometry_ids or text_ids else {})
    for card_id in selected_ids:
        score = full_scores.get(card_id)
        if score is None:
            position = positions.get(card_id)
            score = float(snapshot.embeddings[position] @ query_vectors[id(image)]) if position is not None else 0.
        row = cards.get(card_id)
        if row is None:
            continue
        if "set_id" in row.keys() and is_tcg_pocket_card(row["language"], row["set_id"]):
            continue
        visual.append(
            {
                "card_id": card_id,
                "name": row["name"],
                "view_title": stored_view_title(row),
                "set_id": row["set_id"],
                "set_name": row["set_name"],
                "collector_number": row["collector_number"],
                "set_total": set_total(catalog, row["language"], row["set_id"]),
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
                "supports_first_edition": _supports_first_edition(row),
                "retrieved_via": (["full_card"] if card_id in full_ids else []) +
                                 (["artwork"] if card_id in artwork_by_id else []) +
                                 (["ocr_metadata"] if card_id in metadata_ids else []) +
                                 (["ocr_title"] if card_id in title_ids else []) +
                                 (["ocr_geometry"] if card_id in geometry_ids else []) +
                                 (["ocr_text_identity"] if card_id in text_ids else []),
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
    text_aligned: list[str] = []
    framing_unverified = False
    verifier = getattr(runtime, "artwork_verifier", None)
    ratio = image.width / image.height
    if combined and not retake and verifier is not None and (
        float(combined[0]["visual_score"]) < settings.threshold_min_visual
        or bool(geometry_ids)
        or bool(text_ids)
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
        if text_ids:
            # Number+name candidates are checked first; the cap of eight still applies.
            text_only = [r for r in combined if r['card_id'] in text_ids]
            local_order = [*text_only, *(r for r in local_order if r['card_id'] not in text_ids)]
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
        if text_ids and hasattr(verifier, 'propose_frame') and not any(
                m.card_id in text_ids for m in local_matches):
            # The selected frame may be a whole screenshot or slab. Project each
            # number+name candidate's artwork onto the upload and verify it there.
            for card_id in text_ids:
                row = cards.get(card_id)
                if row is None or not row['image_path']:
                    continue
                reference = (card_id, str(row['image_path']))
                aligned = verifier.propose_frame(input_image, reference)
                found = verifier.verify(aligned, [reference]) if aligned is not None else []
                local_matches.extend(found)
                text_aligned.extend(m.card_id for m in found)
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
        item["cardmarket_prices"] = scan_prices(catalog, item["card_id"], item.get("cardmarket_url"))
        item.update(scan_finishes(catalog, item["card_id"]))
    timings["cardmarket_ms"] = (time.perf_counter() - mark) * 1000
    status, decided_by = decide_status_with_reason(
        combined,
        enable_matched=settings.enable_matched,
        min_visual=settings.threshold_min_visual,
        min_visual_ocr=settings.threshold_min_visual_ocr,
        min_gap=settings.threshold_min_gap,
        retake=retake,
    )
    # Which rules produced or lowered the status, in order. Logged and stored, never acted on.
    status_reasons = [f'rank:{decided_by}', *quad_notes]
    if framing_review_supported and status=='no_match':
        # Independently qualified printed name + explicit collector and the
        # existing OCR-assisted visual floor can support a review result even
        # when another visual neighbour prevented automatic acceptance.
        status='uncertain'
        status_reasons.append('framing_review_rescue')
    if local_matches:
        status = "uncertain"
        status_reasons.append('local_artwork_used')
    if any(h.region=='holder_name' for h in ocr.hits) and status=='matched':
        status='uncertain'
        status_reasons.append('holder_name')
    if any(h.region == 'holder_collector' for h in numbers) and status == 'matched':
        status = 'uncertain'
        status_reasons.append('holder_collector')
    if any(h.region == 'holder_collector' for h in numbers) and not local_matches and not framing_review_supported:
        status = 'retake'
        retake = True
        status_reasons.append('holder_collector_unverified')
    # Upscaled collector OCR can support a review, never introduce a new
    # automatic claim. It does not add independent pixels or calibrated proof.
    if ocr.collector_retry_contributed and status == 'matched':
        status = 'uncertain'
        status_reasons.append('footer_retry_contributed')
    if ocr.collector_retry_skipped and status == 'matched':
        status = 'uncertain'
        status_reasons.append('footer_retry_skipped')
    # A foreground/min-area rectangle is only a retrieval proposal. Even a
    # strong global match on it stays reviewable, never an automatic printing.
    if inferred_frame and status == 'matched':
        status = 'uncertain'
        status_reasons.append('inferred_frame')
    if combined and combined[0].get('retrieved_via') == ['ocr_metadata'] and status == 'matched':
        status = 'uncertain'
        status_reasons.append('metadata_only')
    if combined and combined[0].get('retrieved_via') == ['ocr_title']:
        # Name-only fallback must pass geometry, never automatically confirm.
        if combined[0].get('local_artwork_verified'):
            status = 'uncertain'
            status_reasons.append('title_only_verified')
        else:
            status = 'retake'
            retake = True
            status_reasons.append('title_only_unverified')
    if combined and 'ocr_geometry' in combined[0].get('retrieved_via',[]):
        # Weak/missing-language OCR proposes pixels only. It must never escape
        # local artwork verification or become an automatic printing claim.
        if combined[0].get('local_artwork_verified'):
            status='uncertain'
            status_reasons.append('geometry_verified')
        else:
            status='retake'
            retake=True
            status_reasons.append('geometry_unverified')
    if combined and decision.detected in {'ja','ko','zh','zh-cn','zh-tw'} and combined[0].get('language') not in rank_languages:
        status = 'retake'
        retake = True
        framing_unverified = True
        status_reasons.append('language_mismatch')
    if framing_unverified:
        if framing_review_supported or likely_identity_supported:
            status = 'uncertain'
            status_reasons.append('framing_unverified_review')
        else:
            status = "retake"
            retake = True
            status_reasons.append('framing_unverified')
    text_identity = None
    # A near-threshold leader that contradicts the card's text is no better than an abstention.
    conflicting_leader = bool(text_conflict and combined and combined[0]['card_id'] not in text_ids
        and not combined[0].get('local_artwork_verified') and status in {'uncertain', 'printing_ambiguous'})
    if text_ids and (status in {'retake', 'no_match'} or conflicting_leader) and not (too_small or too_blurry):
        # The scan would abstain, yet a confident printed number and a name read in
        # the photo leave at most three cards. Verified artwork makes it a review
        # result; without it the cards are suggestions that need confirmation.
        verified = [r for r in combined if r['card_id'] in text_ids and r.get('local_artwork_verified')]
        chosen = verified or sorted((r for r in combined if r['card_id'] in text_ids),
                                    key=lambda r: float(r['visual_score']), reverse=True)
        if chosen:
            chosen_ids = [r['card_id'] for r in chosen]
            combined.sort(key=lambda r: (r['card_id'] in chosen_ids,
                                         -chosen_ids.index(r['card_id']) if r['card_id'] in chosen_ids else 0),
                          reverse=True)
            reference_identity = dict(combined[0])
            text_identity = 'verified' if len(verified) == 1 else 'unverified'
            status, retake, framing_unverified = 'uncertain', False, False
            status_reasons.append(f'text_identity_{text_identity}')
    elif text_ids and combined and combined[0]['card_id'] in text_ids and combined[0].get('local_artwork_verified'):
        text_identity = 'verified'
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
        status_reasons.append(f'printing:{printing.reason}')
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
        named = fraction_named_printing(combined, printing.members, numbers)
        damaged_order = bool(getattr(settings, 'ocr_damaged_footer_order', False))
        if not named and damaged_order and not stamp_hint:
            named = damaged_footer_named_printing(combined, printing.members, ocr.hits)
        if not named and getattr(settings, 'ocr_printing_from_text', False) and not stamp_hint:
            text_card = _text_named_card(runtime, catalog, client_text, settings)
            if text_card and any(row.get('card_id') == text_card for row in combined):
                named = text_card
        if named:
            combined.sort(key=lambda row: row.get('card_id') == named, reverse=True)
            if combined:
                reference_identity = dict(combined[0])
        elif not stamp_hint and not printing.collector_evidence:
            prefer_unproven_visual_match(combined, printing.members,
                                          min_gap=settings.threshold_min_gap)
            settle_unproven_twins(combined, printing.members,
                                  min_gap=settings.threshold_min_gap)
            if combined:
                reference_identity = dict(combined[0])
        shown_printing = combined[0]["card_id"] if combined else None
        review_members = sorted(
            printing.members, key=lambda row: row.get("card_id") != shown_printing)
        printing_review = PrintingReview(
            reason=printing.reason, candidate_group_id=printing.candidate_group_id,
            reference_coverage_complete=printing.reference_coverage_complete,
            collector_evidence=list(printing.collector_evidence),
            plausible_printings=[{
                "card_id": row["card_id"], "name": row["name"],
                "view_title": row.get("view_title"),
                "set_name": row["set_name"], "collector_number": row["collector_number"],
                "set_total": row.get("set_total"),
                "language": str(row.get("language") or ""),
                "image_url": row.get("image_url") or _card_image_url(row),
                "cardmarket_url": row.get("cardmarket_url"),
                "supports_first_edition": _supports_first_edition(row),
                "cardmarket_prices": row.get("cardmarket_prices") or scan_prices(
                    catalog, row["card_id"], row.get("cardmarket_url")
                ),
                **({key: row[key] for key in ("finishes", "reverse_holo_prices")}
                   if "finishes" in row else scan_finishes(catalog, row["card_id"])),
            } for row in review_members],
            guidance=printing.guidance,
        )
    elif local_matches and not framing_review_supported and not (
        # A slab label's own number, with verified artwork, outranks a footer misread.
        recovery and combined[0]['card_id'] in label_ids and combined[0].get('local_artwork_verified')
    ) and not artwork_evidence_compatible(
        combined[0], ocr_name=ocr.name_text, name_confidence=name_confidence,
        numbers=numbers, languages=rank_languages
    ):
        status = "retake"
        retake = True
        framing_unverified = True
        status_reasons.append('local_artwork_incompatible')
    timings["printing_review_ms"] = (time.perf_counter() - mark) * 1000
    # Holo glare can defeat artwork descriptors while the printed title,
    # fraction and distributed card layout remain readable. Corroborate those
    # independently, only after normal recognition abstains. Never reinterpret
    # layout landmarks as artwork evidence or an automatic printing match.
    layout_matches = []
    layout_review_supported = False
    layout_footer_hits = []
    layout_verifier = getattr(runtime, 'layout_verifier', None)
    if (getattr(settings, 'structured_layout_recovery', False)
            and layout_verifier is not None and not (too_small or too_blurry)
            and status in {'retake', 'no_match'}):
        mark = time.perf_counter()
        # The compact footer read is confined to this abstained path. Its
        # literal fractions gate layout review only; they never re-enter
        # ordinary ranking or status, so existing results cannot change.
        recovery_numbers = numbers
        if (settings.use_ocr and hasattr(ocr_engine, 'read_compact_footer')
                and name_confidence >= .95 and image.width >= 450
                and .62 <= image.width / image.height <= .80
                and not any(h.region == 'collector' and h.confidence is not None
                            and h.confidence >= .90 and '/' in h.text for h in numbers)):
            try:
                compact_hits, compact_pass = ocr_engine.read_compact_footer(image)
                ocr_passes.append(dict(scope='layout_recovery', **compact_pass))
                layout_footer_hits = compact_hits
                if compact_hits:
                    recovery_numbers = extract_collector_candidates(
                        [line for line in [ocr.collector_text, *ocr.lines] if line],
                        hits=[*ocr.hits, *compact_hits])
            except Exception:  # noqa: BLE001 - optional recovery keeps the abstention
                logging.getLogger(__name__).exception('Optional compact footer read failed')
        eligible = [row for row in combined if layout_identity_agrees(row,
            ocr_name=ocr.name_text, name_confidence=name_confidence,
            numbers=recovery_numbers, languages=rank_languages)]
        identities = {(r['set_id'], r['collector_number'], r['language']) for r in eligible}
        if len(identities) == 1 and 0 < len(eligible) <= 4:
            references = [(row['card_id'], str(cards[row['card_id']]['image_path'] or ''))
                          for row in eligible]
            layout_matches = layout_verifier.verify(image, references)
            supported_ids = {m.card_id for m in layout_matches}
            if supported_ids:
                combined.sort(key=lambda row: row['card_id'] in supported_ids, reverse=True)
                reference_identity = dict(combined[0])
                layout_review_supported = True
                retake = False
                status = 'uncertain'
                status_reasons.append('printed_identity_layout_review')
        timings['layout_verify_ms'] = (time.perf_counter() - mark)*1000
    if (recovery and text_ids and not (too_small or too_blurry)
            and any(r['card_id'] in text_ids and r.get('local_artwork_verified') for r in combined)):
        # A number/label candidate whose artwork verified is never dropped for an empty
        # retake, and a same-name candidate in the label's language leads the one that
        # happened to verify (CLV-017 English, CLF-017 Japanese share the artwork).
        verified = [r for r in combined if r['card_id'] in text_ids and r.get('local_artwork_verified')]
        lead = verified[0]
        def same_name(r):
            return (r['card_id'] != lead['card_id'] and normalize_text(r.get('view_title') or r['name'])
                    == normalize_text(lead.get('view_title') or lead['name']))
        siblings = sorted((r for r in combined if r['card_id'] in text_ids and same_name(r)),
                          key=lambda r: text_ids.index(r['card_id']))
        # The language evidence decides first; otherwise the text order does (label
        # candidates, then the printed total closest to the read one).
        sibling = (next((r for r in siblings if r.get('language') in rank_languages), None)
                   if rank_languages and lead.get('language') not in rank_languages else
                   next((r for r in siblings if text_ids.index(r['card_id']) < text_ids.index(lead['card_id'])
                         and (not rank_languages or r.get('language') in rank_languages)), None))
        order = [*([sibling] if sibling else []), lead,
                 *(r for r in combined if r['card_id'] in text_ids and r not in (sibling, lead))]
        if sibling or status in {'retake', 'no_match'}:
            ids = [r['card_id'] for r in order]
            combined.sort(key=lambda r: ids.index(r['card_id']) if r['card_id'] in ids else len(ids))
            reference_identity = dict(combined[0])
            if status in {'retake', 'no_match'}:
                status, retake, framing_unverified = 'uncertain', False, False
                status_reasons.append('text_identity_verified_review')
            if sibling:
                status = 'uncertain'
                status_reasons.append('text_identity_language_sibling')
            # 'sibling': the shared artwork verified on another printing; show both, sibling
            # first. Verified pixels exist, so the boundary retry is not needed.
            text_identity = 'sibling' if sibling and not sibling.get('local_artwork_verified') else 'verified'
    shown = [] if status in {"no_match", "retake", "failed"} else combined[:1]
    if text_identity in {'unverified', 'sibling'} and status == 'uncertain':
        shown = [r for r in combined if r['card_id'] in text_ids][:3]
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
    elif text_identity == 'sibling' and status == 'uncertain':
        message = 'The label names this card and its language; the same artwork verified on another printing. Pick the right printing before confirming.'
    elif text_identity == 'unverified' and status == 'uncertain':
        message = 'The printed collector number and a name in the photo point to these cards. The artwork was not verified; pick the right one or retake with the whole card visible.'
    elif text_identity == 'verified' and status == 'uncertain':
        message = 'The printed collector number, a name in the photo and the artwork agree. Check the exact printing and finish before confirming.'
    elif layout_review_supported:
        message = 'The printed name, collector number and card layout agree. Artwork similarity is weak; check the card, exact printing and finish before confirming.'
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
    versions['unproven_printing_order'] = (
        'visual-leader-v1+damaged-footer' if getattr(settings, 'ocr_damaged_footer_order', False)
        else 'visual-leader-v1')
    versions['ocr_cache'] = 'request-pixels-v1'
    if adaptive_footer:
        versions['ocr_budget'] = OCR_BUDGET_VERSION
    if fast_path_wanted:
        versions['client_text'] = CLIENT_TEXT_VERSION
    if getattr(settings, 'text_identity_candidates', False):
        versions['text_identity'] = TEXT_IDENTITY_VERSION
        if slab_label:
            versions['label_identity'] = LABEL_IDENTITY_VERSION
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
    if ocr.client_text_used:
        confidence.reasons.append(f'phone_text_used_{ocr.client_text_used}')
    if ocr.footer_skipped:
        confidence.reasons.append('footer_ocr_skipped_single_printing')
    if layout_review_supported:
        confidence.reasons.append('printed_identity_and_layout_agree_review_only')
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
        **({"title_retry_observations_used": bool(title_retry_used)}
           if _title_retry_ocr is not None else {}),
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
        "layout_matches": [vars(m) for m in layout_matches],
        "layout_review_supported": layout_review_supported,
        "layout_footer_hits": [vars(h) for h in layout_footer_hits],
        "artwork_retrieval": [vars(h) for h in artwork_hits],
        "metadata_candidate_ids": metadata_ids,
        "geometry_candidate_ids": geometry_ids,
        **({"text_identity": dict(candidate_ids=text_ids, reason=text_reason, outcome=text_identity,
                                  aligned_verified=text_aligned,
                                  **(dict(label_ids=label_ids, label_reason=label_reason,
                                          leader_conflict=text_conflict) if slab_label else {}),
                                  **(dict(full_image=full_fallback)
                                     if getattr(settings, 'full_image_text_fallback', False) else {}))}
           if getattr(settings, 'text_identity_candidates', False) else {}),
        "framing_unverified": framing_unverified,
        "framing_review_supported": framing_review_supported,
        "likely_identity_supported": likely_identity_supported,
        "frame_selection": frame_selection,
        "status_reasons": status_reasons,
        "frame_detected": detected,
        "query_size": list(image.size),
    }
    def save() -> None:
        with _results_write:
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
                        # What the phone sent with the photo (diagnostics for offline replay).
                        "phone": phone_inputs,
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
                    rebuild_index=False,
                    upload_bytes=data,
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
                           combined, shown, query_image, text_identity)


@parallel_grading_scope
def recognize_bytes(
    data: bytes,
    *,
    settings: Settings,
    runtime: Runtime,
    catalog: sqlite3.Connection,
    results: sqlite3.Connection | None,
    session_id: str,
    persist: bool = True,
    crop_x: float | None = None,
    crop_y: float | None = None,
    crop_w: float | None = None,
    crop_h: float | None = None,
    rotation: int = 0,
    skip_detect: bool = False,
    language: str = "auto",
    store_capture: bool | None = None,
    locale: str | None = None,
    card_quad: list[tuple[float, float]] | None = None,
    graded: bool | None = None,
    client_text: ClientText | None = None,
    client_text_reason: str = 'absent',
    phone_inputs: dict | None = None,
    _grading_job: GradingJob | None = None,
    _progress_observer: Callable | None = None,
    _grading_completion: Callable | None = None,
) -> ScanResponse:
    """Evaluate first, then optionally persist one result and its capture.

    ``persist=False`` evaluates without saving scan/session results or scheduling
    grading updates. It also suppresses captures, even when STORE_CAPTURES is on.

    A failed framing decision may try ONE line-supported frame. Existing useful
    results are never replaced. Recovery uses the same identity/quality guards,
    stays review-only, and cannot discard strong first-pass contradictions.
    Explicit crops and quality retakes do not trigger this extra OCR pass.
    """
    started = time.perf_counter()
    if not persist:
        _grading_completion = None
    ocr_cache = RequestOcrCache()
    kwargs = dict(settings=settings, runtime=runtime, catalog=catalog,
                  results=results, session_id=session_id, crop_x=crop_x,
                  crop_y=crop_y, crop_w=crop_w, crop_h=crop_h, rotation=rotation,
                  skip_detect=skip_detect, language=language, store_capture=store_capture)
    kwargs['_ocr_cache'] = ocr_cache
    if locale:
        kwargs['locale'] = locale
    if card_quad:
        kwargs['card_quad'] = card_quad
    if phone_inputs is not None:
        kwargs['phone_inputs'] = phone_inputs
    if _progress_observer is not None:
        kwargs['_progress_observer'] = _progress_observer
    if _grading_job is not None:
        kwargs['_input_observer'] = _grading_job.start
    # Only the first evaluation may use the phone's text; recoveries read in full.
    first = _recognize_bytes_once(data, **kwargs, client_text=client_text)
    selected = first
    title_recovery = None
    if (getattr(settings, 'ocr_conflict_title_retry', False) and settings.use_ocr and not skip_detect
            and all(v is None for v in (crop_x, crop_y, crop_w, crop_h))
            and title_retry_allowed(first)):
        _, _, title_engine = runtime.require()
        if callable(getattr(title_engine, '_run', None)) and getattr(runtime, 'artwork_verifier', None) is not None:
            mark = time.perf_counter()
            title_recovery = dict(attempted=True, selected=False, original_name=first.ocr.name_text,
                                  first_top_id=first.lead['card_id'])
            try:
                observed, record = read_conflicting_title(title_engine, first.query_image, first.ocr)
                title_recovery['read'] = record
                if observed is not None:
                    retry_kwargs = {k: v for k, v in kwargs.items()
                                    if k not in {'_progress_observer', '_input_observer'}}
                    retry = _recognize_bytes_once(data, **retry_kwargs,
                        _frame_override=('conflicting_title', first.query_image),
                        _frame_detected_override=bool(first.evidence.get('frame_detected')),
                        _title_retry_ocr=observed)
                    verified = {m['card_id'] for m in retry.evidence.get('local_artwork_matches', [])}
                    eligible = bool(retry.lead and retry.lead['card_id'] in verified
                        and retry.response.status in {ScanStatus.uncertain, ScanStatus.printing_ambiguous}
                        and name_match(observed.name_text, retry.lead['name'])
                        and artwork_evidence_compatible(retry.lead, ocr_name=observed.name_text,
                            name_confidence=retry.name_confidence, numbers=first.numbers,
                            languages=first.languages)
                        and not any(retry.lead.get(k) for k in
                            ('strong_name_conflict', 'structured_collector_conflict', 'language_conflict')))
                    # A re-oriented frame falls back to a fresh read; record it.
                    title_recovery.update(retry_top_id=retry.lead['card_id'] if retry.lead else None,
                        observations_used=bool(retry.evidence.get('title_retry_observations_used')),
                        selected=eligible)
                    if eligible:
                        selected = retry
                        selected.timings['first_pass_ms'] = first.timings['total_ms']
            except Exception as error:  # noqa: BLE001 - optional recovery preserves first result
                title_recovery['error_type'] = type(error).__name__
                logging.getLogger(__name__).exception('Optional title recovery failed')
            selected.timings['title_retry_ms'] = (time.perf_counter() - mark) * 1000
    attempted = False
    proposal_ms = embed_ms = 0.
    recovery = {'hypotheses':0,'proposal_profile':None,'proposal_score':None,
                'retry_status':None,'retry_top_id':None,'identity_compatible':None,
                'selection_identity':None}
    # A verified number+name candidate already answered: the boundary retry is skipped
    # (its status is no longer retake). Unverified suggestions still try a better frame.
    if (not skip_detect and all(v is None for v in (crop_x,crop_y,crop_w,crop_h))
            and (first.response.status == ScanStatus.retake or first.text_identity == 'unverified')
            and not first.quality_retake):
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
            keep = _scan_keep(runtime, requested)
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
                    _,scores = top_k(snapshot.embeddings,vector,k=1,keep=keep,segments=getattr(snapshot, 'retrieval_segments', None))
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
    if not grading_requested(settings, graded):
        # The client read the photo and says no slab. Skip label OCR unless
        # card OCR itself already read holder label text: a slab the client
        # missed must not lose its grade.
        grading = GradingEvidence(is_graded=False, grading_status='ungraded',
                                  warnings=['grading_not_requested'])
        label_seen = (any(h.region in ('holder_name', 'holder_collector')
                          for ev in (first, selected) for h in ev.ocr.hits)

                      or any(str((ev.evidence.get('frame_selection') or {}).get('profile', ''))
                             .startswith('slab_') for ev in (first, selected)))
        if (label_seen and getattr(settings, 'use_grading', True)
                and getattr(settings, 'use_ocr', True)):
            _, _, label_engine = runtime.require()
            if label_engine is not None and hasattr(label_engine, 'read_grading'):
                try:
                    grading = label_engine.read_grading(first.input_image)
                    selected.timings['grading_safety_net'] = 1.
                except Exception:  # noqa: BLE001 - keep the plain ungraded result
                    logging.getLogger(__name__).exception('Safety-net grading failed for scan %s', selected.response.id)
    elif getattr(settings, 'use_grading', True) and getattr(settings, 'use_ocr', True):
        _, _, label_engine = runtime.require()
        if deadline:
            if grading_ready:
                try:
                    observed = _grading_job.result()
                    if observed.company is not None:
                        grading = observed
                except Exception:  # noqa: BLE001 - return Raw for manual confirmation
                    logging.getLogger(__name__).exception('Optional grading failed for scan %s', selected.response.id)
            elif (_grading_job is not None and _grading_job.future is not None
                  and _grading_completion is not None):
                grading = GradingEvidence(grading_status='pending')
            elif _grading_completion is not None:
                grading = GradingEvidence(warnings=['grading_worker_busy'])
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
    logging.getLogger('scan.diagnostics').info(
        'grading_hint scan_id=%s hint=%s requested=%s company=%s slab=%s',
        selected.response.id, graded, grading_requested(settings, graded),
        grading.company, grading.slab_detected)
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
                            boundary_retry_selected=float(attempted and selected is not first),
                            total_ms=(time.perf_counter()-started)*1000)
    selected.timings['ocr_cache_hits'] = float(ocr_cache.hits)
    selected.timings['ocr_unique_reads'] = float(ocr_cache.reads)
    selected.response.timings_ms = {key:round(value,2) for key,value in selected.timings.items()}
    selected.evidence['boundary_recovery'] = {
        **recovery,
        'attempted': attempted, 'selected': attempted and selected is not first,
        'first_status': first.response.status.value,
        'first_top_id': first.lead.get('card_id') if first.lead else None,
        'policy': 'one review-only retry; preserve first-pass identity contradictions',
    }
    if title_recovery is not None:
        selected.evidence['title_recovery'] = title_recovery
    selected.evidence['ocr_request_summary'] = {
        'unique_reads': ocr_cache.reads, 'cache_hits': ocr_cache.hits,
        'first_pass_region_reads': first.evidence.get('passes', []),
        'selected_pass_region_reads': selected.evidence.get('passes', []) if selected is not first else [],
        'policy': 'identical request pixels only; pristine cloned observations, no cross-upload cache',
    }
    if client_text is not None or client_text_reason != 'absent':
        frame = first.evidence.get('frame_selection') or {}
        fast = ('used' if first.timings.get('client_text_fast_path')
                else frame.get('client_text_fast_path', 'off'))
        if fast.startswith('eligible'):
            fast = 'server_disagrees'
        ocr_skip = (f'used_{first.ocr.client_text_used}' if first.ocr.client_text_used
                    else frame.get('client_text_ocr', 'off'))
        selected.evidence['client_text'] = {
            'version': CLIENT_TEXT_VERSION, 'parse': client_text_reason, 'fast_path': fast,
            'ocr_skip': ocr_skip,
            'engine': client_text.engine if client_text else None,
            'name': client_text.name if client_text else None,
            'name_conf': client_text.name_conf if client_text else None,
            'number': client_text.number if client_text else None,
            'number_conf': client_text.number_conf if client_text else None,
            'policy': ('fast path skips optional re-reads only; CLIENT_TEXT_OCR may stand in for server '
                       'OCR only where the phone confirms the visual leader; never ranks against it'),
        }
        try:
            logging.getLogger('scan.diagnostics').info('%s', client_text_line(
                selected.response.id, client_text, client_text_reason,
                status=selected.response.status.value, top=selected.lead,
                ocr_name=selected.ocr.name_text, ocr_numbers=selected.numbers, fast_path=fast,
                ocr_skip=ocr_skip))
        except Exception:  # noqa: BLE001 - a log line must not fail the scan
            logging.getLogger(__name__).exception('Client text log failed')
    logging.getLogger('scan.diagnostics').info(
        'scan_reasons scan_id=%s status=%s reasons=%s', selected.response.id,
        selected.response.status.value, ','.join(selected.evidence.get('status_reasons') or ['none']))
    if persist:
        saved = time.perf_counter()
        selected.save()
        if grading.grading_status == 'pending' and _grading_completion is not None:
            _grading_completion(selected.response.id, _grading_job)
            _grading_job.detached = True
        # Saving happens after total_ms is read, so it gets its own line.
        logging.getLogger('scan.diagnostics').info(
            'scan_saved scan_id=%s save_ms=%.1f', selected.response.id, (time.perf_counter() - saved) * 1000)
    return selected.response
