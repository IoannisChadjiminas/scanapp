"""CardTrader listings: which copies count, and what the card page is sent."""

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cardtrader import CardTrader, offers_from_products
from app.db import connect, init_catalog
from app.routes.cardtrader import router


def _product(cents, *, condition="Near Mint", language="en", reverse=False,
             first_edition=False, user_type="normal", country="IT", **extra):
    return {
        "quantity": 1,
        "graded": False,
        "on_vacation": False,
        "properties_hash": {
            "condition": condition,
            "pokemon_language": language,
            "pokemon_reverse": reverse,
            "first_edition": first_edition,
            "signed": False,
            "altered": False,
        },
        "user": {"user_type": user_type, "country_code": country},
        "price": {"cents": cents, "currency": "EUR"},
        **extra,
    }


def test_only_the_wanted_copy_counts_cheapest_first():
    rows = offers_from_products(
        [
            _product(900, user_type="pro", country="DE"),
            _product(500),
            _product(100, condition="Played"),
            _product(110, language="it"),
            _product(120, reverse=True),
            _product(130, graded=True),
            _product(140, on_vacation=True),
            _product(150, quantity=0),
            _product(700, condition="Mint"),
        ],
        language="en",
    )
    assert [row["amount"] for row in rows] == [5.0, 7.0, 9.0]
    assert rows[0] == {
        "label": "NM · English · Italy",
        "amount": 5.0,
        "currency": "EUR",
        "source": "cardtrader",
    }
    assert rows[1]["label"].startswith("MT · ")
    assert rows[2]["label"] == "NM · English · Germany · Professional"


def test_a_played_copy_takes_that_condition_or_better():
    products = [_product(100, condition="Played"), _product(50, condition="Poor")]
    assert offers_from_products(products, language="en") == []
    rows = offers_from_products(products, language="en", condition="LP")
    assert [row["amount"] for row in rows] == [1.0]


def test_reverse_holo_and_first_edition_are_matched():
    products = [_product(100), _product(300, reverse=True), _product(900, first_edition=True)]
    reverse = offers_from_products(products, language="en", reverse=True)
    assert [row["amount"] for row in reverse] == [3.0]
    first = offers_from_products(products, language="en", first_edition=True)
    assert [row["amount"] for row in first] == [9.0]
    unlimited = offers_from_products(products, language="en", first_edition=False)
    assert [row["amount"] for row in unlimited] == [1.0]


def _reader(tmp_path, calls):
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path + ("?" + request.url.query.decode() if request.url.query else ""))
        if request.url.path.endswith("/expansions"):
            return httpx.Response(200, json=[{"id": 7, "game_id": 5}, {"id": 8, "game_id": 1}])
        if request.url.path.endswith("/blueprints/export"):
            return httpx.Response(200, json=[
                {"id": 70, "card_market_ids": [271823], "tcg_player_id": 42346},
                {"id": 71, "card_market_ids": []},
            ])
        return httpx.Response(200, json={"70": [_product(250), _product(400, language="jp")]})

    client = httpx.Client(base_url="https://ct.test", transport=httpx.MockTransport(handle))
    return CardTrader("token", tmp_path / "cardtrader.sqlite", client=client)


def test_a_card_is_found_by_its_cardmarket_id_and_read_once_an_hour(tmp_path):
    calls: list[str] = []
    reader = _reader(tmp_path, calls)
    assert reader.import_map(pause_s=0) == 1
    assert reader.blueprints(271823) == [70]
    assert reader.tcgplayer_id(271823) == 42346
    assert reader.tcgplayer_id(1) is None

    first = reader.prices(271823, "en")
    again = reader.prices(271823, "en")
    assert first == again
    assert first["matched"] is True and first["count"] == 1
    assert first["prices"][0]["amount"] == 2.5
    assert first["observed_at"].endswith("Z")
    assert sum("marketplace" in call for call in calls) == 1

    unknown = reader.prices(1, "en")
    assert unknown["matched"] is False and unknown["prices"] == []
    assert unknown["observed_at"] is None
    reader.close()


def test_the_route_answers_for_a_catalogue_card(tmp_path):
    calls: list[str] = []
    reader = _reader(tmp_path, calls)
    reader.import_map(pause_s=0)
    catalog = connect(tmp_path / "catalog.sqlite")
    init_catalog(catalog)
    columns = {row[1] for row in catalog.execute("PRAGMA table_info(cards)")}
    values = {"id": "base1-58", "name": "Pikachu", "language": "en", "cardmarket_id": 271823}
    required = [
        row[1] for row in catalog.execute("PRAGMA table_info(cards)")
        if row[3] and row[4] is None and row[1] not in values
    ]
    values.update({name: "" for name in required})
    assert set(values) <= columns
    catalog.execute(
        f"INSERT INTO cards ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
        list(values.values()),
    )
    catalog.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.cardtrader = reader
    app.state.dbs = type("Dbs", (), {"catalog": catalog})()
    client = TestClient(app)

    body = client.get("/api/v1/cardtrader/prices", params={"card_id": "base1-58"}).json()
    assert body["enabled"] is True and body["matched"] is True
    assert [price["amount"] for price in body["prices"]] == [2.5]
    assert client.get("/api/v1/cardtrader/prices", params={"card_id": "nope"}).status_code == 404
    assert client.get(
        "/api/v1/cardtrader/prices", params={"card_id": "base1-58", "condition": "XX"}
    ).status_code == 422

    app.state.cardtrader = None
    off = client.get("/api/v1/cardtrader/prices", params={"card_id": "base1-58"}).json()
    assert off == {"enabled": False, "matched": False, "count": 0, "prices": [], "observed_at": None}
    reader.close()
