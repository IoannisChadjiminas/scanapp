from datetime import datetime, timedelta, timezone

import httpx
import pytest
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cardmarket import datetime_now, sample_key, write_snapshot
from app.cardmarket_budget import (
    note_scraper_health,
    record_phone_challenge,
    reserve_attempt,
    usage_today,
)
from app.cardmarket_queue import (
    PROXY_WORKER_ID,
    ClaimError,
    QueueError,
    claim_job,
    claim_proxy_job,
    complete_proxy_job,
    enqueue_job,
    fail_proxy_job,
    issue_helper_credential,
    prices_payload,
)
from app.cardmarket_scraper import ScraperWorker
from app.config import Settings, get_settings
from app.db import connect, init_catalog, init_results

PRODUCT = (
    "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
    "Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102"
)
ENGLISH = f"{PRODUCT}?language=1"
GERMAN = f"{PRODUCT}?language=3"
OFFERS = [{"label": "NM · English", "amount": 4.5, "currency": "EUR"}]


def _catalog(tmp_path):
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    return conn


def test_initial_scraper_health_failure_is_logged_once(monkeypatch, caplog):
    import logging

    worker = ScraperWorker(Settings(scraper_url="http://scraper:8000"))
    def fail(*args, **kwargs):
        raise httpx.ConnectError("secret-must-not-be-logged")
    monkeypatch.setattr("app.cardmarket_scraper.httpx.get", fail)
    note_scraper_health(False, 0)
    with caplog.at_level(logging.INFO, logger="cardmarket.scraper"):
        worker._ping()
        worker._ping()
    assert caplog.text.count("scraper health state=ConnectError") == 1
    assert "secret-must-not-be-logged" not in caplog.text


def _stamp(minutes: int) -> str:
    moment = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minutes)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def direct_scraper(tmp_path, monkeypatch):
    from app.routes.cardmarket import router

    settings = get_settings()
    for key, value in {
        "cardmarket_webview_enabled": False,
        "scraper_enabled": True,
        "scraper_url": "http://scraper",
        "scraper_api_key": "test-key",
        "scraper_daily_pages": 50,
        "scraper_daily_mb": 50,
        "scraper_session_hourly": 10,
        "scraper_ip_hourly": 20,
    }.items():
        monkeypatch.setattr(settings, key, value)
    catalog = _catalog(tmp_path)
    results = connect(tmp_path / "results.sqlite")
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('session', ?, ?)", (datetime_now(), datetime_now()))
    results.commit()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.settings = settings
    app.state.dbs = SimpleNamespace(catalog=catalog, results=results)
    note_scraper_health(True, 0)
    with TestClient(app) as client:
        client.cookies.set(settings.session_cookie, "session")
        yield client, catalog, settings
    note_scraper_health(False, 0)
    catalog.close()
    results.close()


def test_webviews_default_on_and_api_reports_disabled_policy(direct_scraper, monkeypatch):
    client, catalog, settings = direct_scraper
    monkeypatch.delenv("CARDMARKET_WEBVIEW_ENABLED", raising=False)
    assert Settings(_env_file=None).cardmarket_webview_enabled is True
    assert client.get("/api/v1/cardmarket/prices", params={"url": ENGLISH}).json()["webview_enabled"] is False
    batch = client.post("/api/v1/cardmarket/prices/batch", json={"urls": [ENGLISH]}).json()
    assert batch["webview_enabled"] is False
    assert batch["items"][0]["webview_enabled"] is False
    accepted = client.post("/api/v1/cardmarket/escalations", json={"url": ENGLISH})
    assert accepted.status_code == 200
    job = claim_proxy_job(catalog)
    assert job["id"] == accepted.json()["id"]
    monkeypatch.setattr(settings, "cardmarket_webview_enabled", True)
    rejected = client.post("/api/v1/cardmarket/escalations", json={"url": GERMAN})
    assert rejected.status_code == 403
    record_phone_challenge(catalog, session_id="session", ip="testclient", url=GERMAN)
    assert client.post("/api/v1/cardmarket/escalations", json={"url": GERMAN}).status_code == 200


