import random
from datetime import datetime, timezone

import pytest

from app import cardmarket_daily as daily
from app.config import Settings
from app.routes.health import scan_price_config

TODAY = "2026-10-12"


def keys(*names):
    return [f"https://www.cardmarket.com/en/Pokemon/Products/Singles/Set/{n}?language=1" for n in names]


def setup(monkeypatch, cards):
    """cards maps a name to (days since read or None, file trend, trend on the page)."""
    urls = keys(*cards)
    by_url = dict(zip(urls, cards.values()))

    def record(_conn, key):
        age, _file, page = by_url[key]
        if age is None:
            return None
        day = datetime(2026, 10, 12) .toordinal() - age
        stamp = datetime.fromordinal(day).strftime("%Y-%m-%dT10:00:00Z")
        prices = [{"label": "Near Mint", "amount": 1.0, "currency": "EUR"}]
        if page:
            prices.append({"label": "Trend", "amount": page, "currency": "EUR"})
        return {"observed_at": stamp, "fetched_at": stamp, "prices": prices}

    monkeypatch.setattr(daily, "portfolio_keys", lambda _conn: urls)
    monkeypatch.setattr(daily, "snapshot_record", record)
    monkeypatch.setattr(daily, "trend_for_url", lambda _conn, key: by_url[key][1])
    return {name: url for name, url in zip(cards, urls)}


def order(monkeypatch, cards, **settings):
    named = setup(monkeypatch, cards)
    back = {url: name for name, url in named.items()}
    result = daily.due_urls(None, TODAY, None, Settings(**settings), random.Random(1))
    return [back[url] for url in result]


def test_cheap_cards_wait_six_days_and_dear_cards_read_every_night(monkeypatch):
    got = order(monkeypatch, {
        "cheap-new": (2, 0.5, 0.5),
        "cheap-due": (6, 0.5, 0.5),
        "mid-new": (1, 5.0, 5.0),
        "mid-due": (2, 5.0, 5.0),
        "dear": (1, 40.0, 40.0),
        "today": (0, 40.0, 40.0),
    })
    assert sorted(got) == ["cheap-due", "dear", "mid-due"]


def test_no_read_or_unknown_trend_is_read_every_night(monkeypatch):
    got = order(monkeypatch, {"never": (None, 0.5, None), "unknown": (1, None, None)})
    assert sorted(got) == ["never", "unknown"]


def test_expiring_cards_come_first(monkeypatch):
    got = order(monkeypatch, {
        "dear": (1, 40.0, 40.0),
        "moved": (1, 30.0, 20.0),
        "expiring": (6, 0.5, 0.5),
    })
    assert got == ["expiring", "moved", "dear"]


def test_a_small_move_does_not_force_a_read(monkeypatch):
    assert order(monkeypatch, {"steady": (1, 4.0, 3.8)}) == []
    assert daily.trend_moved(4.0, 3.8, 10) is False
    assert daily.trend_moved(4.5, 3.8, 10) is True


def test_gap_has_jitter_and_shrinks_to_meet_the_deadline():
    rng = random.Random(3)
    gaps = {round(daily.jittered(10, 0.3, rng), 2) for _ in range(20)}
    assert len(gaps) > 1 and all(7 <= g <= 13 for g in gaps)
    assert daily.deadline_gap(10, 5, remaining=100, seconds_left=1000, load_s=8) == 5
    assert daily.deadline_gap(10, 5, remaining=100, seconds_left=100_000, load_s=8) == 10
    assert daily.deadline_gap(10, 5, remaining=100, seconds_left=1500, load_s=8) == 7
    now = datetime(2026, 10, 12, 2, 0, tzinfo=timezone.utc)
    assert daily.seconds_until("08:00", now) == 6 * 3600
    assert daily.seconds_until("nonsense", now) == 0


def test_config_sends_the_listing_age_in_seconds():
    assert scan_price_config(Settings()).listing_max_age_s == 7 * 86400
    assert scan_price_config(Settings(cardmarket_listing_max_age_days=3)).listing_max_age_s == 3 * 86400
    assert scan_price_config(Settings()).price_fresh_minutes == 360
