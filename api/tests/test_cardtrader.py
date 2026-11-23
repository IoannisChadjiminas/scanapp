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

    # The card's price over time, from what was kept: Cardmarket's trend on
    # the days it changed, TCGplayer's price on the days it moved, each line
    # run to the newest day.
    from app import price_history

    price_history.ensure_schema(catalog)
    catalog.executemany(
        "INSERT INTO price_history_daily (id_product, day, trend, low) VALUES (?, ?, ?, ?)",
        [(271823, "2026-11-07", 10.0, 5.0), (271823, "2026-11-09", 10.0, 6.0),
         (271823, "2026-11-12", 12.5, 6.0), (555001, "2026-11-08", 90.0, 80.0)],
    )
    catalog.execute("INSERT INTO price_guide_import_days VALUES ('2026-11-20')")
    catalog.commit()
    app.state.dbs.portfolio = catalog
    assert store.record_day("2026-11-01", [(42346, "Normal", 4.0, 2.0), (42999, "Normal", None, 50.0)]) == 2
    # A cent's move is not a point; a real one is.
    assert store.record_day("2026-11-05", [(42346, "Normal", 4.01, 2.0)]) == 0
    assert store.record_day("2026-11-10", [(42346, "Normal", 4.5, 2.0)]) == 1

    def history(**params):
        body = client.get("/api/v1/prices/history", params={"card_id": "base1-58"} | params).json()
        return {name: [(p["day"], p["amount"]) for p in body[name]] for name in body}

    assert history() == {
        "cardmarket": [("2026-11-07", 10.0), ("2026-11-12", 12.5), ("2026-11-20", 12.5)],
        "tcgplayer": [("2026-11-01", 4.0), ("2026-11-10", 4.5), ("2026-11-20", 4.5)],
    }
    assert history(url=second) == {
        "cardmarket": [("2026-11-08", 90.0), ("2026-11-20", 90.0)],
        "tcgplayer": [("2026-11-01", 50.0), ("2026-11-20", 50.0)],
    }
    # A first edition has no Cardmarket trend, and no such printing here.
    assert history(first_edition="true") == {"cardmarket": [], "tcgplayer": []}

    # A collection's copies valued from TCGplayer's market price, in euros.
    from app.fx import EuroRate

    ask = lambda: client.post("/api/v1/tcgplayer/values", json={"copies": [  # noqa: E731
        {"card_id": "base1-58"},
        {"card_id": "base1-58", "url": second},
        {"card_id": "base1-58", "url": unknown},
        {"card_id": "nope"},
    ]}).json()
    # Without a rate there is no value: dollars are never counted as euros.
    nothing = {"value_eur": None, "market": None, "source": None}
    assert ask() == {"enabled": False, "values": [nothing] * 4}
    app.state.fx = EuroRate(client=httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, text="<Cube currency='USD' rate='1.2500'/>"))))
    assert ask() == {"enabled": True, "values": [
        {"value_eur": 3.6, "market": 4.5, "source": "tcgplayer"},
        {"value_eur": 48.0, "market": 60.0, "source": "tcgplayer"},
        nothing,
        nothing,
    ]}
    reader.close()
    store.close()


def test_base_set_first_editions_come_from_the_shadowless_set(tmp_path):
    """Both marketplaces keep Base Set first editions as cards of another set."""
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/expansions"):
            return httpx.Response(200, json=[{"id": 1472, "game_id": 5}, {"id": 1969, "game_id": 5}])
        if request.url.path.endswith("/blueprints/export"):
            shadowless = request.url.params["expansion_id"] == "1969"
            return httpx.Response(200, json=[{
                "id": 134213 if shadowless else 111198,
                "name": "Koffing",
                "fixed_properties": {"collector_number": "051"},
                "card_market_ids": [660177 if shadowless else 273746],
                "tcg_player_id": 107048 if shadowless else 42395,
            }, {
                "id": 1 if shadowless else 2,
                "name": "Only here" if shadowless else "Only there",
                "fixed_properties": {"collector_number": "099"},
                "card_market_ids": [5 if shadowless else 6],
            }])
        blueprint = request.url.params["blueprint_id"]
        listings = (
            [_product(1500, first_edition=True), _product(300)]
            if blueprint == "134213"
            else [_product(130)]
        )
        return httpx.Response(200, json={blueprint: listings})

    reader = CardTrader(
        "token", tmp_path / "cardtrader.sqlite",
        client=httpx.Client(base_url="https://ct.test", transport=httpx.MockTransport(handle)),
    )
    reader.import_map(pause_s=0)
    assert reader.first_edition_product(273746) == 660177
    assert reader.first_edition_product(6) is None
    assert reader.first_edition_product(660177) is None

    catalog = connect(tmp_path / "catalog.sqlite")
    init_catalog(catalog)
    values = {"id": "base1-51", "name": "Koffing", "language": "en", "cardmarket_id": 273746}
    values.update({
        row[1]: "" for row in catalog.execute("PRAGMA table_info(cards)")
        if row[3] and row[4] is None and row[1] not in values
    })
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

    def amounts(**params):
        body = client.get("/api/v1/cardtrader/prices", params={"card_id": "base1-51", **params}).json()
        return [price["amount"] for price in body["prices"]]

    # First edition: the other set's first edition listings only.
    assert amounts(first_edition="true") == [15.0]
    # Unlimited, or no choice: the card's own listings, as before.
    assert amounts(first_edition="false") == [1.3]
    assert amounts() == [1.3]
    reader.close()


