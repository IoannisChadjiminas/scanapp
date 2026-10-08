"""Scans get a price from the nightly file or TCGdex before any listing read."""

import json
import time

import httpx
import pytest

from app import price_sources
from app.cardmarket import write_snapshot
from app.config import Settings, get_settings
from app.db import connect, init_catalog
from app.price_sources import best_prices, import_guide, refresh_tcgdex

URL = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Pikachu"
GUIDE = {
    "version": 1,
    "createdAt": "2026-10-08T02:51:56+0200",
    "priceGuides": [
        {"idProduct": 100, "avg": 5.0, "low": 3.5, "trend": 4.2, "avg7": 4.0,
         "avg-holo": None, "low-holo": 9.0, "trend-holo": 12.0, "avg7-holo": 11.0},
        {"idProduct": 101, "avg": None, "low": None, "trend": None, "avg7": None},
    ],
}


def _catalog(tmp_path):
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    return conn


def _card(conn, card_id, *, product=None, variants=None, language="en", url=None):
    conn.execute(
        "INSERT INTO cards (id, provider_id, name, set_id, set_name, collector_number, language,"
        " variants_json, cardmarket_id, cardmarket_url) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (card_id, card_id, "Pikachu", "base1", "Base Set", "58", language,
         json.dumps(variants or {"normal": True}), product, url),
    )
    conn.commit()


def _labels(prices):
    return {price["label"]: price["amount"] for price in prices}


def test_guide_prices_are_tagged_with_source_and_date(tmp_path):
    conn = _catalog(tmp_path)
    _card(conn, "en:a", product=100)
    import_guide(conn, GUIDE)
    prices = best_prices(conn, "en:a", None)
    assert _labels(prices) == {"From": 3.5, "Trend": 4.2, "7-day": 4.0}
    assert {p["source"] for p in prices} == {"cardmarket_file"}
    assert prices[0]["as_of"] == "2026-10-08T00:51:56Z"
    assert not prices[0]["stale"]


def test_foil_only_printing_uses_the_holo_columns(tmp_path):
    conn = _catalog(tmp_path)
    _card(conn, "en:b", product=100, variants={"normal": False, "holo": True})
    import_guide(conn, GUIDE)
    assert _labels(best_prices(conn, "en:b", None))["Trend"] == 12.0


def test_product_with_only_empty_values_has_no_price(tmp_path):
    conn = _catalog(tmp_path)
    _card(conn, "en:c", product=101)
    import_guide(conn, GUIDE)
    assert best_prices(conn, "en:c", None) == []


def test_a_fresh_listing_sample_beats_the_file(tmp_path):
    conn = _catalog(tmp_path)
    _card(conn, "en:a", product=100, url=URL)
    import_guide(conn, GUIDE)
    write_snapshot(conn, URL, [{"label": "From", "amount": 2.0, "currency": "EUR"}])
    prices = best_prices(conn, "en:a", URL)
    assert prices[0]["source"] == "live" and prices[0]["amount"] == 2.0
    assert not prices[0]["stale"]


def test_an_old_listing_sample_loses_to_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "cardmarket_fresh_by_value", False)
    conn = _catalog(tmp_path)
    _card(conn, "en:a", product=100, url=URL)
    import_guide(conn, GUIDE)
    write_snapshot(conn, URL, [{"label": "From", "amount": 2.0, "currency": "EUR"}])
    monkeypatch.setattr("app.cardmarket_queue.fresh_seconds", lambda: 0)
    time.sleep(1.1)
    assert {p["source"] for p in best_prices(conn, "en:a", URL)} == {"cardmarket_file"}


def test_an_old_listing_sample_is_the_last_resort(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "cardmarket_fresh_by_value", False)
    conn = _catalog(tmp_path)
    _card(conn, "en:a", product=None, url=URL)
    write_snapshot(conn, URL, [{"label": "From", "amount": 2.0, "currency": "EUR"}])
    monkeypatch.setattr("app.cardmarket_queue.fresh_seconds", lambda: 0)
    time.sleep(1.1)
    prices = best_prices(conn, "en:a", URL)
    assert prices[0]["source"] == "live" and prices[0]["stale"]


