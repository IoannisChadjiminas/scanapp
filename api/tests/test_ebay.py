"""eBay graded asking prices: which listings count, and what the app is sent."""

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ebay import Ebay, graded_listings, names_grade
from app.routes.ebay import router


def _item(title, value, *, currency="USD", options=("FIXED_PRICE",), country="US"):
    return {
        "title": title,
        "price": {"value": str(value), "currency": currency},
        "buyingOptions": list(options),
        "itemLocation": {"country": country},
        "itemWebUrl": "https://www.ebay.com/itm/1",
    }


def test_a_title_must_name_the_grader_and_the_exact_grade():
    assert names_grade("Charizard 4/102 Base Set PSA 10 GEM MINT", "PSA", "10")
    assert names_grade("charizard psa10", "PSA", "10")
    assert names_grade("Charizard PSA-9", "PSA", "9")
    assert names_grade("Charizard BGS 9.5 Gem", "BGS", "9.5")
    assert not names_grade("Charizard PSA 10", "PSA", "1")
    assert not names_grade("Charizard PSA 9.5", "PSA", "9")
    assert not names_grade("Charizard PSA 9", "PSA", "9.5")
    assert not names_grade("Charizard CGC 10", "PSA", "10")
    assert not names_grade("Charizard 10 HP", "PSA", "10")


def test_only_buy_it_now_listings_of_one_card_in_the_grade_count():
    listings = graded_listings(
        [
            _item("Charizard 4/102 PSA 10", 900),
            _item("Charizard 4/102 PSA 10 Gem Mint", 750, country="CA"),
            _item("Charizard 4/102 PSA 9", 300),
            _item("Charizard 4/102 PSA 10", 500, options=("AUCTION",)),
            _item("Charizard 4/102 PSA 10", 700, currency="EUR"),
            _item("PSA 10 LOT of 5 Charizard", 100),
            _item("Custom PROXY Charizard PSA 10", 20),
            _item("Charizard 4/102 PSA 10", "free"),
        ],
        grader="PSA",
        grade="10",
        currency="USD",
    )
    assert [item["amount"] for item in listings] == [750.0, 900.0]
    assert listings[0]["country"] == "CA"


def _reader(calls, items):
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/oauth2/token"):
            assert request.headers["authorization"].startswith("Basic ")
            return httpx.Response(200, json={"access_token": "token", "expires_in": 7200})
        assert request.headers["authorization"] == "Bearer token"
        assert request.headers["x-ebay-c-marketplace-id"] == "EBAY_US"
        assert request.url.params["category_ids"] == "183454"
        assert request.url.params["filter"] == "buyingOptions:{FIXED_PRICE}"
        return httpx.Response(200, json={"itemSummaries": items})

    return Ebay("id", "secret", client=httpx.Client(
        base_url="https://ebay.test", transport=httpx.MockTransport(handle)))


def test_the_cheapest_five_are_averaged_and_asked_once_in_six_hours():
    calls: list[str] = []
    prices = [100, 110, 120, 130, 140, 900, 1500]
    reader = _reader(calls, [_item(f"Pikachu 58/102 PSA 10 #{n}", n) for n in prices])
    first = reader.graded("Pikachu 58/102 PSA 10", "PSA", "10")
    assert first["average"] == 120.0
    assert first["count"] == 7
    assert [item["amount"] for item in first["listings"]] == [100, 110, 120, 130, 140]
    assert first["observed_at"].endswith("Z")
    assert reader.graded("pikachu  58/102 psa 10", "PSA", "10") == first
    # One token, one search.
    assert calls == ["/identity/v1/oauth2/token", "/buy/browse/v1/item_summary/search"]
    reader.close()


def test_too_few_listings_give_no_average():
    reader = _reader([], [_item("Pikachu 58/102 PSA 10", 100), _item("Pikachu 58/102 PSA 10", 120)])
    answer = reader.graded("Pikachu 58/102 PSA 10", "PSA", "10")
    assert answer["average"] is None and answer["listings"] == [] and answer["count"] == 2
    reader.close()


def test_the_route_takes_only_a_search_for_the_grade():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.ebay = _reader([], [_item(f"Pikachu 58/102 PSA 10 #{n}", n) for n in (10, 20, 30)])
    client = TestClient(app)
    ask = lambda **params: client.get("/api/v1/ebay/graded", params=params)  # noqa: E731

    body = ask(q="Pikachu 58/102 PSA 10", grader="psa", grade="10").json()
    assert body["enabled"] is True and body["average"] == 20.0 and len(body["listings"]) == 3
    # Not a general way into eBay: the search must name the grader.
    assert ask(q="anything at all", grader="PSA", grade="10").status_code == 422
    assert ask(q="Pikachu PSA 10", grader="XYZ", grade="10").status_code == 422
    assert ask(q="Pikachu PSA 11", grader="PSA", grade="11").status_code == 422

    app.state.ebay = None
    assert ask(q="Pikachu 58/102 PSA 10", grader="PSA", grade="10").json()["enabled"] is False
