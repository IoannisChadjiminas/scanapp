"""A product number shared by cards on different Cardmarket pages prices no
card until its owner is known."""

import json

from app import card_products
from app.cardmarket import remember_listing_product
from app.db import connect, init_catalog
from app.price_sources import best_prices, guide_trend_for_url, import_guide

BASE = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Phantom-Forces/"
GUIDE = {"createdAt": "2026-11-23T02:00:00+0100", "priceGuides": [
    {"idProduct": 100, "low": 9.0, "trend": 12.0, "avg7": 11.0},
    {"idProduct": 200, "low": 150.0, "trend": 220.0, "avg7": 210.0},
    {"idProduct": 300, "low": 1.0, "trend": 2.0, "avg7": 2.0},
]}


def _catalog(tmp_path):
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    for card, number, product in (("en:a-34", "34", 100), ("en:a-114", "114", 100), ("en:a-1", "1", 300)):
        conn.execute(
            "INSERT INTO cards (id, provider_id, name, set_id, set_name, collector_number, language,"
            " variants_json, cardmarket_id, cardmarket_url) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (card, card, "Gengar EX", "a", "Phantom Forces", number, "en",
             json.dumps({"normal": True}), product, f"{BASE}Gengar-EX-PHF{number}"),
        )
    conn.commit()
    import_guide(conn, GUIDE)
    return conn


def _trend(conn, card):
    return {price["label"]: price["amount"] for price in best_prices(conn, card, None)}.get("Trend")


def test_a_shared_number_prices_neither_card(tmp_path):
    conn = _catalog(tmp_path)
    # As the catalogue gives it: the full art shows the regular card's price.
    assert _trend(conn, "en:a-34") == _trend(conn, "en:a-114") == 12.0
    assert card_products.withhold_shared(conn) == 2
    assert _trend(conn, "en:a-34") is None
    assert _trend(conn, "en:a-114") is None
    assert guide_trend_for_url(conn, f"{BASE}Gengar-EX-PHF114")[0] is None
    # A card with a number of its own is untouched.
    assert _trend(conn, "en:a-1") == 2.0


def test_a_read_page_names_its_cards_product(tmp_path):
    conn = _catalog(tmp_path)
    card_products.withhold_shared(conn)
    photo = "https://product-images.s3.cardmarket.com/51/PHF/{0}/{0}.jpg"
    remember_listing_product(conn, f"{BASE}Gengar-EX-PHF34?language=1", photo.format(100))
    assert _trend(conn, "en:a-34") == 12.0
    # The other card is still nobody's, until its own page is read.
    assert _trend(conn, "en:a-114") is None
    remember_listing_product(conn, f"{BASE}Gengar-EX-PHF114", photo.format(200))
    assert _trend(conn, "en:a-114") == 220.0
    # A restart keeps what the pages said.
    assert card_products.withhold_shared(conn) == 0
    assert _trend(conn, "en:a-34") == 12.0
    assert _trend(conn, "en:a-114") == 220.0


def test_a_reviewed_correction_outranks_the_rest(tmp_path):
    conn = _catalog(tmp_path)
    card_products.apply_review(conn, {"en:a-114": 200, "en:a-34": 100})
    assert card_products.withhold_shared(conn) == 0
    assert _trend(conn, "en:a-34") == 12.0
    assert _trend(conn, "en:a-114") == 220.0
