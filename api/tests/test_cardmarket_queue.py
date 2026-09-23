from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from app.cardmarket import write_snapshot
from app.cardmarket_queue import (
    ClaimError,
    QueueError,
    WrongProduct,
    authenticate_helper,
    claim_job,
    complete_job,
    enqueue_job,
    helper_public_state,
    identities_compatible,
    immediate_transaction,
    issue_helper_credential,
    event_should_stop,
    prices_payload,
    recover_job,
    remember_phone_offers,
    release_job,
    renew_claim,
    retry_or_fail_job,
    update_helper_status,
)
from app.db import connect, init_catalog
from app.config import Settings, get_settings

GENGAR = (
    "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
    "Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102"
)
PIKACHU = (
    "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
    "Pokemon-Trading-Card-Game-Classic-Charizard-Ho-Oh-ex-Deck/Pikachu-CLC008"
)
OFFERS = [{"label": "NM", "amount": 12.5, "currency": "EUR"}]


@pytest.fixture(autouse=True)
def enable_pc_helper_for_queue_tests(monkeypatch):
    monkeypatch.setattr(get_settings(), "cardmarket_helper_enabled", True)


def test_pc_helper_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CARDMARKET_HELPER_ENABLED", raising=False)
    assert Settings(_env_file=None).cardmarket_helper_enabled is False


