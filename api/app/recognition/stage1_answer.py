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
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from app.db import coverage_payload
from app.recognition.detect import warp_to_rect
from app.recognition.pipeline import _preview_candidates, _results_write
from app.recognition.presentation import match_presentation
from app.recognition.stage1_gate import (
    MIN_INLIERS, Decision, decide, load_catalogue, text_fields,
)
from app.recognition.client_embedding import parse_client_embedding
from app.schemas import (
    GradingEvidence, OcrEvidence, RecognitionConfidence, ScanResponse, ScanStatus,
)

log = logging.getLogger('scan.diagnostics')


def _catalogue(runtime, catalog: sqlite3.Connection):
    cached = getattr(runtime, 'stage1_catalogue', None)
    if cached is None:
        cached = load_catalogue(catalog)
        runtime.stage1_catalogue = cached
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


def _artwork(runtime, image_bytes: bytes, quad, card_id: str, image_path: str | None) -> int | None:
    verifier = getattr(runtime, 'artwork_verifier', None)
    reference = _reference(verifier, image_path)
    if verifier is None or reference is None or not quad:
        return None
    try:
        photo = ImageOps.exif_transpose(Image.open(BytesIO(image_bytes))).convert('RGB')
    except Exception:
        return None
    pair = (card_id, reference)
    found = []
    rect = _phone_rect(photo, quad)
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


def evaluate_stage1(*, settings, runtime, catalog, client_text: str | None,
                    client_embedding: str | None, card_quad, image_bytes: bytes) -> Decision:
    """Stage 1, then stage 1b when that flag is on. Abstain is not an error."""
    snapshot = getattr(runtime, 'snapshot', None)
    embeddings = getattr(snapshot, 'embeddings', None) if snapshot is not None else None
    card_ids = [str(card_id) for card_id in getattr(snapshot, 'card_ids', [])] if snapshot is not None else []
    vector, vector_reason = parse_client_embedding(client_embedding)
    if vector is None:
        return Decision(False, None, None, None, None, vector_reason if client_embedding else 'no_embedding', 0)
    if embeddings is None or not card_ids or embeddings.shape[0] != len(card_ids):
        return Decision(False, None, None, None, None, 'no_index', 0)
    by_key, by_id, bare_ids = _catalogue(runtime, catalog)
    name, number, language, label = text_fields(client_text)
    stage1b = bool(getattr(settings, 'stage1b_text_verify', False))
    decision = decide(
        vector, np.asarray(embeddings, dtype=np.float32), card_ids,
        by_key=by_key, by_id=by_id, bare_ids=bare_ids,
        name=name, number=number, language=language, quad_ok=bool(card_quad),
        stage1b=stage1b, label=label)
    if decision.stage != '1b_pending':
        return decision
    card = by_id.get(decision.card_id or '')
    started = time.perf_counter()
    inliers = _artwork(runtime, image_bytes, card_quad, decision.card_id or '', None if card is None else card.get('image_path'))
    elapsed = decision.ms + (time.perf_counter() - started) * 1000
    if inliers is None:
        return Decision(False, None, None, decision.margin, None, 'artwork_miss', elapsed)
    return Decision(True, '1b', decision.card_id, decision.margin, inliers, 'artwork', elapsed)


def answer_stage1(*, decision: Decision, settings, runtime, catalog, results, session_id: str,
                  client_text: str | None, graded: bool | None, image_bytes: bytes) -> ScanResponse:
    name, number, _language, _label = text_fields(client_text)
    shown = _preview_candidates(catalog, [decision.card_id or ''])
    if not shown:
        raise LookupError(decision.card_id)
    item = {**shown[0], 'visual_score': 0.0, 'combined_score': 0.0, 'ocr_consistent': True,
            'retrieved_via': [f'stage{decision.stage}']}
    status = ScanStatus.uncertain if getattr(settings, 'stage1_require_confirmation', True) else ScanStatus.matched
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
        reasons=[f'stage_{decision.stage}'])
    presentation = match_presentation([item], status=status.value, printing_review=None)
    scan_id = str(uuid.uuid4())
    response = ScanResponse(
        id=scan_id, status=status, suggestions=[],
        ocr=OcrEvidence(name_text=name, collector_text=number, failed=False),
        coverage=coverage_payload(catalog), timings_ms=timings, versions=versions,
        message='Check this card before confirming.' if status == ScanStatus.uncertain else None,
        confidence=confidence, grading=grading,
        **presentation.model_dump(mode='json'))
    # Candidate list stays the one card. Presentation may repeat it as the best match.
    from app.schemas import Candidate
    response.suggestions = [Candidate.model_validate(item)]
    if results is not None:
        with _results_write:
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
                 json.dumps({}), json.dumps({'stage': decision.stage, 'card_id': decision.card_id}),
                 json.dumps([item]), json.dumps([item]), json.dumps(timings)))
            results.commit()
    return response
