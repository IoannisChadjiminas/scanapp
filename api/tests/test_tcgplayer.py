"""TCGplayer's daily prices: which printing a copy takes, and what is sent."""

import httpx

from app.tcgplayer import TcgplayerPrices, pick_printing, price_rows


def _store(tmp_path, calls):
    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(path)
        if path == "/last-updated.txt":
            return httpx.Response(200, text="2026-11-20T20:06:21+0000\n")
        if path.endswith("/groups"):
            return httpx.Response(200, json={"results": [{"groupId": 604}] if "/3/" in path else []})
        return httpx.Response(200, json={"results": [
            {"productId": 42346, "subTypeName": "Unlimited", "marketPrice": 4.5,
             "lowPrice": 2.0, "midPrice": 5.123, "highPrice": 900.0},
            {"productId": 42346, "subTypeName": "1st Edition", "marketPrice": 60.0,
             "lowPrice": 45.0, "midPrice": 70.0},
            {"productId": 9, "subTypeName": "Normal", "marketPrice": None, "lowPrice": 0.1,
             "midPrice": 0.2},
        ]})

    client = httpx.Client(base_url="https://tcg.test", transport=httpx.MockTransport(handle))
    return TcgplayerPrices(tmp_path / "tcgplayer.sqlite", client=client)


def test_the_copy_takes_its_own_printing():
    rows = {"Normal": {"market": 1}, "Reverse Holofoil": {"market": 2}, "1st Edition": {"market": 3}}
    assert pick_printing(rows, reverse=False, first_edition=None) == {"market": 1}
    assert pick_printing(rows, reverse=True, first_edition=None) == {"market": 2}
    assert pick_printing(rows, reverse=False, first_edition=True) == {"market": 3}
    assert pick_printing({"Holofoil": {"market": 4}}, reverse=True, first_edition=None) is None


def test_nothing_without_a_market_price():
    assert price_rows({"market": None, "low": 0.1, "mid": 0.2}) == []
    assert [row["label"] for row in price_rows({"market": 1.0, "low": None, "mid": 2.0})] == ["Market", "Mid"]


def test_prices_are_imported_once_a_day_and_sent_in_dollars(tmp_path):
    calls: list[str] = []
    store = _store(tmp_path, calls)
    assert store.import_prices(pause_s=0) == 3
    seen = len(calls)

    body = store.prices(42346)
    assert body == {
        "enabled": True,
        "prices": [
            {"label": "Market", "amount": 4.5, "currency": "USD", "source": "tcgplayer"},
            {"label": "Low", "amount": 2.0, "currency": "USD", "source": "tcgplayer"},
            {"label": "Mid", "amount": 5.12, "currency": "USD", "source": "tcgplayer"},
        ],
        "observed_at": "2026-11-20T20:06:21Z",
    }
    assert store.prices(42346, first_edition=True)["prices"][0]["amount"] == 60.0
    for missing in (store.prices(42346, reverse=True), store.prices(9), store.prices(None)):
        assert missing == {"enabled": True, "prices": [], "observed_at": None}
    # Fresh prices: nothing is fetched again.
    assert len(calls) == seen
    store.close()
