"""Reverse holos TCGdex leaves out of Black & White, XY and Sun & Moon."""

import json

import pytest

from app import price_sources
from app.db import connect, init_catalog
from app.price_sources import import_guide
from app.reverse_holos import prints_reverse, with_reverse

GUIDE = {
    "version": 1,
    "createdAt": "2026-11-24T02:51:56+0200",
    "priceGuides": [
        {"idProduct": 372381, "low": 0.02, "trend": 0.77, "avg7": 0.66,
         "low-holo": 0.2, "trend-holo": 3.06, "avg7-holo": 2.53},
    ],
}
TCGDEX_PLAIN = {"firstEdition": False, "holo": False, "normal": True, "reverse": False, "wPromo": False}


def _catalog(tmp_path):
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    return conn


def _card(conn, card_id, *, name, set_id, number, rarity, variants=TCGDEX_PLAIN, product=None, language="en"):
    conn.execute(
        "INSERT INTO cards (id, provider_id, name, set_id, set_name, collector_number, language,"
        " rarity, variants_json, cardmarket_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (card_id, card_id, name, set_id, set_id, number, language, rarity, json.dumps(variants), product),
    )
    conn.commit()


def test_cubone_from_unbroken_bonds_offers_reverse_with_its_prices(tmp_path):
    conn = _catalog(tmp_path)
    _card(conn, "en:sm10-90", name="Cubone", set_id="sm10", number="90", rarity="Common", product=372381)
    import_guide(conn, GUIDE)
    picked = price_sources.scan_finishes(conn, "en:sm10-90")
    assert picked["finishes"] == ["normal", "reverse"]
    trend = {p["label"]: p["amount"] for p in picked["reverse_holo_prices"]}["Trend"]
    assert trend == 3.06
    # The plain price is still the normal print.
    plain = {p["label"]: p["amount"] for p in price_sources.best_prices(conn, "en:sm10-90", None)}
    assert plain["Trend"] == 0.77


@pytest.mark.parametrize("set_id,number,rarity,name", [
    ("sm10", "90", "Common", "Cubone"),
    ("xy9", "1", "Uncommon", "Pinsir"),
    ("bw4", "20", "Rare", "Charizard"),
    ("sm115", "68", "Rare", "Ultra Ball"),
    ("ex11", "4", "Rare", "Espeon δ"),
    ("ex16", "50", "Common", "Electrike"),
    ("sm1", "136", "Uncommon", "Double Colorless Energy"),
])
def test_regular_cards_print_a_reverse(set_id, number, rarity, name):
    assert prints_reverse(set_id, number, rarity, name)


@pytest.mark.parametrize("set_id,number,rarity,name,language", [
    ("sm10", "1", "Ultra Rare", "Pheromosa & Buzzwole GX", "en"),
    ("bw10", "11", "Rare", "Genesect-EX", "en"),  # TCGdex files it as a Rare.
    ("g1", "RC2", "Common", "Shroomish", "en"),
    ("bw11", "RC1", "Common", "Snivy", "en"),
    ("sm10", "215", "Common", "Cubone", "en"),  # above the printed total
    ("sm10", "182a", "", "Pokégear 3.0", "en"),
    ("sm5", "99", "Rare", "Lunala ◇", "en"),
    ("xy8", "45", "Rare", "Florges BREAK", "en"),
    ("xy4", "55", "Rare", "M Gengar-EX", "en"),
    ("ex11", "99", "Rare", "Mewtwo ex", "en"),
    ("ex11", "114", "Rare", "Mew ☆", "en"),
    ("bw1", "105", "Common", "Grass Energy", "en"),
    ("g1", "1", "Common", "Venusaur", "en"),  # Generations: no reverse holos
    ("base1", "58", "Common", "Pikachu", "en"),
    ("sm10", "90", "Common", "Cubone", "ja"),
])
def test_cards_without_a_reverse(set_id, number, rarity, name, language):
    assert not prints_reverse(set_id, number, rarity, name, language)


def test_reverse_only_and_listed_variants_stay_as_stored():
    row = {"set_id": "sm10", "collector_number": "90", "rarity": "Common", "name": "Cubone", "language": "en"}
    listed = {"normal": True, "reverse": True}
    assert with_reverse(listed, row) is listed
    nothing = {"normal": False, "holo": False, "reverse": False}
    assert with_reverse(nothing, row) is nothing
    assert with_reverse({"normal": True}, {}) == {"normal": True}


def test_pattern_only_reverse_offers_no_plain_reverse(tmp_path, monkeypatch):
    from app import reverse_holos

    monkeypatch.setattr(reverse_holos, "PATTERN_ONLY", frozenset({"ja:SV2a-001"}))
    conn = _catalog(tmp_path)
    _card(conn, "ja:SV2a-001", name="フシギダネ", set_id="SV2a", number="001", rarity="Common",
          variants={"normal": True, "reverse": True}, product=719442, language="ja")
    import_guide(conn, {**GUIDE, "priceGuides": [
        {"idProduct": 719442, "low": 0.02, "trend": 0.08, "low-holo": 0.1, "trend-holo": 8.33},
    ]})
    assert price_sources.scan_finishes(conn, "ja:SV2a-001") == {"finishes": [], "reverse_holo_prices": []}
    plain = {p["label"]: p["amount"] for p in price_sources.best_prices(conn, "ja:SV2a-001", None)}
    assert plain["Trend"] == 0.08


def test_pattern_only_list_ships_with_the_server():
    from app.reverse_holos import PATTERN_ONLY

    assert "ja:SV2a-001" in PATTERN_ONLY and "en:me02.5-001" in PATTERN_ONLY
    assert "en:sv08.5-001" not in PATTERN_ONLY  # Prismatic Evolutions also has a plain reverse


def test_ex_era_special_energy_has_a_reverse():
    assert prints_reverse("ex11", "103", "Rare", "Darkness Energy")  # Delta Species
    assert prints_reverse("ex16", "88", "Rare", "Metal Energy")  # Power Keepers
    # Holon Phantoms' holo basic Energy and BW's basic Energy have none.
    assert not prints_reverse("ex13", "105", "Rare", "Grass Energy")
    assert not prints_reverse("bw1", "112", "Common", "Darkness Energy")