def _numbered_reader(tmp_path):
    def blueprint(bid, name, number, languages, ids=(), tcg=None):
        return {
            "id": bid, "name": name, "card_market_ids": list(ids), "tcg_player_id": tcg,
            "fixed_properties": {"collector_number": number},
            "editable_properties": [{"name": "pokemon_language", "possible_values": languages}],
        }

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/expansions"):
            return httpx.Response(200, json=[
                {"id": 2077, "game_id": 5, "name": "Infinity Zone", "code": "s3"},
                {"id": 9, "game_id": 5, "name": "Old Set Sheet", "code": "zz"},
                {"id": 10, "game_id": 5, "name": "Holon Phantoms", "code": "hp"},
            ])
        if request.url.path.endswith("/blueprints/export"):
            expansion = request.url.params["expansion_id"]
            if expansion == "2077":
                return httpx.Response(200, json=[
                    blueprint(1, "Paras", "001/100", ["jp"], tcg=555),
                    blueprint(2, "Eternatus VMAX", "101/100", ["jp"]),
                    blueprint(3, "Eternatus VMAX", "101/100", ["jp"]),
                    blueprint(4, "Parasect", "002/100", ["en", "fr"]),
                    blueprint(5, "Pikachu", "010/100", ["jp"]),
                    blueprint(6, "Pikachu V", "010/100", ["jp"]),
                ])
            if expansion == "9":
                # Listed with Cardmarket ids, and one card without a number.
                return httpx.Response(200, json=[
                    blueprint(20, "Ekans", "", ["jp"], ids=[801]),
                    blueprint(21, "Zubat", "", ["jp"], ids=[802]),
                    blueprint(22, "Grimer", None, ["jp"]),
                ])
            return httpx.Response(200, json=[blueprint(30, "Trapinch", "001", ["jp"])])
        return httpx.Response(200, json={"1": [_product(210, language="jp")]})

    reader = CardTrader(
        "token", tmp_path / "cardtrader.sqlite",
        client=httpx.Client(base_url="https://ct.test", transport=httpx.MockTransport(handle)),
    )
    reader.import_map(pause_s=0)
    return reader


def test_a_set_is_found_by_its_matching_cards_name_code_or_a_close_name(tmp_path):
    reader = _numbered_reader(tmp_path)
    # By name, and by code.
    assert reader.expansions_for([], {"infinityzone"}, "", "ja") == {2077}
    assert reader.expansions_for([], set(), "s3", "ja") == {2077}
    # A name spelt almost the same.
    assert reader.expansions_for([], {"holonphantom"}, "", "ja") == {10}
    # Where most of the set's matching cards are filed, whatever it is called.
    assert reader.expansions_for([801, 802], {"somethingelse"}, "", "ja") == {9}
    assert reader.expansions_for([], {"nothinglikeit"}, "", "ja") == set()
    reader.close()


def test_a_card_without_a_cardmarket_id_is_found_by_number_and_name(tmp_path):
    reader = _numbered_reader(tmp_path)
    zone = {2077}
    assert reader.find(zone, "001", ["parass31"], "ja") == (1, 555)
    # "Pikachu V" is not taken for "Pikachu", nor the other way round.
    assert reader.find(zone, "010", ["pikachuvs3010"], "ja") == (6, None)
    assert reader.find(zone, "10", ["pikachu"], "ja") == (5, None)
    # Another name, two cards the name cannot tell apart, a card that does
    # not exist in Japanese, or no name to check: nothing.
    assert reader.find(zone, "001", ["butterfrees31"], "ja") is None
    assert reader.find(zone, "101", ["eternatusvmaxs3101"], "ja") is None
    assert reader.find(zone, "002", ["parasects32"], "ja") is None
    assert reader.find(zone, "001", [], "ja") is None
    # Listed without a number: by its name alone.
    assert reader.find({9}, "003", ["grimer"], "ja") == (22, None)
    # Used only when the Cardmarket id finds nothing.
    assert reader.prices(481104, "ja", fallback=1)["prices"][0]["amount"] == 2.1
    assert reader.prices(481104, "ja")["matched"] is False
    reader.close()


