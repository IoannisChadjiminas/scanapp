"""Scan price settings stay off until the server turns a paid read on."""

from app.cardmarket import write_snapshot
from app.cardmarket_queue import (
    claim_proxy_job,
    enqueue_job,
    remember_phone_offers,
    schedule_scan_parallel_read,
)
from app.config import Settings, get_settings
from app.db import connect, init_catalog
from app.routes.health import scan_price_config

PRODUCT = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Pikachu"


def _catalog(tmp_path):
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    return conn


def test_config_reports_the_safe_defaults():
    body = scan_price_config(Settings())
    assert body.scan_prices.server_read.mode == "fallback"
    assert body.scan_prices.server_read.daily_pages == 0
    assert body.scan_prices.candidate_reads == 2
    assert body.scan_prices.warm_reader is True
    assert body.price_fresh_minutes >= 1


def test_parallel_reads_stay_queued_until_the_delay(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "scan_price_server_read", "parallel")
    monkeypatch.setattr(settings, "scan_price_server_read_daily_pages", 10)
    monkeypatch.setattr(settings, "scan_price_server_read_delay_ms", 30_000)
    conn = _catalog(tmp_path)
    job_id = schedule_scan_parallel_read(conn, status="matched", url=PRODUCT)
    assert job_id
    assert claim_proxy_job(conn) is None
    row = conn.execute(
        "SELECT job_source, status FROM cardmarket_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    assert row["job_source"] == "scan-parallel"
    assert row["status"] == "pending"


def test_a_phone_result_cancels_a_read_that_has_not_started(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "scan_price_server_read", "parallel")
    monkeypatch.setattr(settings, "scan_price_server_read_daily_pages", 10)
    monkeypatch.setattr(settings, "scan_price_server_read_delay_ms", 30_000)
    conn = _catalog(tmp_path)
    schedule_scan_parallel_read(conn, status="matched", url=PRODUCT)
    assert remember_phone_offers(
        conn,
        PRODUCT,
        [{"price": "1,00 €", "seller": "Ada", "condition": "NM"}],
    )
    row = conn.execute("SELECT status, failure_reason FROM cardmarket_jobs").fetchone()
    assert row["status"] == "failed"
    assert row["failure_reason"] == "phone-first"


def test_uncertain_scans_and_a_zero_limit_do_not_queue(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "scan_price_server_read", "parallel")
    monkeypatch.setattr(settings, "scan_price_server_read_daily_pages", 10)
    conn = _catalog(tmp_path)
    assert schedule_scan_parallel_read(conn, status="printing_ambiguous", url=PRODUCT) is None
    monkeypatch.setattr(settings, "scan_price_server_read_daily_pages", 0)
    assert schedule_scan_parallel_read(conn, status="matched", url=PRODUCT) is None
    monkeypatch.setattr(settings, "scan_price_server_read", "fallback")
    monkeypatch.setattr(settings, "scan_price_server_read_daily_pages", 10)
    assert schedule_scan_parallel_read(conn, status="matched", url=PRODUCT) is None


def test_a_fresh_stored_price_is_not_read_again(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "scan_price_server_read", "parallel")
    monkeypatch.setattr(settings, "scan_price_server_read_daily_pages", 10)
    conn = _catalog(tmp_path)
    write_snapshot(
        conn,
        PRODUCT,
        [{"label": "From", "amount": 1.5, "currency": "EUR"}],
    )
    assert schedule_scan_parallel_read(conn, status="matched", url=PRODUCT) is None
    enqueue_job(conn, PRODUCT, tier="proxy", priority=0)
    assert claim_proxy_job(conn) is not None
