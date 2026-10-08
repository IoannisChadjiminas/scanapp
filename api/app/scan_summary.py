"""One greppable line per scan, so switches can be compared from staging logs.

`scan_summary` describes how the server answered a scan and which switches
were on. `scan_outcome` records what the user did with it. Both carry the scan
id, so `scripts/scan_report.py` can join them with the phone's diagnostics.
"""
from __future__ import annotations

import json
from typing import Any

# Server switches worth comparing. Each one that is on is listed in `flags`.
SWITCHES = (
    'scan_stream_results',
    'grading_requires_client_hint',
    'ocr_title_only_single_printing',
    'ocr_damaged_footer_order',
    'ocr_complete_frame_first',
    'ocr_adaptive_footer',
    'ocr_parallel_regions',
    'parallel_grading',
    'grading_at_card_deadline',
    'app_slab_detection',
    'app_card_warp',
    'app_native_codec',
    'app_live_outline',
    'app_auto_capture',
    'app_native_camera',
    'app_native_camera_android',
    'app_card_anywhere',
    'trust_client_warp',
)

STAGES = (
    'decode_ms', 'detect_ms', 'frame_proposal_ms', 'embed_ms', 'retrieve_ms',
    'local_artwork_ms', 'ocr_ms', 'grading_wait_ms', 'printing_review_ms',
)


def scan_flags(settings: Any, *, stream: bool = False, skip_detect: bool = False,
               graded: bool | None = None) -> list[str]:
    """Server switches that were on, plus what this request asked for."""
    flags = [name for name in SWITCHES if getattr(settings, name, False) is True]
    preset = getattr(settings, 'app_capture_preset', 'max')
    quality = getattr(settings, 'app_jpeg_quality', 95)
    if preset != 'max':
        flags.append(f'app_capture_{preset}')
    if quality != 95:
        flags.append(f'app_jpeg_{quality}')
    max_edge = getattr(settings, 'app_max_edge', 2000)
    if max_edge != 2000:
        flags.append(f'app_edge_{max_edge}')
    if stream:
        flags.append('req_stream')
    if skip_detect:
        flags.append('req_skip_detect')
    if graded is not None:
        flags.append(f'req_graded_{str(graded).lower()}')
    return flags


def _number(value: Any) -> str:
    try:
        return f'{float(value):.1f}'
    except (TypeError, ValueError):
        return 'none'


def scan_summary_line(result: Any, settings: Any, *, trace: str, upload_bytes: int,
                      flags: list[str]) -> str:
    timings = getattr(result, 'timings_ms', None) or {}
    if hasattr(timings, 'model_dump'):
        timings = timings.model_dump()
    suggestions = list(getattr(result, 'suggestions', None) or [])
    top = suggestions[0] if suggestions else None
    scores = [getattr(item, 'visual_score', None) for item in suggestions[:2]]
    gap = (scores[0] - scores[1]) if len(scores) == 2 and None not in scores else None
    status = getattr(getattr(result, 'status', None), 'value', 'none')
    parts = [
        'scan_summary',
        f'trace={trace}',
        f'scan_id={getattr(result, "id", "none")}',
        f'status={status}',
        f'match_state={getattr(result, "match_state", "none")}',
        f'top={getattr(top, "card_id", None) or "none"}',
        f'visual={_number(scores[0]) if scores and scores[0] is not None else "none"}',
        f'gap={"none" if gap is None else f"{gap:.3f}"}',
        f'total_ms={_number(timings.get("total_ms"))}',
    ]
    parts += [f'{stage}={_number(timings[stage])}' for stage in STAGES if stage in timings]
    parts += [
        f'embeddings={int(timings.get("embeddings", 0))}',
        f'ocr_passes={int(timings.get("ocr_passes_count", 0))}',
        f'footer_skipped={str(bool(timings.get("ocr_footer_skipped"))).lower()}',
        f'bytes={int(upload_bytes)}',
        'thresholds={:.2f}/{:.2f}/{:.2f}'.format(
            float(getattr(settings, 'threshold_min_visual', 0)),
            float(getattr(settings, 'threshold_min_visual_ocr', 0)),
            float(getattr(settings, 'threshold_min_gap', 0))),
        f'flags={",".join(flags) or "none"}',
    ]
    return ' '.join(parts)


def scan_outcome(action: str, chosen: str | None, combined_ranking_json: str | None) -> str:
    """confirmed: the user kept the server's top card; corrected: picked another."""
    if action == 'reject':
        return 'rejected'
    try:
        ranking = json.loads(combined_ranking_json or '[]')
        top = ranking[0].get('card_id') if ranking else None
    except (ValueError, AttributeError, TypeError):
        top = None
    if chosen and top and chosen == top:
        return 'confirmed'
    return 'corrected'


def scan_outcome_line(scan_id: str, *, action: str, chosen: str | None,
                      status: str | None, combined_ranking_json: str | None) -> str:
    return ' '.join([
        'scan_outcome',
        f'scan_id={scan_id}',
        f'action={action}',
        f'outcome={scan_outcome(action, chosen, combined_ranking_json)}',
        f'status={status or "none"}',
        f'chosen={chosen or "none"}',
    ])
