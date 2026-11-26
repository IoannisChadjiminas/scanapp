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


def test_a_low_price_stands_alone_where_nothing_sold():
    assert [row["label"] for row in price_rows({"market": None, "low": 0.1, "mid": 0.2})] == ["Low", "Mid"]
    assert [row["label"] for row in price_rows({"market": 1.0, "low": None, "mid": 2.0})] == ["Market", "Mid"]
    assert price_rows({"market": None, "low": None, "mid": 2.0}) == []


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
        "url": "https://www.tcgplayer.com/product/42346",
        "observed_at": "2026-11-20T20:06:21Z",
    }
    assert store.prices(42346, first_edition=True)["prices"][0]["amount"] == 60.0
    for missing in (store.prices(42346, reverse=True), store.prices(None)):
        assert missing == {"enabled": True, "prices": [], "url": None, "observed_at": None}
    # Listings but no sales: the low price, no market price.
    assert [row["label"] for row in store.prices(9)["prices"]] == ["Low", "Mid"]
    # Fresh prices: nothing is fetched again.
    assert len(calls) == seen
    store.close()


def test_a_card_is_found_in_its_set_by_number_and_name(tmp_path):
    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/last-updated.txt":
            return httpx.Response(200, text="2026-11-20T20:06:21+0000")
        if path == "/tcgplayer/3/groups":
            return httpx.Response(200, json={"results": [{"groupId": 3, "abbreviation": "SVP"}]})
        if path == "/tcgplayer/85/groups":
            return httpx.Response(200, json={"results": [{"groupId": 7, "abbreviation": "SV2a"}]})
        number = lambda value: [{"name": "Number", "value": value}]  # noqa: E731
        if path == "/tcgplayer/85/7/products":
            return httpx.Response(200, json={"results": [
                {"productId": 501, "name": "Pikachu - 025/165", "extendedData": number("025/165")},
                {"productId": 601, "name": "Mew ex - 205/165", "extendedData": number("205/165")},
                {"productId": 602, "name": "Mew ex (Master Ball Pattern)", "extendedData": number("205/165")},
                {"productId": 603, "name": "Erika's Invitation - 205/165", "extendedData": number("205/165")},
                {"productId": 900, "name": "Booster Box", "extendedData": []},
            ]})
        if path == "/tcgplayer/3/3/products":
            return httpx.Response(200, json={"results": [
                {"productId": 801, "name": "Pikachu - 025", "extendedData": number("025")},
            ]})
        return httpx.Response(200, json={"results": [
            {"productId": 501, "subTypeName": "Normal", "marketPrice": 1.25, "lowPrice": 0.9, "midPrice": 1.3},
        ]})

    store = TcgplayerPrices(
        tmp_path / "tcgplayer.sqlite",
        client=httpx.Client(base_url="https://tcg.test", transport=httpx.MockTransport(handle)),
    )
    store.import_prices(pause_s=0)
    # The set: by its code, in the card's own language, or where its known
    # products are.
    assert store.groups_for([], "SV2a", "ja") == {7}
    assert store.groups_for([], "SV2a", "en") == set()
    assert store.groups_for([501, 601], "other", "ja") == {7}
    japan = {7}
    assert store.find(japan, "025", ["pikachusv2a025"]) == 501
    assert store.find(japan, "25", []) == 501
    assert store.prices(store.find(japan, "025", []))["prices"][0]["amount"] == 1.25
    # Another name, or two products the name cannot tell apart: nothing.
    assert store.find(japan, "025", ["raichusv2a025"]) is None
    assert store.find(japan, "205", ["mewexsv2a205"]) is None
    assert store.find(japan, "205", []) is None
    # The name picks the one card among different ones sharing a number.
    assert store.find(japan, "205", ["erikasinvitationsv2a205"]) == 603
    assert store.find(set(), "025", []) is None
    store.close()