@pytest.mark.parametrize("restriction, expected", [
    ("session", 401), ("enabled", 503), ("budget", 429), ("hourly", 429), ("cooldown", 429),
])
def test_direct_scraper_keeps_existing_limits(direct_scraper, monkeypatch, restriction, expected):
    client, catalog, settings = direct_scraper
    if restriction == "session":
        client.cookies.clear()
    elif restriction == "enabled":
        monkeypatch.setattr(settings, "scraper_enabled", False)
    elif restriction == "budget":
        monkeypatch.setattr(settings, "scraper_daily_pages", 0)
    elif restriction == "hourly":
        monkeypatch.setattr(settings, "scraper_session_hourly", 0)
    else:
        from app.cardmarket_budget import reconcile_attempt
        reservation = reserve_attempt(catalog, sample=sample_key(ENGLISH), session_id="session", ip="testclient")
        reconcile_attempt(catalog, reservation, outcome="timeout", actual_bytes=0, elapsed_ms=1)
    response = client.post("/api/v1/cardmarket/escalations", json={"url": ENGLISH})
    assert response.status_code == expected
    assert claim_proxy_job(catalog) is None


def test_filtered_samples_do_not_overwrite_each_other(tmp_path):
    conn = _catalog(tmp_path)
    write_snapshot(conn, ENGLISH, OFFERS, observed_at=_stamp(0))
    write_snapshot(
        conn,
        GERMAN,
        [{"label": "NM · German", "amount": 9, "currency": "EUR"}],
        observed_at=_stamp(1),
    )
    english = prices_payload(conn, ENGLISH)
    german = prices_payload(conn, GERMAN)
    bare = prices_payload(conn, PRODUCT)
    assert english["url"] == sample_key(ENGLISH)
    assert english["prices"][0]["amount"] == 4.5
    assert german["prices"][0]["amount"] == 9
    assert bare["prices"] == []
    assert english["url"] != german["url"]


def test_one_empty_keeps_the_last_price_and_two_confirm_unlisted(tmp_path):
    conn = _catalog(tmp_path)
    write_snapshot(conn, ENGLISH, OFFERS, observed_at=_stamp(0))
    write_snapshot(conn, ENGLISH, [], allow_empty=True, observed_at=_stamp(20), empty_source="proxy")
    kept = prices_payload(conn, ENGLISH)
    assert kept["prices"][0]["amount"] == 4.5
    assert kept["unlisted"] is False
    write_snapshot(conn, ENGLISH, [], allow_empty=True, observed_at=_stamp(40), empty_source="proxy")
    cleared = prices_payload(conn, ENGLISH)
    assert cleared["unlisted"] is True
    assert cleared["prices"] == []


def test_free_helpers_skip_proxy_jobs_and_bad_tokens_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "cardmarket_helper_enabled", True)
    conn = _catalog(tmp_path)
    helper_id, _ = issue_helper_credential(conn)
    enqueue_job(conn, ENGLISH, tier="proxy")
    assert claim_job(conn, helper_id) is None
    job = claim_proxy_job(conn, PROXY_WORKER_ID)
    assert job is not None
    assert job["filters"]["language"] == "1"
    try:
        complete_proxy_job(
            conn,
            job["id"],
            "wrong-token",
            url=ENGLISH,
            prices=OFFERS,
            submission_id="one",
        )
    except ClaimError:
        pass
    else:
        raise AssertionError("wrong claim token was accepted")
    conn.execute(
        "UPDATE cardmarket_jobs SET claim_expires_at = '2020-01-01T00:00:00Z' WHERE id = ?",
        (job["id"],),
    )
    conn.commit()
    again = claim_proxy_job(conn, PROXY_WORKER_ID)
    assert again is not None
    assert again["id"] == job["id"]
    fail_proxy_job(conn, again["id"], again["claim_token"], "challenge", terminal=True)
    assert prices_payload(conn, ENGLISH)["status"] == "failed"


