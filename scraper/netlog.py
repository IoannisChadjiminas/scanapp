"""Summarise a Chrome ``--log-net-log`` file for the hosts one attempt cares about.

Chrome writes the file as it goes; a killed browser leaves it cut off mid-list,
so events are read line by line. Only host names, status lines, and Chrome
error names leave this module: never header values.
"""

from __future__ import annotations

import json
from collections import Counter
from urllib.parse import urlsplit

WATCHED = ("cardmarket.com", "cloudflare.com")
_EVENTS = '"events": ['


def _watched(host: str) -> bool:
    return any(host == name or host.endswith("." + name) for name in WATCHED)


def _status(headers: list) -> str:
    line = str(headers[0]) if headers else ""
    parts = line.split(" ", 1)
    return parts[1].strip() if len(parts) == 2 else line.strip()


def _events(body: str):
    for raw in body.splitlines():
        line = raw.strip()
        if line.endswith("],"):
            line = line[:-2]
        line = line.rstrip(",")
        if not line.startswith("{"):
            continue
        try:
            yield json.loads(line)
        except ValueError:
            continue


def summarize_net_log(text: str) -> dict:
    """``{host: {"tunnel": {...}, "response": {...}, "error": {...}}}`` for watched hosts."""
    head, found, body = text.partition(_EVENTS)
    if not found:
        return {}
    try:
        constants = json.loads(head.rstrip().rstrip(",") + "}")["constants"]
    except (ValueError, KeyError, TypeError):
        return {}
    types = {code: name for name, code in (constants.get("logEventTypes") or {}).items()}
    errors = {
        code: name if name.startswith("ERR_") else f"ERR_{name}"
        for name, code in (constants.get("netError") or {}).items()
    }

    tunnel_host: dict[int, str] = {}
    tunnel_reply: dict[int, str] = {}
    request_host: dict[int, str] = {}
    responses: dict[str, Counter] = {}
    failures: dict[str, Counter] = {}

    for event in _events(body):
        name = types.get(event.get("type"))
        source = (event.get("source") or {}).get("id")
        params = event.get("params") or {}
        if name == "HTTP_TRANSACTION_SEND_TUNNEL_HEADERS":
            for header in params.get("headers") or []:
                if str(header).lower().startswith("host:"):
                    host = str(header).split(":", 1)[1].strip().rsplit(":", 1)[0]
                    if _watched(host):
                        tunnel_host[source] = host
        elif name == "HTTP_TRANSACTION_READ_TUNNEL_RESPONSE_HEADERS" and source in tunnel_host:
            tunnel_reply[source] = _status(params.get("headers") or [])
        elif name == "URL_REQUEST_START_JOB":
            host = urlsplit(str(params.get("url") or "")).hostname or ""
            if _watched(host):
                request_host[source] = host
        elif name == "HTTP_TRANSACTION_READ_RESPONSE_HEADERS" and source in request_host:
            responses.setdefault(request_host[source], Counter())[
                _status(params.get("headers") or [])
            ] += 1
        elif name == "REQUEST_ALIVE" and source in request_host:
            code = params.get("net_error")
            if isinstance(code, int) and code != 0:
                failures.setdefault(request_host[source], Counter())[
                    errors.get(code, str(code))
                ] += 1

    summary: dict[str, dict] = {}
    for source, host in tunnel_host.items():
        reply = tunnel_reply.get(source, "no reply")
        summary.setdefault(host, {}).setdefault("tunnel", Counter())[reply] += 1
    for host, counts in responses.items():
        summary.setdefault(host, {})["response"] = counts
    for host, counts in failures.items():
        summary.setdefault(host, {})["error"] = counts
    for host in set(request_host.values()):
        summary.setdefault(host, {})
    return {
        host: {kind: dict(counts) for kind, counts in parts.items()}
        for host, parts in sorted(summary.items())
    }


def read_net_log(path: str) -> dict:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return summarize_net_log(handle.read())
    except OSError:
        return {}
