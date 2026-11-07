"""Early reads for moving cards, spike episodes and condition listings."""

import json
import random
import subprocess
import sys
from pathlib import Path

from app import cardmarket_daily as daily
from app import price_moves
from app.cardmarket import write_snapshot
from app.cardmarket_queue import prices_payload
from app.config import Settings, get_settings
from app.db import connect, init_catalog
from app.price_sources import fresh_window, import_guide, tier_window

PRODUCT = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Pikachu"
NM = f"{PRODUCT}?language=1&minCondition=2"
LP = f"{PRODUCT}?language=1&minCondition=5"
FIRST = f"{PRODUCT}?isFirstEd=Y&language=1&minCondition=2"
SETTINGS = Settings()


def _catalog(tmp_path):
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    conn.execute(
        "INSERT INTO cards (id, provider_id, name, set_id, set_name, collector_number, language,"
        " variants_json, cardmarket_id, cardmarket_url) VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("en:a", "en:a", "Pikachu", "base1", "Base Set", "58", "en", json.dumps({"normal": True}), 100, PRODUCT),
    )
    conn.commit()
    return conn


def _guide(conn, day, *, avg1, avg7, trend=10.0):
    import_guide(conn, {"version": 1, "createdAt": f"{day}T02:00:00+0000", "priceGuides": [
        {"idProduct": 100, "avg": trend, "low": trend, "trend": trend, "avg1": avg1, "avg7": avg7},
        {"idProduct": 101, "trend": 1.0},
    ]})


def _read(conn, url, stamp, trend=10.0):
    write_snapshot(conn, url, [{"label": "Near Mint", "amount": trend, "currency": "EUR"},
                               {"label": "Trend", "amount": trend, "currency": "EUR"}],
                   observed_at=stamp, parser_version="test")


def test_a_move_needs_ten_percent_and_fifty_cents():
    assert price_moves.trend_moved(1.15, 1.0, 10, 0.5) is False
    assert price_moves.trend_moved(11.0, 10.0, 10, 0.5) is True
    assert price_moves.trend_moved(10.9, 10.0, 10, 0.5) is False
    assert price_moves.trend_moved(None, 10.0, 10, 0.5) is False


def test_a_spike_needs_both_ratio_and_euro_floor_and_valid_averages():
    assert price_moves.spike_predicate(3.0, 2.0, 1.5, 1.0) is True
    assert price_moves.spike_predicate(1.5, 1.0, 1.5, 1.0) is False
    assert price_moves.spike_predicate(2.9, 2.0, 1.5, 1.0) is False
    assert price_moves.spike_predicate(None, 2.0, 1.5, 1.0) is None
    assert price_moves.spike_predicate(3.0, 0, 1.5, 1.0) is None


def test_one_spike_read_per_key_and_an_nm_read_leaves_lp_eligible(tmp_path):
    conn = _catalog(tmp_path)
    _read(conn, NM, "2026-11-01T10:00:00Z")
    _read(conn, LP, "2026-11-01T10:00:00Z")
    _guide(conn, "2026-11-03", avg1=30.0, avg7=10.0)
    record = lambda url: daily.snapshot_record(conn, url)  # noqa: E731
    now = "2026-11-03T12:00:00Z"
    assert price_moves.moving(conn, NM, record(NM), SETTINGS, now)
    assert price_moves.moving(conn, LP, record(LP), SETTINGS, now)
    started = price_moves.spike_started(conn, NM, SETTINGS, now)
    # A delayed observation from before the spike does not consume it.
    _read(conn, NM, "2026-11-02T10:00:00Z")
    assert price_moves.moving(conn, NM, record(NM), SETTINGS, now)
    _read(conn, NM, started)
    assert not price_moves.moving(conn, NM, record(NM), SETTINGS, now)
    assert price_moves.moving(conn, LP, record(LP), SETTINGS, now)
    # The spike stays high for days; neither a repeated nor an older guide rearms it.
    _guide(conn, "2026-11-04", avg1=31.0, avg7=10.0)
    _guide(conn, "2026-11-02", avg1=31.0, avg7=10.0)
    assert price_moves.spike_started(conn, NM, SETTINGS, now) == started
    assert not price_moves.moving(conn, NM, record(NM), SETTINGS, now)


def test_missing_averages_do_not_clear_but_a_valid_quiet_guide_does(tmp_path):
    conn = _catalog(tmp_path)
    _guide(conn, "2026-11-03", avg1=30.0, avg7=10.0)
    started = price_moves.spike_started(conn, NM, SETTINGS, "x")
    _guide(conn, "2026-11-04", avg1=None, avg7=10.0)
    assert price_moves.spike_started(conn, NM, SETTINGS, "x") == started
    _guide(conn, "2026-11-05", avg1=10.0, avg7=10.0)
    assert price_moves.spike_started(conn, NM, SETTINGS, "x") is None
    _guide(conn, "2026-11-06", avg1=30.0, avg7=10.0)
    again = price_moves.spike_started(conn, NM, SETTINGS, "x")
    assert again is not None and again >= started


def test_first_edition_keys_ignore_the_unlimited_guide(tmp_path):
    conn = _catalog(tmp_path)
    _read(conn, FIRST, "2026-11-01T10:00:00Z", trend=5.0)
    _guide(conn, "2026-11-03", avg1=30.0, avg7=10.0, trend=40.0)
    assert not price_moves.moving(conn, FIRST, daily.snapshot_record(conn, FIRST), SETTINGS, "2026-11-03T12:00:00Z")