def test_tcgdex_cardmarket_then_tcgplayer(tmp_path):
    conn = _catalog(tmp_path)
    _card(conn, "en:d", variants={"normal": True, "reverse": True})
    conn.execute(
        "INSERT INTO tcgdex_prices VALUES (?,?,?,?)",
        ("en:d", json.dumps({"unit": "EUR", "trend": 1.5, "low": 0.9, "updated": "2026-10-08T01:00:00Z"}),
         json.dumps({"unit": "USD", "normal": {"marketPrice": 2.25, "lowPrice": 1.0}}), "x"),
    )
    prices = best_prices(conn, "en:d", None)
    assert {p["source"] for p in prices} == {"tcgdex"} and _labels(prices)["Trend"] == 1.5

    conn.execute("UPDATE tcgdex_prices SET cardmarket_json = '{}'")
    prices = best_prices(conn, "en:d", None)
    assert {p["source"] for p in prices} == {"tcgplayer"}
    assert _labels(prices) == {"Market": 2.25, "Low": 1.0}
    assert {p["currency"] for p in prices} == {"USD"}


def test_a_much_smaller_file_is_refused(tmp_path):
    conn = _catalog(tmp_path)
    big = {**GUIDE, "priceGuides": [{"idProduct": i, "trend": 1.0} for i in range(10)]}
    import_guide(conn, big)
    with pytest.raises(ValueError):
        import_guide(conn, {**GUIDE, "priceGuides": big["priceGuides"][:2]})
    assert conn.execute("SELECT COUNT(*) FROM cardmarket_guide").fetchone()[0] == 10


def test_a_new_file_replaces_the_old_without_leaving_stale_rows(tmp_path):
    conn = _catalog(tmp_path)
    import_guide(conn, GUIDE)
    newer = {**GUIDE, "createdAt": "2026-10-09T02:51:56+0200",
             "priceGuides": [{"idProduct": 100, "trend": 7.0}, {"idProduct": 102, "trend": 1.0}]}
    import_guide(conn, newer)
    ids = {r[0] for r in conn.execute("SELECT id_product FROM cardmarket_guide")}
    assert ids == {100, 102}


def test_not_a_price_guide_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        import_guide(_catalog(tmp_path), {"hello": "world"})


