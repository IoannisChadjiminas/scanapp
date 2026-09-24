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
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
API = HERE.parent / "api"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(API))

from allow import cardmarket_product  # noqa: E402
from browser import ATTEMPT_SECONDS, NET_LOG, ChromeSession, reap_stale_browsers, run_attempt  # noqa: E402
from proxy import proxy_direct, proxy_exit, proxy_server  # noqa: E402
from app.cardmarket_html import parse_cardmarket_html  # noqa: E402

log = logging.getLogger("scraper")
logging.basicConfig(level=logging.INFO, format="%(message)s")


class _SkipHealthAccess(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            path = str(record.args[2]).split("?", 1)[0]
            return path != "/health"
        return "GET /health " not in record.getMessage()


def _quiet_health_access() -> None:
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, _SkipHealthAccess) for item in access.filters):
        access.addFilter(_SkipHealthAccess())


_quiet_health_access()

API_KEY = os.environ.get("SCRAPER_API_KEY", "")
MAX_BROWSERS = max(1, int(os.environ.get("MAX_BROWSERS", "1")))
COOLDOWN_SECONDS = float(os.environ.get("SCRAPER_RATE_LIMIT_S", "900"))
# Costs one extra paid page load per attempt; leave off outside diagnosis.
DIRECT_PROBE = os.environ.get("SCRAPER_DIRECT_PROBE", "").strip().lower() in {"1", "true", "yes"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    _quiet_health_access()
    log.info(
        "scraper config api_key_configured=%s proxy_host_configured=%s "
        "proxy_user_configured=%s proxy_password_configured=%s max_browsers=%s deadline_s=%s "
        "direct_probe=%s net_log=%s",
        bool(API_KEY), bool(os.environ.get("PROXY_HOST", "").strip()),
        bool(os.environ.get("PROXY_USER", "").strip()), bool(os.environ.get("PROXY_PASS")),
        MAX_BROWSERS, ATTEMPT_SECONDS, DIRECT_PROBE, NET_LOG,
    )
    yield


app = FastAPI(title="Cardmarket scraper", docs_url=None, redoc_url=None, lifespan=lifespan)
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


def log_proxy_exit(session_id: str, proxy: str | None) -> None:
    if not proxy:
        return
    started = time.time()
    try:
        exit_info = proxy_exit(proxy)
    except Exception as exc:
        log.info(
            "proxy exit failed session=%s error=%s elapsed_ms=%s",
            session_id, type(exc).__name__, int((time.time() - started) * 1000),
        )
        return
    log.info(
        "proxy exit session=%s ip=%s country=%s org=%s elapsed_ms=%s",
        session_id, exit_info["ip"], exit_info["country"], exit_info["org"],
        int((time.time() - started) * 1000),
    )


def log_chrome_net(session_id: str, session: object) -> None:
    summary = getattr(session, "net_summary", None)
    if summary is None:
        return
    log.info(
        "chrome net session=%s %s",
        session_id,
        json.dumps(summary, ensure_ascii=False, sort_keys=True) if summary else "no cardmarket or cloudflare traffic",
    )


def log_cardmarket_direct(session_id: str, proxy: str | None, url: str) -> None:
    if not DIRECT_PROBE or not proxy:
        return
    started = time.time()
    try:
        page = proxy_direct(proxy, url)
    except Exception as exc:
        log.info(
            "cardmarket direct failed session=%s error=%s elapsed_ms=%s",
            session_id, type(exc).__name__, int((time.time() - started) * 1000),
        )
        return
    log.info(
        "cardmarket direct session=%s status=%s server=%s cf_mitigated=%s bytes=%s title=%r elapsed_ms=%s",
        session_id, page["status"], page["server"], page["cf_mitigated"] or "-",
        page["bytes"], page["title"], int((time.time() - started) * 1000),
    )


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
    log.info("scrape started session=%s", payload.session_id)
    session = None
    try:
        reap_stale_browsers(ATTEMPT_SECONDS + 15)
        session = open_session(payload.session_id)
        log_proxy_exit(payload.session_id, session.proxy)
        log_cardmarket_direct(payload.session_id, session.proxy, payload.url)
        log.info("scrape browser starting session=%s proxy_enabled=%s", payload.session_id, bool(session.proxy))
        result = run_attempt(session, payload.url, parse_html=parse_cardmarket_html)
    except Exception as exc:
        # Exception messages from browser/proxy libraries can contain credentials.
        log.error("scrape failed session=%s error=%s", payload.session_id, type(exc).__name__)
        raise HTTPException(status_code=500, detail="Scrape attempt failed") from None
    finally:
        _slots.release()
        log_chrome_net(payload.session_id, session)
    if result.get("outcome") == "rate_limited":
        log.info("scrape rate_limited session=%s cooldown_s=%s", payload.session_id, COOLDOWN_SECONDS)
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
