from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any

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
from app.recognition.detect import detect_and_rectify
from app.recognition.embed import top_k
from app.recognition.images import apply_crop, blur_variance, decode_image
from app.recognition.language import expand_language, language_label, resolve_search_languages
from app.recognition.ocr import OcrResult
from app.recognition.rank import decide_status, extract_collector_candidates, rerank
from app.recognition.runtime import Runtime
from app.schemas import (
    Candidate,
    OcrEvidence,
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
    if not skip_detect:
        image, detected = detect_and_rectify(image)
    query_image = image
    timings["detect_ms"] = (time.perf_counter() - mark) * 1000

    blur = blur_variance(image)
    too_small = min(image.size) < settings.threshold_min_side
    too_blurry = blur < settings.threshold_blur
    retake = too_small or too_blurry

    ocr = OcrResult(failed=True)
    mark = time.perf_counter()
    if settings.use_ocr and ocr_engine is not None and not retake:
        ocr = ocr_engine.read(image)
    timings["ocr_ms"] = (time.perf_counter() - mark) * 1000

    decision = resolve_search_languages(
        language,
        [line for line in [ocr.name_text, ocr.collector_text, *ocr.lines] if line],
    )
    keep = None
    if decision.reason == "user" and decision.search and runtime.card_languages is not None:
        keep = np.isin(runtime.card_languages, list(decision.search))

    mark = time.perf_counter()
    query = embedder.embed(image, settings.preprocess_config)
    timings["embed_ms"] = (time.perf_counter() - mark) * 1000

    mark = time.perf_counter()
    indices, scores = top_k(snapshot.embeddings, query, k=20, keep=keep)
    timings["retrieve_ms"] = (time.perf_counter() - mark) * 1000

    visual: list[dict[str, Any]] = []
    selected_ids = [str(snapshot.card_ids[i]) for i in indices]
    cards = _lookup_cards(catalog, selected_ids)
    for index, score in zip(indices, scores, strict=True):
        card_id = str(snapshot.card_ids[index])
        row = cards.get(card_id)
        if row is None:
            continue
        visual.append(
            {
                "card_id": card_id,
                "name": row["name"],
                "set_name": row["set_name"],
                "collector_number": row["collector_number"],
                "image_url": _card_image_url(row),
                "visual_score": float(score),
                "combined_score": float(score),
                "ocr_consistent": None,
                "language": str(row["language"] or ""),
                "cardmarket_url": url_for_row(row),
            }
        )

    numbers = extract_collector_candidates(
        [line for line in [ocr.collector_text, *ocr.lines] if line],
        hits=ocr.hits,
    )
    rank_languages = (
        decision.search
        if decision.reason == "user"
        else expand_language(decision.detected)
    )
    combined = rerank(
        visual,
        ocr.name_text,
        numbers,
        ocr.failed,
        detected_languages=rank_languages,
    )
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
    shown = combined[:1]
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
    elif status in {"no_match"}:
        message = "This photograph did not match a catalogue card."
    if not detected and not skip_detect and status != "retake":
        extra = " Automatic card detection was unreliable; using the provided crop."
        message = (message or "") + extra

    suggestions = [Candidate.model_validate(item) for item in shown]
    scan_id = str(uuid.uuid4())
    created_at = _now()
    versions = runtime.versions()
    ocr_payload = {
        "name_text": ocr.name_text,
        "collector_text": ocr.collector_text,
        "lines": ocr.lines,
        "failed": ocr.failed,
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
    }
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
            json.dumps(visual[:20]),
            json.dumps(combined[:20]),
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

    return ScanResponse(
        id=scan_id,
        status=ScanStatus(status),
        suggestions=suggestions,
        ocr=OcrEvidence(
            name_text=ocr.name_text,
            collector_text=ocr.collector_text,
            lines=ocr.lines,
            failed=ocr.failed,
        ),
        coverage=coverage_model,
        timings_ms={key: round(value, 2) for key, value in timings.items()},
        versions=versions,
        message=message.strip() if message else None,
        detected_language=decision.detected,
        search_languages=list(decision.search),
    )
