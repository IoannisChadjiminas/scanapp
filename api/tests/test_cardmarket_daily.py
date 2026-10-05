from __future__ import annotations

import pytest

from app.cardmarket import snapshot_record, write_snapshot
from app.cardmarket_daily import (
    DailyPace,
    DailyRateLimit,
    accepted_daily_browsers,
    due_urls,
    replace_portfolio,
    run_pass,
    should_schedule,
    store_result,
)
from app.cardmarket_queue import remember_phone_offers
from app.config import Settings, get_settings
from app.db import connect, init_catalog

GENGAR = (
    "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
    "Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102"
)
PIKACHU = (
    "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
    "Pokemon-Trading-Card-Game-Classic-Charizard-Ho-Oh-ex-Deck/Pikachu-CLC008"
)
OFFER = {
    "outcome": "offers",
    "rows": [{"price": "1,00 €", "condition": "NM"}],
    "header": {"From": 1.0},
}


def _catalog(tmp_path):
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    return conn


def _pace(**overrides) -> DailyPace:
    values = dict(
        gap_min=2,
        gap_max=60,
        gap_step=5,
        session_pages=30,
        rotate_before=120,
        lifetime=1800,
        now=lambda: 0,
        gap=2,
        session_id="daily-start",
        pages=0,
        started=0,
        challenge_streak=0,
    )
    values.update(overrides)
    return DailyPace(**values)


def test_portfolio_url_must_be_planetscale():
    from app.portfolio_db import connect_portfolio

    with pytest.raises(ValueError):
        connect_portfolio("postgres://user:secret@localhost/pokesingle-product")


def test_daily_switch_defaults_off():
    settings = Settings(_env_file=None)
    assert settings.daily_prices_enabled is False
    assert should_schedule(settings) is False
    settings.scraper_enabled = True
    assert should_schedule(settings) is False
    settings.daily_prices_enabled = True
    assert should_schedule(settings) is True


def test_more_than_one_daily_browser_is_refused():
    assert accepted_daily_browsers(1) == 1
    assert accepted_daily_browsers(10) == 1


def test_gap_returns_to_the_minimum_and_a_challenge_steps_up():
    pace = _pace(gap=12)
    pace.note("offers")
    pace.note("offers")
    assert pace.gap == 2
    pace.note("challenge_unsolved")
    assert pace.gap == 7
    capped = _pace(gap=60)
    capped.note("challenge_unsolved")
    assert capped.gap == 60


def test_session_rotates_on_the_page_cap_and_before_the_browser_lifetime():
    pace = _pace()
    first = pace.session_id
    pace.note("offers")
    assert pace.session_id == first
    pace.pages = 29
    pace.note("offers")
    assert pace.session_id != first
    clock = {"t": 0.0}
    timed = _pace(now=lambda: clock["t"], started=0)
    held = timed.session_id
    clock["t"] = 1800 - 120
    timed.note("offers")
    assert timed.session_id != held


def test_two_portfolios_one_url_and_a_snapshot_from_today_is_skipped(tmp_path):
    conn = _catalog(tmp_path)
    replace_portfolio(conn, "a", [(GENGAR, "2026-10-02T10:00:00Z")])
    replace_portfolio(conn, "b", [(GENGAR, "2026-10-02T11:00:00Z"), (PIKACHU, "2026-10-02T09:00:00Z")])
    assert due_urls(conn, "2026-10-02") == [GENGAR, PIKACHU]
    write_snapshot(conn, GENGAR, [{"label": "NM", "amount": 3.0, "currency": "EUR"}])
    today = snapshot_record(conn, GENGAR)["fetched_at"][:10]
    assert due_urls(conn, today) == [PIKACHU]
    remember_phone_offers(
        conn,
        PIKACHU,
        [{"price": "2,00 €", "condition": "NM"}],
    )
    assert due_urls(conn, today) == []


def test_a_newer_phone_price_is_kept(tmp_path):
    conn = _catalog(tmp_path)
    write_snapshot(
        conn,
        GENGAR,
        [{"label": "NM", "amount": 9.0, "currency": "EUR"}],
        observed_at="2099-01-01T00:00:00Z",
    )
    store_result(conn, GENGAR, {**OFFER, "url": GENGAR})
    record = snapshot_record(conn, GENGAR)
    assert record["prices"][0]["amount"] == 9.0


def test_rate_limit_sets_the_max_gap_and_resumes_on_a_new_session(tmp_path, monkeypatch):
    conn = _catalog(tmp_path)
    replace_portfolio(conn, "a", [(GENGAR, "2026-10-02T12:00:00Z")])
    monkeypatch.setattr("app.cardmarket_daily.scraper_block_reason", lambda conn: None)
    settings = get_settings()
    settings.photo_scrape_active = False
    settings.daily_browsers = 4
    settings.daily_gap_min_s = 2
    settings.daily_gap_max_s = 60
    settings.daily_gap_step_s = 5
    settings.scraper_page_gap_s = 0
    settings.daily_session_pages = 30
    settings.scraper_browser_lifetime_s = 1800
    settings.daily_session_rotate_before_s = 120
    calls = []
    sleeps = []

    def scrape(url, session_id):
        calls.append(session_id)
        if len(calls) == 1:
            raise DailyRateLimit(9)
        return {**OFFER, "url": url}

    assert run_pass(
        conn,
        settings,
        scrape=scrape,
        sleep=sleeps.append,
        today="2026-10-01",
        now=lambda: 0,
    ) == "done"
    assert sleeps == [9, 55]
    assert calls[0] != calls[1]
    assert snapshot_record(conn, GENGAR)["prices"]
