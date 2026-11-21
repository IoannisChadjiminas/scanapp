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
                {"id": 72, "card_market_ids": [555001], "tcg_player_id": 42999},
            ])
        if request.url.params.get("blueprint_id") == "72":
            return httpx.Response(200, json={"72": [_product(900)]})
        return httpx.Response(200, json={"70": [_product(250), _product(400, language="jp")]})

    client = httpx.Client(base_url="https://ct.test", transport=httpx.MockTransport(handle))
    return CardTrader("token", tmp_path / "cardtrader.sqlite", client=client)


def test_a_card_is_found_by_its_cardmarket_id_and_read_once_an_hour(tmp_path):
    calls: list[str] = []
    reader = _reader(tmp_path, calls)
    assert reader.import_map(pause_s=0) == 2
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


def test_a_picked_listing_is_priced_as_its_own_product(tmp_path):
    """V1 and V2 are separate Cardmarket products of one catalogue card."""
    from app.tcgplayer import TcgplayerPrices

    reader = _reader(tmp_path, [])
    reader.import_map(pause_s=0)
    main = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Pikachu-V1"
    second = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Pikachu-V2"
    unknown = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Pikachu-V3"
    catalog = connect(tmp_path / "catalog.sqlite")
    init_catalog(catalog)
    values = {"id": "base1-58", "name": "Pikachu", "language": "en",
              "cardmarket_id": 271823, "cardmarket_url": main}
    values.update({
        row[1]: "" for row in catalog.execute("PRAGMA table_info(cards)")
        if row[3] and row[4] is None and row[1] not in values
    })
    catalog.execute(
        f"INSERT INTO cards ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
        list(values.values()),
    )
    for url, product in ((second, 555001), (unknown, None)):
        catalog.execute(
            "INSERT INTO cardmarket_expansion_products "
            "(url, source, card_id, matched, imported_at, product_id) VALUES (?, 'test', ?, 1, '', ?)",
            (url, "base1-58", product),
        )
    catalog.commit()

    store = TcgplayerPrices(tmp_path / "tcgplayer.sqlite", client=httpx.Client(
        base_url="https://tcg.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    ))
    store._conn.executemany(
        "INSERT INTO prices VALUES (?, 'Normal', ?, ?, ?)",
        [(42346, 4.5, 2.0, 5.0), (42999, 60.0, 45.0, 70.0)],
    )
    store._conn.executemany(
        "INSERT INTO meta VALUES (?, ?)",
        [("imported_at", "99999999999"), ("priced_at", "2026-11-20T20:06:21+0000")],
    )
    store._conn.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.cardtrader = reader
    app.state.tcgplayer = store
    app.state.dbs = type("Dbs", (), {"catalog": catalog})()
    client = TestClient(app)

    def amounts(path, url=None):
        params = {"card_id": "base1-58"} | ({"url": url} if url else {})
        return [p["amount"] for p in client.get(f"/api/v1/{path}/prices", params=params).json()["prices"]]

    # No listing, or the main one (with or without its filters): the card's own product.
    for url in (None, main, main + "?language=1&minCondition=2"):
        assert amounts("cardtrader", url) == [2.5]
        assert amounts("tcgplayer", url)[0] == 4.5
    # An address that is not one of the card's stored listings means the card.
    assert amounts("cardtrader", main.replace("/en/", "/de/")) == [2.5]
    # The second listing has its own product, so its own prices.
    assert amounts("cardtrader", second + "?isFirstEd=N") == [9.0]
    assert amounts("tcgplayer", second)[0] == 60.0
    # A listing whose product is not known shows nothing, never another version's price.
    assert amounts("cardtrader", unknown) == []
    assert amounts("tcgplayer", unknown) == []
    reader.close()
    store.close()
