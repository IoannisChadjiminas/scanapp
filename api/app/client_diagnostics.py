"""Phone scan timings. Values are allow-listed so a client cannot write
URLs, photos, card text, or secrets into the log."""

from __future__ import annotations

import re
from typing import Any

_TOKEN = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")
_EVENT = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")
_BUILD = re.compile(r"^[0-9A-Za-z.]{1,20}\+[0-9]{1,6}$|^[0-9A-Za-z.]{1,20}$")
_INT_KEYS = {"status", "elapsed_ms", "bytes", "queued", "entries", "quality", "frames", "found",
             "wait_ms", "missed_ms", "steady_ms", "focus_ms", "held_ms", "looks", "holder", "coasted",
             "same_ms", "busy_ms", "jumps", "ratio",
             # The phone's own match and provisional card, and the footer read.
             "ms_after_shutter", "round_trip_ms", "shutter_to_done_ms", "rows", "read_ms",
             "extra_wait_ms", "crop_w", "crop_h", "candidates", "guide_w", "guide_h", "installed_age_days"}
_NUMBER_KEYS = {"fps", "detect_ms", "print_gap", "native_ms", "load_ms"}
_TEXT_KEYS = {"route", "host", "cf_ray", "server_trace", "language", "server_scan", "error_type", "state", "scan", "codec", "price_source", "version",
              # Catalogue card ids and short reason words only (the token pattern), never card text.
              "card", "provisional", "final", "reason", "kind"}
# Yes/no fields. Only a real boolean is kept, so "name"/"number" can never carry the card's text.
_BOOL_KEYS = {"cancelled", "stored", "guessed", "agree", "ok", "name", "number", "text_name", "text_number"}
_MAX_EVENTS = 40
_MAX_TIMINGS = 40


def phone_diagnostic_lines(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        raise ValueError("diagnostics body must be an object")
    raw = payload.get("events")
    if not isinstance(raw, list) or len(raw) > _MAX_EVENTS:
        raise ValueError("diagnostics events must be a short list")
    lines: list[str] = []
    for item in raw:
        line = _event_line(item)
        if line:
            lines.append(line)
    return lines


def _event_line(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    event = item.get("event")
    if not isinstance(event, str) or not _EVENT.match(event):
        return None
    parts = [f"event={event}"]
    scan = _token(item.get("scan"))
    if scan:
        parts.append(f"scan={scan}")
    for key in (
        "route",
        "host",
        "status",
        "elapsed_ms",
        "bytes",
        "queued",
        "entries",
        "language",
        "server_scan",
        "error_type",
        "state",
        "version",
        "installed_age_days",
        "cf_ray",
        "server_trace",
        "cancelled",
        "stored",
        "guessed",
        "price_source",
        "quality",
        "codec",
        "frames",
        "found",
        "fps",
        "detect_ms",
        "wait_ms",
        "missed_ms",
        "steady_ms",
        "focus_ms",
        "held_ms",
        "looks",
        "holder",
        "coasted",
        "same_ms",
        "busy_ms",
        "jumps",
        "ratio",
        "print_gap",
        "build",
        "card",
        "provisional",
        "final",
        "agree",
        "reason",
        "ms_after_shutter",
        "native_ms",
        "round_trip_ms",
        "shutter_to_done_ms",
        "kind",
        "rows",
        "load_ms",
        "ok",
        "name",
        "number",
        "text_name",
        "text_number",
        "read_ms",
        "extra_wait_ms",
        "crop_w",
        "crop_h",
        "candidates",
        "guide_w",
        "guide_h",
    ):
        value = _scalar(key, item.get(key))
        if value is not None:
            parts.append(f"{key}={value}")
    timings = _timings(item.get("server_timings"))
    if timings:
        parts.append(f"server_timings={timings}")
    return "phone " + " ".join(parts)


def _token(value: Any) -> str | None:
    if not isinstance(value, str) or not _TOKEN.match(value):
        return None
    return value


def _scalar(key: str, value: Any) -> str | None:
    if key in _INT_KEYS and isinstance(value, bool):
        return None
    if key in _INT_KEYS and isinstance(value, int) and not isinstance(value, bool):
        limit = 1_000_000_000 if key == 'bytes' else 10_000_000
        return str(value) if abs(value) <= limit else None
    if key in _NUMBER_KEYS and isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):g}" if abs(value) <= 1_000_000 else None
    if key in _TEXT_KEYS:
        if key == 'version':
            return value if isinstance(value, str) and re.fullmatch(r'[a-f0-9]{64}', value) else None
        return _token(value)
    if key == "build" and isinstance(value, str) and _BUILD.match(value):
        return value
    if key in _BOOL_KEYS and isinstance(value, bool):
        return "true" if value else "false"
    if key == "status" and isinstance(value, str):
        return _token(value)
    return None


def _timings(value: Any) -> str | None:
    if not isinstance(value, dict) or len(value) > _MAX_TIMINGS:
        return None
    kept: list[str] = []
    for key, item in value.items():
        if not isinstance(key, str) or not _EVENT.match(key):
            continue
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            continue
        kept.append(f"{key}:{item}")
    if not kept:
        return None
    return ",".join(kept)
