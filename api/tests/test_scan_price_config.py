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
    assert body.slab_detection is False


def test_config_lets_the_server_switch_slab_detection_on():
    assert scan_price_config(Settings(app_slab_detection=True)).slab_detection is True


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


def test_config_sends_phone_capture_and_warp_switches():
    body = scan_price_config(Settings(_env_file=None))
    assert body.card_warp is False
    assert body.capture.model_dump() == dict(preset='max', jpeg_quality=95, max_edge=2000, native_codec=False,
                                                live_outline=True, auto_capture=True, native_camera=False, native_camera_android=False, card_anywhere=True)
    body = scan_price_config(Settings(_env_file=None, app_card_warp=True, app_capture_preset='ultraHigh',
                                      app_jpeg_quality=85, app_max_edge=1400, app_native_codec=True,
                                      app_live_outline=True, app_auto_capture=True, app_native_camera=True, native_camera_android=False, card_anywhere=True))
    assert body.card_warp is True
    assert body.capture.model_dump() == dict(preset='ultraHigh', jpeg_quality=85, max_edge=1400, native_codec=True,
                                                live_outline=True, auto_capture=True, native_camera=True, native_camera_android=False, card_anywhere=True)


def test_config_never_sends_an_unknown_preset_or_silly_quality():
    body = scan_price_config(Settings(_env_file=None, app_capture_preset='huge', app_jpeg_quality=5))
    assert body.capture.preset == 'max' and body.capture.jpeg_quality == 50


def test_config_keeps_the_photo_edge_in_a_sensible_range():
    assert scan_price_config(Settings(_env_file=None, app_max_edge=100)).capture.max_edge == 800
    assert scan_price_config(Settings(_env_file=None, app_max_edge=99999)).capture.max_edge == 4000


def test_auto_capture_needs_the_live_outline():
    body = scan_price_config(Settings(_env_file=None, app_live_outline=False, app_auto_capture=True))
    assert body.capture.auto_capture is False


def test_outline_and_auto_capture_can_be_switched_off():
    body = scan_price_config(Settings(_env_file=None, app_auto_capture=False))
    assert (body.capture.live_outline, body.capture.auto_capture) == (True, False)
    body = scan_price_config(Settings(_env_file=None, app_live_outline=False))
    assert (body.capture.live_outline, body.capture.auto_capture) == (False, False)


def test_card_anywhere_can_be_switched_off():
    assert scan_price_config(Settings(_env_file=None)).capture.card_anywhere is True
    assert scan_price_config(Settings(_env_file=None, app_card_anywhere=False)).capture.card_anywhere is False


def test_android_camera_switch_is_separate_from_the_iphone_one():
    off = scan_price_config(Settings(_env_file=None, app_native_camera=True))
    assert off.capture.native_camera is True
    assert off.capture.native_camera_android is False
    on = scan_price_config(Settings(_env_file=None, app_native_camera_android=True))
    assert on.capture.native_camera is False
    assert on.capture.native_camera_android is True
