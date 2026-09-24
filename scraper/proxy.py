"""Sticky residential proxy. The password is never logged."""

from __future__ import annotations

import json
import os
import urllib.request
from urllib.parse import quote, unquote, urlparse

EXIT_URL = "https://ipinfo.io/json"


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


def proxy_exit(proxy_url: str, timeout: float = 8.0) -> dict:
    """Exit IP, country, and network of this sticky session, as a site sees it."""
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
    )
    with opener.open(EXIT_URL, timeout=timeout) as response:
        body = json.loads(response.read(4096) or b"{}")
    return {key: str(body.get(key) or "") for key in ("ip", "country", "org")}
