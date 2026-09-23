from datetime import datetime, timedelta, timezone

import httpx

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
from app.config import get_settings
from app.db import connect, init_catalog

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


def _stamp(minutes: int) -> str:
    moment = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minutes)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


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


def test_free_helpers_skip_proxy_jobs_and_bad_tokens_fail(tmp_path):
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
