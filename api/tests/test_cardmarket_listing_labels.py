"""Names for Cardmarket listings that Cardmarket only numbers (V1, V2, V3)."""

import collections
import csv
import importlib.util
import re
from pathlib import Path

from app.cardmarket import _LISTING_LABELS_FILE, variant_record

BASE = "https://www.cardmarket.com/en/Pokemon/Products/Singles"
_spec = importlib.util.spec_from_file_location(
    "name_numbered_listings", Path(__file__).resolve().parents[1] / "scripts" / "name_numbered_listings.py")
names = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(names)


def _shipped():
    with open(_LISTING_LABELS_FILE, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _listing(url, pid=None, primary=False):
    expansion = url.split("/")[0]
    return {"url": f"{BASE}/{url}", "expansion": expansion, "pid": pid, "primary": primary}


def _variant(pid, type_="holo", stamp=None, foil=None, size="standard"):
    return {"type": type_, "stamp": stamp, "foil": foil, "size": size, "thirdParty": {"cardmarket": pid}}


def _labels(listings, variants=(), guide=None):
    found = names.name_card(listings, list(variants), guide or {})
    return {url.split("/Singles/")[1]: label for url, (label, _) in found.items()}


def test_the_shipped_file():
    rows = _shipped()
    assert len(rows) == 1067
    assert len({row["url"] for row in rows}) == len(rows)
    for row in rows:
        assert row["label"] and len(row["label"]) <= 40 and not re.search(r"\bV\d", row["label"])
        assert row["rule"].split()[0] in {"reviewed", "tcgdex", "mcdonalds", "expansion", "own", "photo+tcgdex", "photo"}
    per_card = collections.defaultdict(list)
    for row in rows:
        per_card[row["card_id"]].append(row["label"])
    assert all(len(set(labels)) == len(labels) for labels in per_card.values())


def test_shipped_names_reach_the_version_tiles():
    def label(path):
        return variant_record({"url": f"{BASE}/{path}", "name": "x"})["label"]

    assert label("151/Bulbasaur-V1-MEW001") == "Normal"
    assert label("151/Bulbasaur-V3-MEW001") == "Set logo stamp"
    assert label("151/Bulbasaur-V4-MEW001") == "Cosmos holo"
    assert label("Professor-Program/Professor-Juniper-PPPBLW-101") == "Professor Program"
    assert label("Black-White/Professor-Juniper-BLW101") == "Normal"
    assert label("McDonalds-Collection-25th-Anniversary/Bulbasaur-V2") == "Holo"


def test_tcgdex_names_a_stamp_by_product_id_when_the_price_agrees():
    listings = [_listing("151/Bulbasaur-V1-MEW001", 1, primary=True), _listing("151/Bulbasaur-V3-MEW001", 3),
                _listing("151/Bulbasaur-V4-MEW001", 4)]
    variants = [_variant(1, "normal"), _variant(1, "reverse"), _variant(3, "normal", stamp=["set-logo"]),
                _variant(4, "reverse", foil="cosmos")]
    guide = {1: {"trend": 0.15}, 3: {"trend": 80}, 4: {"trend": 0.10}}
    # The cosmos holo trends below the plain card, so TCGdex is not trusted for it.
    assert _labels(listings, variants, guide) == {
        "151/Bulbasaur-V1-MEW001": "Normal", "151/Bulbasaur-V3-MEW001": "Set logo stamp"}


def test_tcgdex_is_ignored_where_it_contradicts_itself():
    listings = [_listing("Obsidian-Flames/Froakie-V1-OBF056", 1), _listing("Obsidian-Flames/Froakie-V2-OBF056", 2, primary=True)]
    variants = [_variant(1, "reverse"), _variant(2, "holo", foil="cosmos"), _variant(2, "normal")]
    assert _labels(listings, variants, {1: {"trend": 0.03}, 2: {"trend": 0.32}}) == {}


def test_an_unknown_stamp_keeps_its_number():
    listings = [_listing("Surging-Sparks/Terapagos-V1-SSP161", 1, primary=True), _listing("Surging-Sparks/Terapagos-V2-SSP161", 2)]
    variants = [_variant(1), _variant(2, stamp=["michael-pramawat"])]
    assert _labels(listings, variants, {1: {"trend": 1}, 2: {"trend": 9}}) == {"Surging-Sparks/Terapagos-V1-SSP161": "Normal"}


def test_mcdonalds_v1_is_the_non_holo_and_v2_the_holo():
    listings = [_listing("McDonalds-Collection-25th-Anniversary/Bulbasaur-V1", primary=True),
                _listing("McDonalds-Collection-25th-Anniversary/Bulbasaur-V2")]
    assert _labels(listings) == {"McDonalds-Collection-25th-Anniversary/Bulbasaur-V1": "Non-holo",
                                 "McDonalds-Collection-25th-Anniversary/Bulbasaur-V2": "Holo"}


def test_another_expansion_names_the_listing_and_the_card_is_normal():
    listings = [_listing("Black-White/Professor-Juniper-BLW101", primary=True),
                _listing("Professor-Program/Professor-Juniper-PPPBLW-101")]
    assert _labels(listings) == {"Black-White/Professor-Juniper-BLW101": "Normal",
                                 "Professor-Program/Professor-Juniper-PPPBLW-101": "Professor Program"}


def test_two_listings_with_the_same_name_keep_their_numbers():
    listings = [_listing("Scarlet-Violet/Quaxly-V1-SVI052", primary=True),
                _listing("Southeast-Asia-Promos/Quaxly-V1-SEASVI-052"), _listing("Southeast-Asia-Promos/Quaxly-V2-SEASVI-052")]
    assert _labels(listings) == {}


def test_labels_are_short():
    assert names.special_label(_variant(1, size="jumbo", stamp=["set-logo"])) == "Jumbo, Set logo stamp"
    assert names.special_label(_variant(1, stamp=["set-logo", "staff"])) == "Staff stamp"
    assert names.special_label(_variant(1, stamp=["1st-place", "poke-ball-league"])) == "League 1st place stamp"
    assert names.special_label(_variant(1, "reverse", foil="league")) is None