def test_completed_submission_replays_the_filtered_sample(tmp_path):
    conn = _catalog(tmp_path)
    write_snapshot(
        conn,
        PRODUCT,
        [{"label": "NM", "amount": 99, "currency": "EUR"}],
        observed_at=_stamp(0),
    )
    enqueue_job(conn, ENGLISH, tier="proxy")
    job = claim_proxy_job(conn, PROXY_WORKER_ID)
    first = complete_proxy_job(
        conn,
        job["id"],
        job["claim_token"],
        url=ENGLISH,
        prices=OFFERS,
        submission_id="same",
        sampled_offer_count=1,
    )
    again = complete_proxy_job(
        conn,
        job["id"],
        job["claim_token"],
        url=ENGLISH,
        prices=[{"label": "NM", "amount": 99, "currency": "EUR"}],
        submission_id="same",
        sampled_offer_count=1,
    )
    assert first["idempotent"] is False
    assert again["idempotent"] is True
    assert again["prices"][0]["amount"] == 4.5
    assert again["url"] == sample_key(ENGLISH)


def test_cooldown_releases_without_another_paid_page(tmp_path):
    conn = _catalog(tmp_path)
    note_scraper_health(False, 0)
    try:
        enqueue_job(conn, ENGLISH, tier="proxy")
        job = claim_proxy_job(conn, PROXY_WORKER_ID)
        worker = ScraperWorker(get_settings())
        calls = {"n": 0}

        def blocked(url):
            calls["n"] += 1
            request = httpx.Request("POST", "http://scraper/scrape")
            response = httpx.Response(503, headers={"retry-after": "900"}, request=request)
            raise httpx.HTTPStatusError("cooling", request=request, response=response)

        worker._scrape = blocked
        worker._handle(conn, job)
        assert calls["n"] == 1
        row = conn.execute(
            "SELECT status, attempts, next_attempt_at FROM cardmarket_jobs WHERE id = ?",
            (job["id"],),
        ).fetchone()
        assert row["status"] == "pending"
        assert int(row["attempts"] or 0) == 0
        assert row["next_attempt_at"] > datetime_now()
        assert claim_proxy_job(conn, PROXY_WORKER_ID) is None
        pages, _used = usage_today(conn)
        assert pages == 1
        scrape = conn.execute(
            "SELECT state, bytes, reserved_bytes FROM cardmarket_scrapes"
        ).fetchone()
        assert scrape["state"] == "used"
        assert scrape["bytes"] == scrape["reserved_bytes"]

        conn.execute(
            "UPDATE cardmarket_jobs SET next_attempt_at = '2020-01-01T00:00:00Z' WHERE id = ?",
            (job["id"],),
        )
        conn.commit()
        again = claim_proxy_job(conn, PROXY_WORKER_ID)
        assert again is not None
        worker._handle(conn, again)
        assert calls["n"] == 1
        assert usage_today(conn)[0] == 1
    finally:
        note_scraper_health(False, 0)


def test_budget_reservation_is_atomic(tmp_path, monkeypatch):
    conn = _catalog(tmp_path)
    monkeypatch.setenv("SCRAPER_DAILY_PAGES", "1")
    monkeypatch.setenv("SCRAPER_DAILY_MB", "1")
    from app.config import get_settings

    get_settings.cache_clear()
    first = reserve_attempt(conn, sample=sample_key(ENGLISH), session_id="s", ip="1.1.1.1")
    assert first
    try:
        reserve_attempt(conn, sample=sample_key(GERMAN), session_id="s", ip="1.1.1.1")
    except QueueError as exc:
        assert exc.status_code == 429
    else:
        raise AssertionError("budget allowed a second page")
    record_phone_challenge(conn, session_id="s", ip="1.1.1.1", url=ENGLISH)
    get_settings.cache_clear()
