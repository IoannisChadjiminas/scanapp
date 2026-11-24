"""Poké Ball, Master Ball and other reverse patterns sold as their own products."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import pattern_products
from app.cardmarket import variants_for_row
from app.config import get_settings
from app.db import connect, init_catalog
from app.pattern_products import apply_reviewed_file, read_reviewed
from app.price_sources import import_guide, product_id_for_url, trend_for_url

BASE = "https://www.cardmarket.com/en/Pokemon/Products/Singles"
MAIN = f"{BASE}/Prismatic-Evolutions/Exeggcute-PRE001"
POKE = f"{BASE}/Prismatic-Evolutions-Additionals/Exeggcute-V1-xPRE001"
MASTER = f"{BASE}/Prismatic-Evolutions-Additionals/Exeggcute-V2-xPRE001"
IMG = "https://product-images.s3.cardmarket.com/51/xPRE/{0}/{0}.jpg"


def _catalog(tmp_path):
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    conn.execute(
        "INSERT INTO cards (id, provider_id, name, set_id, set_name, collector_number, language,"
        " variants_json, cardmarket_id, cardmarket_url) VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("en:sv08.5-001", "sv08.5-001", "Exeggcute", "sv08.5", "Prismatic Evolutions", "001", "en",
         json.dumps({"normal": True, "reverse": True}), 805390, MAIN),
    )
    conn.commit()
    return conn


def _file(tmp_path, rows):
    path = tmp_path / "patterns.csv"
    lines = ["card_id,pattern,product_id,url,image"]
    lines += [f"en:sv08.5-001,{pattern},{product},{url},{IMG.format(product)}" for pattern, product, url in rows]
    path.write_text("\n".join(lines) + "\n")
    return path


ROWS = [("pokeball", 806408, POKE), ("masterball", 806409, MASTER)]


def test_patterns_are_versions_after_the_card_itself(tmp_path):
    conn = _catalog(tmp_path)
    assert apply_reviewed_file(conn, _file(tmp_path, ROWS)) == 2
    row = conn.execute("SELECT * FROM cards WHERE id = 'en:sv08.5-001'").fetchone()
    found = variants_for_row(conn, row)
    assert [(v["url"], v["label"]) for v in found] == [
        (MAIN, "Normal"), (POKE, "Poké Ball"), (MASTER, "Master Ball"),
    ]
    assert found[2]["image"] == "/api/v1/cardmarket/listing-images/806409.jpg"


def test_each_pattern_is_priced_from_its_own_product(tmp_path):
    conn = _catalog(tmp_path)
    apply_reviewed_file(conn, _file(tmp_path, ROWS))
    import_guide(conn, {"version": 1, "createdAt": "2026-11-24T02:00:00+0100", "priceGuides": [
        {"idProduct": 805390, "low": 0.02, "trend": 0.03},
        {"idProduct": 806408, "low": 0.02, "trend": 0.25},
        # Sellers file the Master Ball copies as reverse holos: the plain trend is empty.
        {"idProduct": 806409, "low": 0.7, "trend": 0, "trend-holo": 1.74},
    ]})
    assert product_id_for_url(conn, MASTER) == 806409
    assert trend_for_url(conn, POKE) == 0.25
    assert trend_for_url(conn, MASTER) == 1.74
    assert trend_for_url(conn, MAIN) == 0.03


def test_loading_again_replaces_the_list(tmp_path):
    conn = _catalog(tmp_path)
    apply_reviewed_file(conn, _file(tmp_path, ROWS))
    apply_reviewed_file(conn, _file(tmp_path, ROWS[:1]))
    row = conn.execute("SELECT * FROM cards WHERE id = 'en:sv08.5-001'").fetchone()
    assert [v["label"] for v in variants_for_row(conn, row)] == ["Normal", "Poké Ball"]


def test_the_setting_turns_patterns_off(tmp_path, monkeypatch):
    conn = _catalog(tmp_path)
    apply_reviewed_file(conn, _file(tmp_path, ROWS))
    monkeypatch.setattr(get_settings(), "pattern_versions", False)
    row = conn.execute("SELECT * FROM cards WHERE id = 'en:sv08.5-001'").fetchone()
    assert variants_for_row(conn, row) == []


def test_unconfirmed_pattern_is_a_ball_pattern():
    assert pattern_products.label("", f"{BASE}/MEGA-Dream-ex-Additionals/Charcadet-V2-xm2a030") == "Ball pattern"
    assert pattern_products.label("team-rocket", POKE) == "Team Rocket"


def test_a_pattern_photo_is_saved_on_first_request(tmp_path, monkeypatch):
    from app.routes.cardmarket import listing_image

    conn = _catalog(tmp_path)
    apply_reviewed_file(conn, _file(tmp_path, ROWS))
    asked = []

    def fake_fetch(source, target):
        asked.append(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\xff\xd8\xffjpeg")
        return True

    monkeypatch.setattr(pattern_products, "fetch_image", fake_fetch)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        settings=SimpleNamespace(data_dir=str(tmp_path)), dbs=SimpleNamespace(catalog=conn))))
    response = listing_image("806409", request)
    assert Path(response.path).read_bytes() == b"\xff\xd8\xffjpeg"
    listing_image("806409", request)  # cached: no second fetch
    assert asked == [IMG.format(806409)]
    with pytest.raises(HTTPException):
        listing_image("123", request)  # not a pattern product


def test_the_shipped_list():
    rows = read_reviewed()
    assert len(rows) == 1746
    by_product = {row["product_id"]: row for row in rows}
    # Cardmarket's V1 is the Poké Ball even where TCGdex says otherwise (White Flare Swadloon).
    assert by_product[836496]["pattern"] == "pokeball" and "-V1-" in by_product[836496]["url"]
    assert by_product[837231]["card_id"] == "ja:SV2a-001" and by_product[837231]["pattern"] == "masterball"


def test_mega_dream_patterns_are_named_from_their_photos():
    by_product = {row["product_id"]: row for row in read_reviewed()}
    assert by_product[861527]["pattern"] == "pokeball"  # Ethan's Pinsir
    assert by_product[861529]["pattern"] == "quickball"  # Yanma
    assert by_product[861583]["pattern"] == "team-rocket"  # Team Rocket's Articuno
    unnamed = sorted(row["card_id"] for row in read_reviewed() if not row["pattern"])
    assert unnamed == ["ja:M2a-030", "ja:M2a-140"]  # no photo on Cardmarket yet


def test_numbered_listings_with_a_reviewed_name():
    from app.cardmarket import variant_record

    tinsel = variant_record({"url": f"{BASE}/Scarlet-Violet-Energies/Basic-Fire-Energy-V2-SVE018",
                             "name": "Basic Fire Energy (SVE 018)From 0,02 €", "card_id": "en:sve-018"})
    winner = variant_record({"url": f"{BASE}/SV-Black-Star-Promos/Pikachu-V6-SVP225",
                             "name": "Pikachu (SVP 225)From 48,00 €", "card_id": "en:svp-225"})
    assert (tinsel["label"], winner["label"]) == ("Tinsel", "League winner stamp")


def test_the_photo_host_mislabels_its_pictures(tmp_path, monkeypatch):
    import httpx

    class Reply:
        status_code = 200
        headers = {"content-type": "multerS3.AUTO_CONTENT_TYPE"}
        content = b"\xff\xd8\xff\xe0 photo"

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: Reply())
    assert pattern_products.fetch_image(IMG.format(806409), tmp_path / "806409.jpg")
    Reply.content = b"<?xml version='1.0'?><Error>AccessDenied</Error>"
    assert not pattern_products.fetch_image(IMG.format(806408), tmp_path / "806408.jpg")


def test_japanese_pattern_cards_have_no_plain_reverse():
    from app.reverse_holos import PATTERN_ONLY, with_reverse

    for card_id in ("ja:SV8a-001", "ja:SV11B-001", "ja:SV11W-001", "ja:M2a-001", "ja:SV2a-001"):
        card = {"id": card_id, "set_id": card_id[3:].split("-")[0], "collector_number": "001",
                "rarity": "Common", "name": "x", "language": "ja"}
        assert card_id in PATTERN_ONLY
        assert with_reverse({"normal": True, "reverse": True}, card)["reverse"] is False
    # English pattern sets keep their plain reverse.
    assert "en:sv08.5-001" not in PATTERN_ONLY