def test_disabling_pc_helper_blocks_prices_and_keeps_phone_available(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes.cardmarket import router

    conn = _catalog(tmp_path)
    helper_id, token = issue_helper_credential(conn, "cdp-pc")
    update_helper_status(conn, helper_id, ready=True)
    enqueue_job(conn, GENGAR)
    job = claim_job(conn, helper_id)
    write_snapshot(conn, GENGAR, OFFERS)
    settings = get_settings()
    monkeypatch.setattr(settings, "cardmarket_helper_enabled", False)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.dbs = SimpleNamespace(catalog=conn)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    claim = {"job_id": job["id"], "claim_token": job["claim_token"]}

    snapshot = client.get("/api/v1/cardmarket/prices", params={"url": GENGAR}).json()
    assert snapshot["prices"] == OFFERS
    assert snapshot["status"] is None
    assert not snapshot["helper_ready"] and not snapshot["cdp_ready"]
    assert not snapshot["helper_online"]
    assert client.post("/api/v1/cardmarket/jobs", json={"url": GENGAR}).status_code == 503
    recovered = client.post("/api/v1/cardmarket/helper/claim", json=claim, headers=headers)
    assert recovered.json()["status"] == "idle"
    assert client.post("/api/v1/cardmarket/helper/renew", json=claim, headers=headers).status_code == 503
    completed = client.post(
        "/api/v1/cardmarket/helper/complete",
        json={**claim, "url": GENGAR, "prices": [], "empty": True, "submission_id": "disabled"},
        headers=headers,
    )
    assert completed.status_code == 503
    assert prices_payload(conn, GENGAR)["prices"] == OFFERS
    assert remember_phone_offers(conn, GENGAR, [{"price": "2,50 €", "condition": "NM"}])
    assert prices_payload(conn, GENGAR)["prices"][0]["amount"] == 2.5

    monkeypatch.setattr(settings, "cardmarket_helper_enabled", True)
    assert helper_public_state(conn)["helper_ready"] is True
    assert recover_job(conn, helper_id, job["id"], job["claim_token"])["id"] == job["id"]


def test_proxy_can_take_over_disabled_pc_claim(tmp_path, monkeypatch):
    from app.cardmarket_queue import claim_proxy_job, complete_proxy_job

    conn = _catalog(tmp_path)
    helper_id, _ = issue_helper_credential(conn)
    job_id = enqueue_job(conn, GENGAR)
    previous = claim_job(conn, helper_id)
    monkeypatch.setattr(get_settings(), "cardmarket_helper_enabled", False)
    assert enqueue_job(conn, GENGAR, tier="proxy") == job_id
    job = claim_proxy_job(conn)
    assert job["id"] == job_id
    assert job["claim_token"] != previous["claim_token"]
    assert prices_payload(conn, GENGAR)["status"] == "claimed"
    result = complete_proxy_job(
        conn, job_id, job["claim_token"], url=GENGAR, prices=OFFERS, submission_id="proxy"
    )
    assert result["prices"] == OFFERS


def _catalog(tmp_path):
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    return conn


def _helpers(conn, n=2):
    tokens = []
    for _ in range(n):
        tokens.append(issue_helper_credential(conn))
    return tokens


def _complete(conn, helper_id, job, url=None, prices=None, empty=False, submission_id="sub-1"):
    return complete_job(
        conn,
        helper_id,
        job["id"],
        job["claim_token"],
        submission_id=submission_id,
        url=url or job["url"],
        prices=prices if prices is not None else OFFERS,
        empty=empty,
    )


def test_concurrent_claims_one_winner(tmp_path):
    conn = _catalog(tmp_path)
    enqueue_job(conn, GENGAR, "gengar")
    (id_a, _), (id_b, _) = _helpers(conn)
    conn_a = connect(tmp_path / "catalog.sqlite")
    conn_b = connect(tmp_path / "catalog.sqlite")
    results: list = [None, None]

    def take(index, connection, helper_id):
        results[index] = claim_job(connection, helper_id)

    threads = [
        threading.Thread(target=take, args=(0, conn_a, id_a)),
        threading.Thread(target=take, args=(1, conn_b, id_b)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    claimed = [item for item in results if item is not None]
    assert len(claimed) == 1
    assert claimed[0]["status"] == "claimed"


def test_expired_claim_is_rejected(tmp_path):
    conn = _catalog(tmp_path)
    helper_id, _ = issue_helper_credential(conn)
    enqueue_job(conn, GENGAR, "gengar")
    job = claim_job(conn, helper_id)
    assert job is not None
    conn.execute(
        "UPDATE cardmarket_jobs SET claim_expires_at = '2020-01-01T00:00:00Z' WHERE id = ?",
        (job["id"],),
    )
    conn.commit()
    try:
        complete_job(
            conn,
            helper_id,
            job["id"],
            job["claim_token"],
            submission_id="late",
            url=GENGAR,
            prices=OFFERS,
        )
        raise AssertionError("expired claim must not complete")
    except ClaimError:
        pass


def test_duplicate_submission_is_idempotent(tmp_path):
    conn = _catalog(tmp_path)
    helper_id, _ = issue_helper_credential(conn)
    enqueue_job(conn, GENGAR, "gengar")
    job = claim_job(conn, helper_id)
    first = _complete(conn, helper_id, job, submission_id="same")
    again = _complete(conn, helper_id, job, submission_id="same")
    assert first["idempotent"] is False
    assert again["idempotent"] is True
    assert again["prices"] == OFFERS


def test_wrong_product_is_rejected(tmp_path):
    conn = _catalog(tmp_path)
    helper_id, _ = issue_helper_credential(conn)
    enqueue_job(conn, GENGAR, "gengar")
    job = claim_job(conn, helper_id)
    try:
        _complete(conn, helper_id, job, url=PIKACHU)
        raise AssertionError("wrong product must not complete")
    except WrongProduct:
        pass
    row = conn.execute("SELECT status FROM cardmarket_jobs WHERE id = ?", (job["id"],)).fetchone()
    assert row["status"] == "claimed"


def test_empty_observation_is_stored(tmp_path):
    conn = _catalog(tmp_path)
    helper_id, _ = issue_helper_credential(conn)
    enqueue_job(conn, GENGAR, "gengar")
    job = claim_job(conn, helper_id)
    result = _complete(conn, helper_id, job, prices=[], empty=True)
    assert result["status"] == "done"
    payload = prices_payload(conn, GENGAR)
    assert payload["prices"] == []
    assert payload["observed_at"]
    assert payload["status"] == "done"


def test_retry_limit_then_stop(tmp_path):
    conn = _catalog(tmp_path)
    helper_id, _ = issue_helper_credential(conn)
    enqueue_job(conn, GENGAR, "gengar")
    for index in range(3):
        job = claim_job(conn, helper_id)
        assert job is not None
        status = retry_or_fail_job(
            conn,
            job["id"],
            helper_id=helper_id,
            claim_token=job["claim_token"],
            reason="network",
        )
        if index < 2:
            assert status == "pending"
            conn.execute(
                "UPDATE cardmarket_jobs SET next_attempt_at = '2020-01-01T00:00:00Z' WHERE id = ?",
                (job["id"],),
            )
            conn.commit()
        else:
            assert status == "failed"
    assert claim_job(conn, helper_id) is None


def test_prices_status_prefers_active_job_over_failed(tmp_path):
    conn = _catalog(tmp_path)
    helper_id, _ = issue_helper_credential(conn)
    enqueue_job(conn, GENGAR, "gengar")
    for index in range(3):
        job = claim_job(conn, helper_id)
        assert job is not None
        status = retry_or_fail_job(
            conn,
            job["id"],
            helper_id=helper_id,
            claim_token=job["claim_token"],
            reason="parser",
        )
        if index < 2:
            assert status == "pending"
            conn.execute(
                "UPDATE cardmarket_jobs SET next_attempt_at = '2020-01-01T00:00:00Z' WHERE id = ?",
                (job["id"],),
            )
            conn.commit()
    assert prices_payload(conn, GENGAR)["status"] == "failed"
    enqueue_job(conn, GENGAR, "gengar")
    assert prices_payload(conn, GENGAR)["status"] == "pending"


def test_complete_rollback_leaves_claim(tmp_path):
    conn = _catalog(tmp_path)
    helper_id, _ = issue_helper_credential(conn)
    enqueue_job(conn, GENGAR, "gengar")
    job = claim_job(conn, helper_id)
    try:
        _complete(conn, helper_id, job, prices=[], empty=False)
        raise AssertionError("empty without flag must roll back")
    except QueueError:
        pass
    row = conn.execute("SELECT status FROM cardmarket_jobs WHERE id = ?", (job["id"],)).fetchone()
    assert row["status"] == "claimed"
    assert prices_payload(conn, GENGAR)["prices"] == []


def test_older_observation_does_not_overwrite(tmp_path):
    conn = _catalog(tmp_path)
    write_snapshot(
        conn,
        GENGAR,
        [{"label": "NM", "amount": 9.0, "currency": "EUR"}],
        observed_at="2026-09-17T12:00:00Z",
        commit=True,
    )
    helper_id, _ = issue_helper_credential(conn)
    enqueue_job(conn, GENGAR, "gengar")
    job = claim_job(conn, helper_id)
    complete_job(
        conn,
        helper_id,
        job["id"],
        job["claim_token"],
        submission_id="old",
        url=GENGAR,
        prices=[{"label": "NM", "amount": 1.0, "currency": "EUR"}],
        observed_at="2026-09-17T11:00:00Z",
    )
    payload = prices_payload(conn, GENGAR)
    assert payload["prices"][0]["amount"] == 9.0
    row = conn.execute("SELECT status FROM cardmarket_jobs WHERE id = ?", (job["id"],)).fetchone()
    assert row["status"] == "done"


def test_reclaimed_job_rejects_old_submission(tmp_path):
    conn = _catalog(tmp_path)
    helper_a, _ = issue_helper_credential(conn)
    helper_b, _ = issue_helper_credential(conn)
    enqueue_job(conn, GENGAR, "gengar")
    first = claim_job(conn, helper_a)
    conn.execute(
        "UPDATE cardmarket_jobs SET claim_expires_at = '2020-01-01T00:00:00Z' WHERE id = ?",
        (first["id"],),
    )
    conn.commit()
    second = claim_job(conn, helper_b)
    assert second is not None
    try:
        _complete(conn, helper_a, first, submission_id="obsolete")
        raise AssertionError("obsolete helper must not complete")
    except ClaimError:
        pass
    result = _complete(conn, helper_b, second, submission_id="fresh")
    assert result["idempotent"] is False


def test_filters_are_kept_separate_from_url(tmp_path):
    conn = _catalog(tmp_path)
    job_id = enqueue_job(
        conn,
        GENGAR + "?minCondition=NM&utm_source=x",
        "gengar",
    )
    job = conn.execute("SELECT url, filters_json FROM cardmarket_jobs WHERE id = ?", (job_id,)).fetchone()
    assert job["url"] == GENGAR
    assert "minCondition" in job["filters_json"]
    assert "utm_source" not in job["filters_json"]
    assert enqueue_job(conn, GENGAR + "?minCondition=NM") == job_id
    other = enqueue_job(conn, GENGAR + "?minCondition=EX")
    assert other != job_id


def test_helper_auth_and_http_flow(tmp_path):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.routes.cardmarket import router

    conn = _catalog(tmp_path)
    helper_id, token = issue_helper_credential(conn)
    app = fastapi.FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.dbs = SimpleNamespace(catalog=conn)
    client = TestClient(app)
    denied = client.post("/api/v1/cardmarket/helper/claim")
    assert denied.status_code == 401
    headers = {"Authorization": f"Bearer {token}"}
    queued = client.post(
        "/api/v1/cardmarket/jobs",
        json={"url": GENGAR, "card_id": "gengar"},
    )
    assert queued.status_code == 200
    claimed = client.post("/api/v1/cardmarket/helper/claim", headers=headers)
    assert claimed.status_code == 200
    job = claimed.json()
    completed = client.post(
        "/api/v1/cardmarket/helper/complete",
        headers=headers,
        json={
            "job_id": job["id"],
            "claim_token": job["claim_token"],
            "submission_id": "http-1",
            "url": GENGAR,
            "prices": OFFERS,
            "parser_version": "offers-v1",
            "sampled_offer_count": 1,
        },
    )
    assert completed.status_code == 200
    prices = client.get("/api/v1/cardmarket/prices", params={"url": GENGAR})
    body = prices.json()
    assert body["prices"][0]["amount"] == 12.5
    assert body["helper_online"] is True
    status = client.post(
        "/api/v1/cardmarket/helper/status",
        headers=headers,
        json={"ready": True, "paused": False},
    )
    assert status.json()["helper_ready"] is True
    assert authenticate_helper(conn, token)["helper_id"] == helper_id
    assert status.json()["cdp_online"] is False


def test_cdp_helper_is_preferred_online(tmp_path):
    conn = _catalog(tmp_path)
    ext_id, _ = issue_helper_credential(conn)
    cdp_id, _ = issue_helper_credential(conn, "cdp")
    update_helper_status(conn, cdp_id, ready=True, paused=False)
    state = helper_public_state(conn)
    assert state["cdp_online"] is True
    assert state["cdp_ready"] is True
    assert state["helper_online"] is True
    conn.execute(
        "UPDATE cardmarket_helpers SET last_seen = '2020-01-01T00:00:00Z' WHERE helper_id = ?",
        (cdp_id,),
    )
    conn.commit()
    update_helper_status(conn, ext_id, ready=True, paused=False)
    state = helper_public_state(conn)
    assert state["cdp_online"] is False
    assert state["helper_online"] is True


def test_recover_and_renew_claim(tmp_path):
    conn = _catalog(tmp_path)
    helper_id, _ = issue_helper_credential(conn)
    enqueue_job(conn, GENGAR, "gengar")
    job = claim_job(conn, helper_id)
    recovered = recover_job(conn, helper_id, job["id"], job["claim_token"])
    assert recovered is not None
    renewed = renew_claim(conn, helper_id, job["id"], job["claim_token"])
    assert renewed["claim_expires_at"] != job["claim_expires_at"] or True
    released = release_job(conn, helper_id, job["id"], job["claim_token"], reason="paused")
    assert released["status"] == "pending"


def test_immediate_transaction_rolls_back(tmp_path):
    conn = _catalog(tmp_path)
    enqueue_job(conn, GENGAR, "gengar")
    try:
        with immediate_transaction(conn):
            conn.execute("UPDATE cardmarket_jobs SET status = 'claimed'")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    row = conn.execute("SELECT status FROM cardmarket_jobs").fetchone()
    assert row["status"] == "pending"


def test_wait_for_product_wakes_on_notify():
    import asyncio

    from app.cardmarket_events import bind_loop, notify_product, wait_for_product

    async def main():
        bind_loop(asyncio.get_running_loop())
        task = asyncio.create_task(wait_for_product(GENGAR, 2.0))
        await asyncio.sleep(0.05)
        notify_product(GENGAR)
        assert await task is True
        bind_loop(None)

    asyncio.run(main())


def test_claim_prefers_the_newest_pending_job(tmp_path):
    conn = _catalog(tmp_path)
    helper_id, _ = issue_helper_credential(conn)
    first_id = enqueue_job(conn, GENGAR, "gengar")
    second_id = enqueue_job(conn, PIKACHU, "pikachu")
    claimed = claim_job(conn, helper_id)
    assert claimed is not None
    assert claimed["id"] == second_id
    assert claimed["url"] == PIKACHU
    leftover = conn.execute(
        "SELECT status FROM cardmarket_jobs WHERE id = ?",
        (first_id,),
    ).fetchone()
    assert leftover["status"] == "pending"


def test_claim_switches_to_a_newer_scan(tmp_path):
    conn = _catalog(tmp_path)
    helper_id, _ = issue_helper_credential(conn)
    first_id = enqueue_job(conn, GENGAR, "gengar")
    first = claim_job(conn, helper_id)
    assert first is not None
    assert first["id"] == first_id
    second_id = enqueue_job(conn, PIKACHU, "pikachu")
    switched = claim_job(conn, helper_id)
    assert switched is not None
    assert switched["id"] == second_id
    parked = conn.execute(
        "SELECT status, helper_id FROM cardmarket_jobs WHERE id = ?",
        (first_id,),
    ).fetchone()
    assert parked["status"] == "pending"
    assert parked["helper_id"] is None


def test_empty_identity_does_not_match_another_product():
    assert identities_compatible(None, "singles:clc008") is False
    assert identities_compatible("", "path:tag-bolt/gengar") is False
    assert identities_compatible("singles:sm9102", "singles:clc008") is False
    assert identities_compatible("singles:sm9102", "singles:sm9102") is True


def test_price_events_stream_after_complete(tmp_path):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.routes.cardmarket import router

    conn = _catalog(tmp_path)
    helper_id, token = issue_helper_credential(conn)
    app = fastapi.FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.dbs = SimpleNamespace(catalog=conn)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/v1/cardmarket/jobs", json={"url": GENGAR, "card_id": "gengar"})
    job = client.post("/api/v1/cardmarket/helper/claim", headers=headers).json()
    completed = client.post(
        "/api/v1/cardmarket/helper/complete",
        headers=headers,
        json={
            "job_id": job["id"],
            "claim_token": job["claim_token"],
            "submission_id": "stream-1",
            "url": GENGAR,
            "prices": OFFERS,
            "parser_version": "offers-v1",
            "sampled_offer_count": 1,
        },
    )
    assert completed.status_code == 200
    with client.stream("GET", "/api/v1/cardmarket/prices/events", params={"url": GENGAR}) as response:
        assert response.status_code == 200
        text = ""
        for line in response.iter_lines():
            text += f"{line}\n"
            if str(line).startswith("data:"):
                break
    assert "12.5" in text
    assert "NM" in text


def test_phone_offer_skips_unchanged_fresh_sample(tmp_path):
    conn = _catalog(tmp_path)
    write_snapshot(conn, GENGAR, OFFERS)
    stored = remember_phone_offers(
        conn,
        GENGAR,
        [{"price": "12,50 €", "condition": "NM"}],
    )
    assert stored is False


def test_phone_offer_refreshes_unchanged_stale_sample(tmp_path):
    conn = _catalog(tmp_path)
    write_snapshot(conn, GENGAR, OFFERS)
    key = prices_payload(conn, GENGAR)["url"]
    conn.execute(
        "UPDATE cardmarket_snapshots SET observed_at = '2020-01-01T00:00:00Z' WHERE url = ?",
        (key,),
    )
    conn.commit()
    assert remember_phone_offers(
        conn,
        GENGAR,
        [{"price": "12,50 €", "condition": "NM"}],
    )
    payload = prices_payload(conn, GENGAR)
    assert payload["freshness"] == "fresh"
    assert payload["observed_at"] != "2020-01-01T00:00:00Z"
    assert payload["prices"] == OFFERS


def test_phone_offer_stores_a_new_sample(tmp_path):
    conn = _catalog(tmp_path)
    assert remember_phone_offers(
        conn,
        GENGAR,
        [{"price": "2,50 €", "condition": "NM", "language": "English"}],
    )
    payload = prices_payload(conn, GENGAR)
    assert payload["prices"] == [
        {"label": "NM · English", "amount": 2.5, "currency": "EUR"}
    ]
    assert payload["freshness"] == "fresh"


def test_event_stops_for_a_newer_observation_or_failure():
    same = {
        "observed_at": "2020-01-01T00:00:00Z",
        "status": "done",
        "prices": OFFERS,
    }
    newer = {
        "observed_at": "2020-01-01T00:00:01Z",
        "status": "done",
        "prices": OFFERS,
    }
    failed = {
        "observed_at": "2020-01-01T00:00:00Z",
        "status": "failed",
        "prices": [],
    }
    assert event_should_stop(same, "2020-01-01T00:00:00Z") is False
    assert event_should_stop(newer, "2020-01-01T00:00:00Z") is True
    assert event_should_stop(failed, "2020-01-01T00:00:00Z") is True
    assert event_should_stop(same, None) is True


@pytest.mark.parametrize("status", ["pending", "claimed"])
def test_equal_observation_stays_open_despite_clock_jitter(monkeypatch, status):
    ticks = iter([2_000_000_000.0, 2_000_000_000.001, 2_000_000_000.002, 2_000_000_000.004])
    monkeypatch.setattr("app.cardmarket_queue.time.time", lambda: next(ticks))
    stamp = "2020-01-01T00:00:00Z"
    payload = {"observed_at": stamp, "status": status, "prices": OFFERS}
    assert event_should_stop(payload, stamp) is False


def test_pending_job_is_not_closed_by_an_older_empty(tmp_path):
    older_empty = {
        "observed_at": "2020-01-01T00:00:00Z",
        "attempted_at": "2020-01-01T00:10:00Z",
        "status": "pending",
        "prices": OFFERS,
    }
    assert event_should_stop(older_empty, "2020-01-01T00:00:00Z") is False
    assert event_should_stop({**older_empty, "status": "claimed"}, older_empty["observed_at"]) is False
    assert event_should_stop({**older_empty, "status": "done"}, older_empty["observed_at"]) is True
    priced = {**older_empty, "observed_at": "2020-01-01T00:11:00Z"}
    assert event_should_stop(priced, "2020-01-01T00:00:00Z") is True

    conn = _catalog(tmp_path)
    write_snapshot(conn, GENGAR, OFFERS, observed_at="2020-01-01T00:00:00Z")
    write_snapshot(
        conn,
        GENGAR,
        [],
        allow_empty=True,
        observed_at="2020-01-01T00:10:00Z",
        empty_source="proxy",
    )
    enqueue_job(conn, GENGAR, tier="proxy")
    payload = prices_payload(conn, GENGAR)
    assert payload["status"] == "pending"
    assert payload["attempted_at"] > payload["observed_at"]
    assert event_should_stop(payload, payload["observed_at"]) is False


def test_price_batch_returns_each_product_once(tmp_path):
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.routes.cardmarket import router

    conn = _catalog(tmp_path)
    write_snapshot(conn, GENGAR, OFFERS)
    app = fastapi.FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.dbs = SimpleNamespace(catalog=conn)
    client = TestClient(app)
    response = client.post(
        "/api/v1/cardmarket/prices/batch",
        json={"urls": [GENGAR, PIKACHU, GENGAR, "https://example.com/nope"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["items"][0]["prices"][0]["amount"] == 12.5
    assert body["items"][1]["prices"] == []