def test_a_moving_snapshot_is_fresh_for_six_hours_then_its_normal_tier(tmp_path, monkeypatch):
    conn = _catalog(tmp_path)
    monkeypatch.setattr("app.cardmarket_budget.scraper_is_ready", lambda _conn: False)
    monkeypatch.setattr("app.cardmarket_budget.scraper_online", lambda: False)
    _read(conn, NM, "2026-11-01T10:00:00Z")
    _guide(conn, "2026-11-03", avg1=30.0, avg7=10.0)
    assert prices_payload(conn, NM)["fresh_for_s"] == 21600
    _read(conn, NM, "2099-01-01T00:00:00Z")
    payload = prices_payload(conn, NM)
    assert payload["fresh_for_s"] == fresh_window(conn, NM) > 21600
    assert payload["freshness"] in {"fresh", "live"}


def test_a_condition_listing_waits_one_tier_longer():
    assert tier_window(SETTINGS, 40.0) == 86400
    assert tier_window(SETTINGS, 40.0, condition=True) == 172800
    assert tier_window(SETTINGS, 5.0, condition=True) == 518400
    assert tier_window(SETTINGS, 1.0, condition=True) == 518400
    assert price_moves.is_condition_key(LP) and not price_moves.is_condition_key(NM)


def _plan(monkeypatch, cards, **kwargs):
    """cards maps a url to (days since read, file trend, moving)."""
    monkeypatch.setattr(daily, "snapshot_record", lambda _conn, key: {
        "observed_at": f"2026-11-{10 - cards[key][0]:02d}T10:00:00Z", "prices": [{"label": "Trend", "amount": 1}]})
    monkeypatch.setattr(daily, "trend_for_url", lambda _conn, key: cards[key][1])
    monkeypatch.setattr(price_moves, "moving", lambda _c, key, *_a, **_k: cards[key][2])
    return daily.plan_night(None, "2026-11-10", settings=SETTINGS, rng=random.Random(1),
                            candidates=list(cards), **kwargs)


def test_cheap_condition_keys_are_skipped_but_nm_unknown_and_first_edition_are_kept(monkeypatch):
    cheap_lp = f"{PRODUCT}-cheap?language=1&minCondition=5"
    cheap_nm = f"{PRODUCT}-cheap?language=1&minCondition=2"
    unknown_lp = f"{PRODUCT}-unknown?language=1&minCondition=5"
    first_lp = f"{PRODUCT}-first?isFirstEd=Y&language=1&minCondition=5"
    plan = _plan(monkeypatch, {cheap_lp: (6, 1.0, False), cheap_nm: (6, 1.0, False),
                               unknown_lp: (2, None, False), first_lp: (2, None, False)})
    assert set(plan.urls) == {cheap_nm, unknown_lp, first_lp}


def test_early_reads_are_capped_and_due_moving_cards_stay_normal(monkeypatch):
    moving = {f"{PRODUCT}-{n}?language=1&minCondition=2": (1, 40.0 if n < 2 else 5.0, True) for n in range(6)}
    plan = _plan(monkeypatch, moving, early_limit=2)
    due = [url for url, (age, trend, _) in moving.items() if trend >= 20]
    assert set(due) <= set(plan.urls) and not set(due) & plan.early
    assert len(plan.early) == 2
    assert len(plan.urls) == len(due) + 2


def test_a_moving_cards_nm_key_goes_before_its_condition_key(monkeypatch):
    cards = {LP: (1, 5.0, True), NM: (1, 5.0, True)}
    assert _plan(monkeypatch, cards).urls == [NM, LP]


def test_early_allowance_comes_from_pages_after_the_reserve():
    assert daily.early_read_limit(SETTINGS, 50, 10) == 12
    assert daily.early_read_limit(SETTINGS, 5, 10) == 0


def test_an_early_key_read_since_planning_is_skipped(monkeypatch):
    queue = daily.WorkQueue([NM], {NM})
    monkeypatch.setattr(price_moves, "moving", lambda *_a, **_k: False)
    monkeypatch.setattr(daily, "snapshot_record", lambda *_a: None)
    calls = []
    status = daily.run_pass(None, Settings(scraper_daily_pages=50), scrape=lambda *a: calls.append(a) or {},
                            sleep=lambda _s: None, today="2026-11-10", queue=queue)
    assert status == "done" and calls == []


def test_config_sends_condition_switch_and_threshold():
    from app.routes.health import scan_price_config

    body = scan_price_config(Settings()).model_dump()
    assert body["condition_prices_enabled"] is False
    assert body["condition_read_min_trend"] == 2.0
    on = scan_price_config(Settings(condition_prices_enabled=True, condition_read_min_trend=3)).model_dump()
    assert on["condition_prices_enabled"] is True and on["condition_read_min_trend"] == 3.0


def test_production_check_refuses_the_night_job_without_the_subscriber_gate(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts" / "check-production.py"
    env = tmp_path / ".env-prod"
    env.write_text("DAILY_PRICES_ENABLED=true\n")
    env.chmod(0o600)
    out = subprocess.run([sys.executable, str(script), "--env-file", str(env)], capture_output=True, text=True)
    assert "PRODUCT_API_PAID_GATE_READY" in out.stdout
    env.write_text("DAILY_PRICES_ENABLED=true\nPRODUCT_API_PAID_GATE_READY=true\n")
    out = subprocess.run([sys.executable, str(script), "--env-file", str(env)], capture_output=True, text=True)
    assert "PRODUCT_API_PAID_GATE_READY" not in out.stdout


get_settings.cache_clear()