def test_the_routes_find_a_card_cardtrader_lists_without_a_cardmarket_id(tmp_path):
    from app.tcgplayer import TcgplayerPrices

    reader = _numbered_reader(tmp_path)
    catalog = connect(tmp_path / "catalog.sqlite")
    init_catalog(catalog)
    base = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Infinity-Zone/"
    for card_id, name, number, market_id, url in (
        ("ja:S3-001", "パラス", "001", 481104, base + "Paras-s31"),
        ("ja:S3-055", "なにか", "055", None, None),
    ):
        values = {"id": card_id, "name": name, "language": "ja", "set_id": "S3",
                  "set_name": "Infinity Zone", "collector_number": number,
                  "cardmarket_id": market_id, "cardmarket_url": url}
        values.update({
            row[1]: "" for row in catalog.execute("PRAGMA table_info(cards)")
            if row[3] and row[4] is None and row[1] not in values
        })
        catalog.execute(
            f"INSERT INTO cards ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
            list(values.values()),
        )
    catalog.commit()
    store = TcgplayerPrices(tmp_path / "tcgplayer.sqlite", client=httpx.Client(
        base_url="https://tcg.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    ))
    store._conn.executemany(
        "INSERT INTO listed VALUES (85, 7, 's3', ?, ?, ?)",
        [("1", "paras", 555), ("55", "somecard", 777)],
    )
    store._conn.executemany(
        "INSERT INTO prices VALUES (?, 'Normal', ?, ?, ?)",
        [(555, 1.25, 0.9, 1.3), (777, None, 0.4, 0.6)],
    )
    store._conn.executemany(
        "INSERT INTO meta VALUES (?, ?)",
        [("imported_at", "99999999999"), ("version", "2"), ("priced_at", "2026-11-20T20:06:21+0000")],
    )
    store._conn.commit()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.cardtrader = reader
    app.state.tcgplayer = store
    app.state.dbs = type("Dbs", (), {"catalog": catalog})()
    client = TestClient(app)

    def answer(path, card_id):
        return client.get(f"/api/v1/{path}/prices", params={"card_id": card_id}).json()

    assert [p["amount"] for p in answer("cardtrader", "ja:S3-001")["prices"]] == [2.1]
    assert answer("tcgplayer", "ja:S3-001")["prices"][0] == {
        "label": "Market", "amount": 1.25, "currency": "USD", "source": "tcgplayer",
    }
    # No Cardmarket id and no name in Latin letters: not on CardTrader, but
    # TCGplayer's own set has the number, with a low price and no sales.
    assert answer("cardtrader", "ja:S3-055") == {
        "enabled": True, "matched": False, "count": 0, "prices": [], "observed_at": None,
    }
    assert [p["label"] for p in answer("tcgplayer", "ja:S3-055")["prices"]] == ["Low", "Mid"]
    reader.close()
    store.close()


def test_the_lowest_listing_is_the_last_resort(tmp_path):
    """A product the file has only a lowest listing for is valued at it."""
    from types import SimpleNamespace

    from app.db import connect, init_catalog
    from app.price_sources import import_guide
    from app.routes.cardtrader import TcgplayerCopy, _lowest_listing

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    import_guide(conn, {"createdAt": "2026-11-23T02:00:00+0100", "priceGuides": [
        {"idProduct": 1, "low": 7.5, "low-holo": 9.0},
        {"idProduct": 2, "low": 3.0, "trend": 4.0},
        {"idProduct": 3},
    ]})
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(dbs=SimpleNamespace(catalog=conn))))
    low = lambda product, **copy: _lowest_listing(request, product, TcgplayerCopy(card_id="x", **copy))  # noqa: E731
    assert low(1) == 7.5
    assert low(1, reverse=True) == 9.0
    # The file prices the unlimited print only.
    assert low(1, first_edition=True) is None
    # A product with a trend is never valued at its lowest listing.
    assert low(2) is None
    assert low(3) is None
    assert low(None) is None
