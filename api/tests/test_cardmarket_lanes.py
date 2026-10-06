"""Paid reads stay inside the budget, and interactive jobs go first."""

import time

import httpx

from app.cardmarket import datetime_now
from app.cardmarket_budget import release_attempt, reserve_attempt, usage_today
from app.cardmarket_queue import QueueError, claim_proxy_job, enqueue_job
from app.cardmarket_scraper import ScraperWorker, classify_503
from app.config import get_settings
from app.db import connect, init_catalog


def _catalog(tmp_path):
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    return conn


PRODUCT = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Pikachu"


def test_busy_reply_does_not_spend_a_page(tmp_path):
    conn = _catalog(tmp_path)
    enqueue_job(conn, PRODUCT, tier="proxy")
    job = claim_proxy_job(conn)
    worker = ScraperWorker(get_settings())

    def busy(url):
        request = httpx.Request("POST", "http://scraper/scrape")
        response = httpx.Response(
            503, headers={"retry-after": "5"}, json={"detail": "Busy"}, request=request
        )
        raise httpx.HTTPStatusError("busy", request=request, response=response)

    worker._scrape = busy
    worker._handle(conn, job)
    pages, used = usage_today(conn)
    assert pages == 0
    assert used == 0
    row = conn.execute("SELECT state, outcome FROM cardmarket_scrapes").fetchone()
    assert row["state"] == "released"
    assert row["outcome"] == "busy"
    assert worker._sticky.session_id


def test_the_page_after_the_daily_cap_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "scraper_daily_pages", 1)
    monkeypatch.setattr(get_settings(), "scraper_daily_mb", 50)
    conn = _catalog(tmp_path)
    first = reserve_attempt(conn, sample=PRODUCT, session_id="proxy", ip="")
    release_attempt(conn, first, "busy")
    second = reserve_attempt(conn, sample=PRODUCT + "-2", session_id="proxy", ip="")
    from app.cardmarket_budget import reconcile_attempt

    reconcile_attempt(conn, second, outcome="offers", actual_bytes=100, elapsed_ms=10)
    try:
        reserve_attempt(conn, sample=PRODUCT + "-3", session_id="proxy", ip="")
    except QueueError as exc:
        assert exc.status_code == 429
    else:
        raise AssertionError("cap did not hold")


def test_interactive_jobs_run_before_nightly_ones(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "cardmarket_interactive_start_s", 30)
    conn = _catalog(tmp_path)
    nightly = enqueue_job(conn, PRODUCT, tier="proxy", priority=20)
    interactive = enqueue_job(conn, PRODUCT + "-V2", tier="proxy", priority=0)
    first = claim_proxy_job(conn)
    assert first["id"] == interactive
    second = claim_proxy_job(conn)
    assert second["id"] == nightly


def test_an_expired_interactive_job_is_not_reserved(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "cardmarket_interactive_start_s", 30)
    conn = _catalog(tmp_path)
    job_id = enqueue_job(conn, PRODUCT, tier="proxy", priority=0)
    conn.execute(
        "UPDATE cardmarket_jobs SET deadline_at = ? WHERE id = ?",
        ("2000-01-01T00:00:00Z", job_id),
    )
    conn.commit()
    assert claim_proxy_job(conn) is None
    row = conn.execute("SELECT status, failure_reason FROM cardmarket_jobs WHERE id = ?", (job_id,)).fetchone()
    assert row["status"] == "failed"
    assert row["failure_reason"] == "expired"
    assert usage_today(conn) == (0, 0)


def test_a_long_retry_after_is_a_rate_limit_and_a_short_one_is_busy():
    limited = httpx.Response(503, headers={"retry-after": "900"}, request=httpx.Request("POST", "http://s"))
    busy = httpx.Response(503, headers={"retry-after": "5"}, request=httpx.Request("POST", "http://s"))
    assert classify_503(limited) == "rate_limited"
    assert classify_503(busy) == "busy"


def test_busy_keeps_the_sticky_session(tmp_path):
    conn = _catalog(tmp_path)
    enqueue_job(conn, PRODUCT, tier="proxy")
    job = claim_proxy_job(conn)
    worker = ScraperWorker(get_settings())
    before = worker._sticky.session_id

    def busy(url):
        request = httpx.Request("POST", "http://scraper/scrape")
        response = httpx.Response(503, headers={"retry-after": "5"}, request=request)
        raise httpx.HTTPStatusError("busy", request=request, response=response)

    worker._scrape = busy
    worker._handle(conn, job)
    assert worker._sticky.session_id == before
    assert time.time() > 0
    assert datetime_now()
