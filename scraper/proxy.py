"""Sticky residential proxy. The password is never logged."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import quote, unquote, urlparse

EXIT_URL = "https://ipinfo.io/json"
DIRECT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
_TITLE = re.compile(rb"<title[^>]*>(.*?)</title>", re.I | re.S)


def proxy_server(session_id: str) -> str | None:
    host = os.environ.get("PROXY_HOST", "").strip()
    user = os.environ.get("PROXY_USER", "").strip()
    password = os.environ.get("PROXY_PASS", "")
    country = os.environ.get("PROXY_COUNTRY", "").strip()
    template = os.environ.get("PROXY_USER_TEMPLATE", "").strip()
    if not host or not user or not password or not session_id:
        return None
    if not template:
        # DataImpulse-style sticky session. Confirm the template in the dashboard.
        template = "{user}__cr.{country};sessid.{session}" if country else "{user};sessid.{session}"
    username = template.format(user=user, session=session_id, country=country)
    return f"http://{quote(username, safe='')}:{quote(password, safe='')}@{host}"


def seleniumbase_proxy(proxy_url: str | None) -> str | None:
    """SeleniumBase wants ``user:pass@host:port``, without a scheme."""
    parsed = urlparse(proxy_url or "")
    host = parsed.hostname
    if not host:
        return None
    port = f":{parsed.port}" if parsed.port else ""
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    if user and password:
        return f"{user}:{password}@{host}{port}"
    if user:
        return f"{user}@{host}{port}"
    return f"{host}{port}"


def _opener(proxy_url: str):
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
    )


def proxy_exit(proxy_url: str, timeout: float = 8.0) -> dict:
    """Exit IP, country, and network of this sticky session, as a site sees it."""
    with _opener(proxy_url).open(EXIT_URL, timeout=timeout) as response:
        body = json.loads(response.read(4096) or b"{}")
    return {key: str(body.get(key) or "") for key in ("ip", "country", "org")}


def proxy_direct(proxy_url: str, url: str, timeout: float = 15.0, limit: int = 65536) -> dict:
    """One plain HTTPS GET through this sticky session, without a browser.

    A Cloudflare status here with a stalled Chrome points at the browser; a
    stall here too points at the exit IP.
    """
    request = urllib.request.Request(url, headers=DIRECT_HEADERS)
    try:
        response = _opener(proxy_url).open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = response.read(limit) or b""
        status = int(getattr(response, "status", None) or getattr(response, "code", 0) or 0)
        headers = response.headers
    match = _TITLE.search(body)
    title = match.group(1).decode("utf-8", "replace") if match else ""
    return {
        "status": status,
        "bytes": len(body),
        "server": str(headers.get("server") or ""),
        "cf_mitigated": str(headers.get("cf-mitigated") or ""),
        "title": " ".join(title.split())[:80],
    }