def test_tcgdex_refresh_covers_only_cards_the_file_misses(tmp_path, monkeypatch):
    conn = _catalog(tmp_path)
    _card(conn, "en:a", product=100)
    _card(conn, "en:e", product=None)
    import_guide(conn, GUIDE)
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={"pricing": {"cardmarket": {"trend": 3.0, "unit": "EUR"}}})

    real = httpx.Client
    monkeypatch.setattr(price_sources.httpx, "Client",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    settings = Settings(tcgdex_prices_batch=10, tcgdex_prices_gap_s=0)
    assert refresh_tcgdex(conn, settings, sleep=lambda _s: None) == 1
    assert seen == ["/v2/en/cards/e"]
    assert {p["source"] for p in best_prices(conn, "en:e", None)} == {"tcgdex"}


def test_tcgdex_refresh_reads_cards_from_the_catalogue_connection(tmp_path, monkeypatch):
    # With the cloud catalogue the cards exist only on the serving connection;
    # the job's own connection to the file holds the price tables and no cards.
    own = _catalog(tmp_path)
    serving = connect(tmp_path / "serving.sqlite")
    init_catalog(serving)
    _card(serving, "en:a", product=100)
    _card(serving, "en:e", product=None)
    _card(serving, "en:fresh", product=None)
    import_guide(own, GUIDE)
    with own:
        own.execute("INSERT INTO tcgdex_prices (card_id, cardmarket_json, tcgplayer_json, fetched_at)"
                    " VALUES ('en:fresh', '{}', '{}', '2026-10-07T00:00:00Z')")
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={"pricing": {"cardmarket": {"trend": 3.0, "unit": "EUR"}}})

    real = httpx.Client
    monkeypatch.setattr(price_sources.httpx, "Client",
                        lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    settings = Settings(tcgdex_prices_batch=10, tcgdex_prices_gap_s=0)
    assert refresh_tcgdex(own, settings, catalog=serving, sleep=lambda _s: None) == 2
    assert seen == ["/v2/en/cards/e", "/v2/en/cards/fresh"]
    stored = {r[0] for r in own.execute("SELECT card_id FROM tcgdex_prices")}
    assert stored == {"en:e", "en:fresh"}


def test_tiers_make_cheap_cards_fresh_for_longer():
    settings = Settings()
    assert price_sources.tier_window(settings, 0.5) == 604800
    assert price_sources.tier_window(settings, 4.2) == 86400
    assert price_sources.tier_window(settings, 50) == 21600
    assert price_sources.tier_window(settings, 300) == 3600
    assert price_sources.tier_window(settings, None) is None
    assert price_sources.tier_window(Settings(cardmarket_fresh_by_value=False), 0.5) is None


def test_bad_tier_text_is_ignored():
    assert price_sources.parse_tiers("x:1,5:abc,3:60,*:10") == [(3.0, 60), (None, 10)]


def test_fresh_window_follows_the_trend_of_the_product(tmp_path):
    conn = _catalog(tmp_path)
    _card(conn, "en:a", product=100, url=URL)
    import_guide(conn, GUIDE)
    assert price_sources.trend_for_url(conn, URL) == 4.2
    assert price_sources.fresh_window(conn, URL) == 86400
    assert price_sources.fresh_window(conn, "https://example.test/none") == Settings().cardmarket_price_fresh_minutes * 60


def test_a_day_old_sample_of_a_cheap_card_is_still_live(tmp_path, monkeypatch):
    conn = _catalog(tmp_path)
    _card(conn, "en:a", product=100, url=URL)
    import_guide(conn, GUIDE)
    write_snapshot(conn, URL, [{"label": "From", "amount": 2.0, "currency": "EUR"}])
    # Fifteen minutes is the plain window; a 4 EUR card gets a day.
    monkeypatch.setattr("app.cardmarket_queue.fresh_seconds", lambda: 0)
    prices = best_prices(conn, "en:a", URL)
    assert prices[0]["source"] == "live" and not prices[0]["stale"]


def test_parallel_read_is_skipped_for_a_cheap_card(tmp_path, monkeypatch):
    from app.cardmarket_queue import schedule_scan_parallel_read

    settings = get_settings()
    monkeypatch.setattr(settings, "scan_price_server_read", "parallel")
    monkeypatch.setattr(settings, "scan_price_server_read_daily_pages", 10)
    conn = _catalog(tmp_path)
    _card(conn, "en:a", product=100, url=URL)
    import_guide(conn, {**GUIDE, "priceGuides": [{"idProduct": 100, "trend": 0.4}]})
    assert schedule_scan_parallel_read(conn, status="matched", url=URL) is None
    import_guide(conn, {**GUIDE, "createdAt": "2026-10-09T02:51:56+0200",
                        "priceGuides": [{"idProduct": 100, "trend": 9.0}]})
    assert schedule_scan_parallel_read(conn, status="matched", url=URL) is not None
    monkeypatch.setattr(settings, "scan_price_server_read_min_trend", 0)
    assert schedule_scan_parallel_read(conn, status="matched", url=URL + "-other") is not None


def test_first_price_event_passes_the_allow_list():
    from app.client_diagnostics import phone_diagnostic_lines

    lines = phone_diagnostic_lines({"events": [{
        "event": "price.first_shown", "scan": "abc123", "elapsed_ms": 420,
        "price_source": "cardmarket_file", "stored": False, "guessed": True,
        "url": "https://secret.example/x", "card_name": "Pikachu",
    }]})
    assert lines == ["phone event=price.first_shown scan=abc123 elapsed_ms=420 "
                     "stored=false guessed=true price_source=cardmarket_file"]


def test_preview_candidates_carry_set_number_and_a_stored_price(tmp_path):
    from app.recognition.pipeline import _preview_candidates

    conn = _catalog(tmp_path)
    _card(conn, "en:a", product=100, url=URL)
    import_guide(conn, GUIDE)
    [preview] = _preview_candidates(conn, ["en:a", "missing"])
    assert preview["card_id"] == "en:a"
    assert preview["set_name"] == "Base Set"
    assert preview["collector_number"] == "58"
    assert preview["language"] == "en"
    assert preview["cardmarket_url"] == URL
    assert {p["source"] for p in preview["cardmarket_prices"]} == {"cardmarket_file"}
