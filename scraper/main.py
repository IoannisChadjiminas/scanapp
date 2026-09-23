"""Internal Cardmarket fallback. scanapp is the only caller."""

from __future__ import annotations

import hmac
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
API = HERE.parent / "api"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(API))

from allow import cardmarket_product  # noqa: E402
from browser import ATTEMPT_SECONDS, ChromeSession, reap_stale_browsers, run_attempt  # noqa: E402
from proxy import proxy_server  # noqa: E402
from app.cardmarket_html import parse_cardmarket_html  # noqa: E402

log = logging.getLogger("scraper")
logging.basicConfig(level=logging.INFO, format="%(message)s")

API_KEY = os.environ.get("SCRAPER_API_KEY", "")
MAX_BROWSERS = max(1, int(os.environ.get("MAX_BROWSERS", "1")))
COOLDOWN_SECONDS = float(os.environ.get("SCRAPER_RATE_LIMIT_S", "900"))

app = FastAPI(title="Cardmarket scraper", docs_url=None, redoc_url=None)
_slots = threading.BoundedSemaphore(MAX_BROWSERS)
_cooldown_until = 0.0
_cooldown_lock = threading.Lock()


class ScrapeRequest(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    session_id: str = Field(min_length=1, max_length=80)


def _authorized(header: str | None) -> bool:
    raw = (header or "").strip()
    token = raw[7:].strip() if raw.lower().startswith("bearer ") else ""
    if not API_KEY or not token:
        return False
    return hmac.compare_digest(token, API_KEY)


def open_session(session_id: str) -> ChromeSession:
    return ChromeSession(proxy_server(session_id))


@app.get("/health")
def health() -> dict:
    with _cooldown_lock:
        left = max(0.0, _cooldown_until - time.time())
    return {"ok": True, "cooldown_until": time.time() + left if left else 0}


@app.post("/scrape")
def scrape(payload: ScrapeRequest, authorization: str | None = Header(default=None)) -> dict:
    global _cooldown_until
    if not _authorized(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not cardmarket_product(payload.url):
        raise HTTPException(status_code=400, detail="Cardmarket product URL required")
    with _cooldown_lock:
        left = _cooldown_until - time.time()
    if left > 0:
        raise HTTPException(
            status_code=503,
            detail="Rate limited",
            headers={"Retry-After": str(int(left) + 1)},
        )
    if not _slots.acquire(timeout=30):
        raise HTTPException(status_code=503, detail="Busy", headers={"Retry-After": "5"})
    started = time.time()
    try:
        reap_stale_browsers(ATTEMPT_SECONDS + 15)
        session = open_session(payload.session_id)
        result = run_attempt(session, payload.url, parse_html=parse_cardmarket_html)
    finally:
        _slots.release()
    if result.get("outcome") == "rate_limited":
        with _cooldown_lock:
            _cooldown_until = time.time() + COOLDOWN_SECONDS
        raise HTTPException(
            status_code=503,
            detail="Rate limited",
            headers={"Retry-After": str(int(COOLDOWN_SECONDS))},
        )
    log.info(
        json.dumps(
            {
                "url": payload.url,
                "outcome": result.get("outcome"),
                "bytes": result.get("bytes"),
                "elapsed_ms": result.get("elapsed_ms"),
                "session_id": payload.session_id,
                "country": os.environ.get("PROXY_COUNTRY", ""),
                "wait_ms": int((time.time() - started) * 1000),
            },
            ensure_ascii=False,
        )
    )
    return result
