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
    immediate_transaction,
    issue_helper_credential,
    prices_payload,
    recover_job,
    release_job,
    renew_claim,
    retry_or_fail_job,
    update_helper_status,
)
from app.db import connect, init_catalog

GENGAR = (
    "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
    "Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102"
)
PIKACHU = (
    "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
    "Pokemon-Trading-Card-Game-Classic-Charizard-Ho-Oh-ex-Deck/Pikachu-CLC008"
)
OFFERS = [{"label": "NM", "amount": 12.5, "currency": "EUR"}]


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
