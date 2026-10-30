"""Turn a stage 1 decision into the scan response, without the full pipeline.

Prices come from the local tables. Grading runs only when the phone said the
photo is a slab. The scan row is saved the same way as a pipeline answer.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import replace
from contextlib import nullcontext
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from app.db import coverage_payload
from app.recognition.detect import server_frame_rect, warp_to_rect
from app.recognition.pipeline import _preview_candidates, _results_write
from app.recognition.presentation import match_presentation
from app.recognition.stage1_gate import (
    MIN_INLIERS, Decision, GateOptions, collapse_hits, decide, load_catalogue, lookup, one_card,
    printing_group, resolve_number, text_fields, text_number_candidates,
)
from app.recognition.client_embedding import parse_client_embedding
from app.schemas import (
    GradingEvidence, OcrEvidence, RecognitionConfidence, ScanResponse, ScanStatus, PrintingReview,
)

log = logging.getLogger('scan.diagnostics')


def _catalogue(runtime, catalog: sqlite3.Connection, options: GateOptions):
    cached = getattr(runtime, 'stage1_catalogue', None)
    key = (options.set_totals, options.normalize_duplicates, options.promo_numbers)
    if cached is None or getattr(runtime, 'stage1_catalogue_options', None) != key:
        cached = load_catalogue(catalog, options)
        runtime.stage1_catalogue = cached
        runtime.stage1_catalogue_options = key
    return cached


def _reference(verifier, image_path: str | None) -> str | None:
    if not image_path or verifier is None:
        return None
    root = verifier.root
    named = root / Path(image_path).name
    if named.is_file():
        return str(named)
    path = Path(image_path)
    if path.is_file() and path.resolve().is_relative_to(root):
        return str(path)
    return None


def _phone_rect(photo: Image.Image, quad) -> np.ndarray | None:
    """Phone corners in pixels, in the order the phone sent them.

    The measured stage 1b check warps those corners directly. A geometry
    rejection here would drop photos the simulation accepted.
    """
    if not quad or len(quad) != 4:
        return None
    width, height = photo.size
    return np.array([[float(x) * (width - 1), float(y) * (height - 1)] for x, y in quad], dtype=np.float32)


def _artwork(runtime, image_bytes: bytes, quad, card_id: str, image_path: str | None,
             server_rect: np.ndarray | None = None) -> int | None:
    verifier = getattr(runtime, 'artwork_verifier', None)
    reference = _reference(verifier, image_path)
    if verifier is None or reference is None or (not quad and server_rect is None):
        return None
    try:
        photo = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes))).convert('RGB')
    except Exception:
        return None
    pair = (card_id, reference)
    found = []
    rect = _phone_rect(photo, quad) if quad else server_rect
    if rect is not None:
        try:
            found = verifier.verify(warp_to_rect(photo, rect), [pair])
        except Exception:
            log.exception('stage1 phone quad verify failed')
            found = []
    if not found and hasattr(verifier, 'propose_frame'):
        try:
            aligned = verifier.propose_frame(photo, pair)
            found = verifier.verify(aligned, [pair]) if aligned is not None else []
        except Exception:
            log.exception('stage1 frame verify failed')
            found = []
    if not found or found[0].artwork_inliers < MIN_INLIERS:
        return None
    return int(found[0].artwork_inliers)


def _server_frame_vector(runtime, image_bytes: bytes):
    """The server's own detected frame and one embedding of it: (rect, vector) or None.

    The same detector and model the full pipeline starts with. Costs one detection and
    one embedding, so callers only ask once the text already names a single card.
    """
    embedder = getattr(runtime, 'embedder', None)
    if embedder is None:
        try:
            embedder = runtime.require()[1]
        except Exception:
            return None
    try:
        photo = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes))).convert('RGB')
        rect = server_frame_rect(photo)
        if rect is None:
            return None
        return rect, np.asarray(embedder.embed(warp_to_rect(photo, rect), 'pad'), dtype=np.float32)
    except Exception:
        log.exception('stage1b server frame failed')
        return None


def card_shaped_quad(quad, size: tuple[int, int]) -> bool:
    """Whether the phone's corners, in pixels, have a raw card's proportions (0.66 to 0.78 wide over tall)."""
    if not quad or len(quad) != 4:
        return False
    width, height = size
    pts = [(float(x) * (width - 1), float(y) * (height - 1)) for x, y in quad]

    def edge(a, b):
        return ((pts[a][0] - pts[b][0]) ** 2 + (pts[a][1] - pts[b][1]) ** 2) ** 0.5
    wide = (edge(0, 1) + edge(3, 2)) / 2
    tall = (edge(0, 3) + edge(1, 2)) / 2
    return tall > 0 and 0.66 <= wide / tall <= 0.78


def _phone_frame_vector(runtime, image_bytes: bytes, card_quad):
    """Stage 1b frame when the server finds none: the phone's card-shaped corners, else the whole upload.

    The artwork check still runs on this frame, so this only changes what is compared, never
    whether a photo is accepted without verification.
    """
    embedder = getattr(runtime, 'embedder', None)
    if embedder is None:
        try:
            embedder = runtime.require()[1]
        except Exception:
            return None
    try:
        photo = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes))).convert('RGB')
        if card_shaped_quad(card_quad, photo.size):
            rect = _phone_rect(photo, card_quad)
        else:
            width, height = photo.size
            rect = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
        return rect, np.asarray(embedder.embed(warp_to_rect(photo, rect), 'pad'), dtype=np.float32)
    except Exception:
        log.exception('stage1b phone frame failed')
        return None


def _evaluate_server_frame(*, settings, runtime, catalog, client_text, card_quad, image_bytes, options) -> Decision:
    """Stage 1b for a photo with no phone vector (usually no corners either): the text names one card.

    Whatever the outcome of the gate, an answer still needs the single-card artwork
    check, here on the server's frame. A vector that agrees is not enough by itself,
    because the server vector comes from the same frame the artwork check would use.
    """
    started = time.perf_counter()
    snapshot = getattr(runtime, 'snapshot', None)
    embeddings = getattr(snapshot, 'embeddings', None) if snapshot is not None else None
    card_ids = [str(card_id) for card_id in getattr(snapshot, 'card_ids', [])] if snapshot is not None else []
    if embeddings is None or not card_ids or embeddings.shape[0] != len(card_ids):
        return Decision(False, None, None, None, None, 'no_index', 0)
    by_key, by_id, bare_ids = _catalogue(runtime, catalog, options)
    name, number, language, label = text_fields(client_text)
    number, used_candidate = resolve_number(name, number, text_number_candidates(client_text), language, by_key, options)
    hits = collapse_hits(lookup(by_key, name, number, language, options), bare_ids)
    if not hits:
        return Decision(False, None, None, None, None, 'no_unique_text', (time.perf_counter() - started) * 1000)
    if len(hits) > 1:
        position = {card_id: index for index, card_id in enumerate(card_ids)}
        if printing_group(hits, embeddings, position)[0] is None and one_card(hits, language, embeddings, position) is None:
            return Decision(False, None, None, None, None, 'ambiguous_text', (time.perf_counter() - started) * 1000)
    framed = _server_frame_vector(runtime, image_bytes)
    if framed is None and getattr(settings, 'stage1b_frame_fallback', False):
        framed = _phone_frame_vector(runtime, image_bytes, card_quad)
    if framed is None:
        return Decision(False, None, None, None, None, 'no_server_frame', (time.perf_counter() - started) * 1000)
    rect, vector = framed
    decision = decide(
        vector, np.asarray(embeddings, dtype=np.float32), card_ids,
        by_key=by_key, by_id=by_id, bare_ids=bare_ids,
        name=name, number=number, language=language, quad_ok=True,
        stage1b=True, label=label, options=options)
    if decision.answered:
        # A stage 1 answer here would rest on the server's own frame alone. Verify the artwork too.
        decision = replace(decision, answered=False, stage='1b_pending', reason='needs_artwork')
    decision = replace(decision, number_candidate=used_candidate)
    if decision.stage != '1b_pending':
        return replace(decision, ms=(time.perf_counter() - started) * 1000)
    card = by_id.get(decision.card_id or '')
    inliers = _artwork(runtime, image_bytes, card_quad, decision.card_id or '',
                       None if card is None else card.get('image_path'), server_rect=rect)
    elapsed = (time.perf_counter() - started) * 1000
    if inliers is None:
        return replace(decision, answered=False, stage=None, card_id=None, inliers=None,
                       reason='artwork_miss', ms=elapsed)
    return replace(decision, answered=True, stage='1b', inliers=inliers, reason='server_frame_artwork', ms=elapsed)


def evaluate_stage1(*, settings, runtime, catalog, client_text: str | None,
                    client_embedding: str | None, card_quad, image_bytes: bytes) -> Decision:
    """Stage 1, then stage 1b when that flag is on. Abstain is not an error."""
    snapshot = getattr(runtime, 'snapshot', None)
    embeddings = getattr(snapshot, 'embeddings', None) if snapshot is not None else None
    card_ids = [str(card_id) for card_id in getattr(snapshot, 'card_ids', [])] if snapshot is not None else []
    vector, vector_reason = parse_client_embedding(client_embedding)
    if vector is None:
        if (getattr(settings, 'stage1b_server_frame', False) and getattr(settings, 'stage1b_text_verify', False)
                and not client_embedding and client_text):
            return _evaluate_server_frame(settings=settings, runtime=runtime, catalog=catalog, client_text=client_text,
                                          card_quad=card_quad, image_bytes=image_bytes, options=GateOptions.from_settings(settings))
        return Decision(False, None, None, None, None, vector_reason if client_embedding else 'no_embedding', 0)
    if embeddings is None or not card_ids or embeddings.shape[0] != len(card_ids):
        return Decision(False, None, None, None, None, 'no_index', 0)
    options = GateOptions.from_settings(settings)
    by_key, by_id, bare_ids = _catalogue(runtime, catalog, options)
    name, number, language, label = text_fields(client_text)
    number, used_candidate = resolve_number(name, number, text_number_candidates(client_text), language, by_key, options)
    stage1b = bool(getattr(settings, 'stage1b_text_verify', False))
    decision = decide(
        vector, np.asarray(embeddings, dtype=np.float32), card_ids,
        by_key=by_key, by_id=by_id, bare_ids=bare_ids,
        name=name, number=number, language=language, quad_ok=bool(card_quad),
        stage1b=stage1b, label=label, options=options)
    decision = replace(decision, number_candidate=used_candidate)
    if decision.stage != '1b_pending':
        return decision
    card = by_id.get(decision.card_id or '')
    started = time.perf_counter()
    inliers = _artwork(runtime, image_bytes, card_quad, decision.card_id or '', None if card is None else card.get('image_path'))
    elapsed = decision.ms + (time.perf_counter() - started) * 1000
    if inliers is None:
        return replace(decision, answered=False, stage=None, card_id=None, inliers=None, reason='artwork_miss', ms=elapsed)
    return replace(decision, answered=True, stage='1b', inliers=inliers, reason='artwork', ms=elapsed)


def answer_stage1(*, decision: Decision, settings, runtime, catalog, results, session_id: str,
                  client_text: str | None, graded: bool | None, image_bytes: bytes,
                  on_persist=None) -> ScanResponse:
    name, number, _language, _label = text_fields(client_text)
    shown = _preview_candidates(catalog, [decision.card_id or ''])
    if not shown:
        raise LookupError(decision.card_id)
    item = {**shown[0], 'visual_score': 0.0, 'combined_score': 0.0, 'ocr_consistent': True,
            'retrieved_via': [f'stage{decision.stage}']}
    status = ScanStatus.uncertain if getattr(settings, 'stage1_require_confirmation', True) else ScanStatus.matched
    printing_review = None
    if decision.printing_ids:
        # Same artwork identifies the card, never its stamp/edition. Reuse the
        # existing explicit printing-selection and feedback contract.
        members = _preview_candidates(catalog, list(decision.printing_ids))
        if len(members) != len(decision.printing_ids) or members[0]['card_id'] != decision.card_id:
            raise LookupError('incomplete stage1 printing group')
        status = ScanStatus.printing_ambiguous
        printing_review = PrintingReview(
            reason='stage1_same_artwork_reprint', candidate_group_id='stage1:' + (decision.card_id or ''),
            grouping_basis='reference_vector_similarity_or_catalogue_reprint',
            reference_coverage_complete=False, collector_evidence=[number] if number else [],
            plausible_printings=members,
            guidance='Choose the exact printing, including any Prize Pack stamp, before confirming.')
    grading = GradingEvidence(is_graded=False, grading_status='ungraded', warnings=['grading_not_requested'])
    if graded is True:
        _snapshot, _embedder, engine = runtime.require()
        if engine is not None and hasattr(engine, 'read_grading'):
            try:
                photo = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes))).convert('RGB')
                grading = engine.read_grading(photo)
            except Exception:
                log.exception('stage1 grading failed')
                grading = GradingEvidence(warnings=['grading_failed'])
    versions = runtime.versions() if hasattr(runtime, 'versions') else {}
    versions['stage'] = decision.stage or ''
    if decision.margin is not None:
        versions['stage_margin'] = f'{decision.margin:.4f}'
    if decision.inliers is not None:
        versions['stage_inliers'] = str(decision.inliers)
    timings = {'total_ms': round(decision.ms, 2), 'stage1_ms': round(decision.ms, 2)}
    confidence = RecognitionConfidence(
        candidate_card_id=decision.card_id, visual_margin=decision.margin,
        identity='stage1', requires_confirmation=status != ScanStatus.matched,
        printing='ambiguous' if printing_review else 'unconfirmed',
        reasons=[f'stage_{decision.stage}', *(['choose_printing'] if printing_review else [])])
    presentation = match_presentation([item], status=status.value, printing_review=printing_review)
    scan_id = str(uuid.uuid4())
    response = ScanResponse(
        id=scan_id, status=status, suggestions=[],
        ocr=OcrEvidence(name_text=name, collector_text=number, failed=False),
        coverage=coverage_payload(catalog), timings_ms=timings, versions=versions,
        message='Check this card before confirming.' if status == ScanStatus.uncertain else None,
        confidence=confidence, grading=grading,
        printing_review=printing_review,
        **presentation.model_dump(mode='json'))
    # Candidate list stays the one card. Presentation may repeat it as the best match.
    from app.schemas import Candidate
    response.suggestions = [Candidate.model_validate(item)]
    if results is not None:
        with _results_write, getattr(results, '_cache_lock', nullcontext()):
            results.execute(
                """
                INSERT INTO scans (
                    id, session_id, created_at, status, preprocessing, model_revision,
                    catalogue_version, ocr_version, ranking_version, threshold_config_json,
                    ocr_json, visual_ranking_json, combined_ranking_json, timings_json,
                    confirmed_card_id, rejected, error
                ) VALUES (?, ?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, NULL)
                """,
                (scan_id, session_id, status.value, settings.preprocess_config,
                 versions.get('model_revision', ''), versions.get('catalogue', ''),
                 versions.get('ocr', ''), versions.get('ranking', ''),
                 json.dumps({}), json.dumps({'stage': decision.stage, 'card_id': decision.card_id,
                     **({'printing_review': printing_review.model_dump(mode='json')} if printing_review else {})}),
                 json.dumps([item]), json.dumps([item]), json.dumps(timings)))
            try:
                if on_persist is not None:
                    on_persist(results, scan_id, status.value)
                results.commit()
            except Exception:
                results.rollback()
                raise
    return response
