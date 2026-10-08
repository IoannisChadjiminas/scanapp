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
             "same_ms", "busy_ms", "jumps", "ratio"}
_NUMBER_KEYS = {"fps", "detect_ms"}
_TEXT_KEYS = {"route", "host", "cf_ray", "server_trace", "language", "server_scan", "error_type", "state", "scan", "codec"}
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
        "cf_ray",
        "server_trace",
        "cancelled",
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
        "build",
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
        return str(value) if abs(value) <= 10_000_000 else None
    if key in _NUMBER_KEYS and isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):g}" if abs(value) <= 1_000_000 else None
    if key in _TEXT_KEYS:
        return _token(value)
    if key == "build" and isinstance(value, str) and _BUILD.match(value):
        return value
    if key == "cancelled" and isinstance(value, bool):
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
