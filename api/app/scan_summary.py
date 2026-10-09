"""One greppable line per scan, so switches can be compared from staging logs.

`scan_summary` describes how the server answered a scan and which switches
were on. `scan_outcome` records what the user did with it. Both carry the scan
id, so `scripts/scan_report.py` can join them with the phone's diagnostics.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
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


PLATFORMS = ('ios', 'android')
CAPTURES = ('auto', 'manual', 'gallery')
CAMERAS = ('native', 'plugin')
QUAD_SOURCES = ('rect', 'document')
_BUILD = re.compile(r'^[0-9A-Za-z.+_-]{1,24}$')
_LOCALE = re.compile(r'^[A-Za-z]{2,3}([_-][A-Za-z0-9]{2,8})?$')


@dataclass(frozen=True)
class ScanSource:
    """Where a scan came from. Every field is optional: older app builds send none."""
    platform: str = 'unknown'
    capture: str = 'unknown'
    camera: str = 'unknown'
    build: str = 'unknown'
    locale: str = 'unknown'
    quad: str = 'none'  # none, or the detector that found the corners the phone sent
    quad_valid: bool = False


def _choice(value: str | None, allowed: tuple[str, ...]) -> str:
    cleaned = (value or '').strip().lower()
    return cleaned if cleaned in allowed else 'unknown'


def parse_quad(raw: str | None) -> list[tuple[float, float]] | None:
    """Four corners as "x1,y1,x2,y2,x3,y3,x4,y4", fractions of the photo, clockwise from top-left."""
    try:
        values = [float(part) for part in (raw or '').split(',')]
    except ValueError:
        return None
    if len(values) != 8 or any(not -0.05 <= v <= 1.05 for v in values):
        return None
    points = list(zip(values[0::2], values[1::2]))
    area = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        area += x1 * y2 - x2 * y1
    # A real card is a clockwise quad (image y points down) covering a visible part of the photo.
    return points if area / 2 >= 0.02 else None


def scan_source(*, platform: str | None = None, capture: str | None = None,
                camera: str | None = None, app_build: str | None = None,
                locale: str | None = None, card_quad: str | None = None,
                quad_source: str | None = None) -> ScanSource:
    """Normalise what the phone says about itself. Unknown values never fail a scan."""
    build = (app_build or '').strip()
    loc = (locale or '').strip()
    has_quad = bool((card_quad or '').strip())
    return ScanSource(
        platform=_choice(platform, PLATFORMS),
        capture=_choice(capture, CAPTURES),
        camera=_choice(camera, CAMERAS),
        build=build if _BUILD.match(build) else 'unknown',
        locale=loc.replace('-', '_') if _LOCALE.match(loc) else 'unknown',
        quad=(_choice(quad_source, QUAD_SOURCES) if has_quad else 'none'),
        quad_valid=parse_quad(card_quad) is not None if has_quad else False,
    )


def source_parts(source: ScanSource | None) -> list[str]:
    if source is None:
        return []
    return [f'platform={source.platform}', f'capture={source.capture}',
            f'camera={source.camera}', f'build={source.build}', f'locale={source.locale}',
            f'quad={source.quad}', f'quad_valid={str(source.quad_valid).lower()}']


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
                      flags: list[str], source: ScanSource | None = None) -> str:
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
        *source_parts(source),
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
