"""The reviewed catalogue corrections re-applied on every catalogue load."""

import json
from pathlib import Path

from app import catalogue_corrections
from app.db import connect, init_catalog

DOCS = Path(__file__).resolve().parents[2] / "docs"
SVP = "https://www.cardmarket.com/en/Pokemon/Products/Singles/SV-Black-Star-Promos/Charizard-ex-"


def _catalogue(tmp_path):
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    return conn


def _product(conn, url, card_id, image=None):
    conn.execute(
        "INSERT INTO cardmarket_expansion_products(url,expansion,name,source,card_id,matched,imported_at,listing_image_url)"
        " VALUES (?,?,?,?,?,1,'now',?)", (url, url.split("/")[-2], "x", "crawl", card_id, image))


def test_the_shipped_file_matches_the_rollback_records():
    rows = catalogue_corrections.load()
    unlinked = {r["url"]: r["card_id"] for r in rows if r["action"] == "unlink"}
    for name in ("catalogue-ja-xy-links-20261125.json", "catalogue-foreign-prints-20261125.json",
                 "catalogue-foreign-prints-2-20261125.json"):
        for row in json.loads((DOCS / name).read_text())["unlinked"]:
            assert unlinked.pop(row["url"]) == row["card_id"]
    assert unlinked == {SVP + "V2-SVP196": "en:svp-196"}
    (move,) = [r for r in rows if r["action"] == "replace_url"]
    assert (move["url"], move["new_url"]) == (SVP + "V1-SVP196", SVP + "V3-SVP196")


def test_an_old_catalogue_is_corrected_and_a_corrected_one_is_left_alone(tmp_path):
    conn = _catalogue(tmp_path)
    conn.execute("INSERT INTO cards(id,provider_id,set_id,name,set_name,collector_number,language,cardmarket_id,cardmarket_url)"
                 " VALUES ('en:svp-196','svp-196','svp','Charizard ex','SVP','196','en',821616,?)", (SVP + "V1-SVP196",))
    _product(conn, SVP + "V1-SVP196", "en:svp-196")
    _product(conn, SVP + "V2-SVP196", "en:svp-196")
    foreign = catalogue_corrections.load()[0]
    _product(conn, foreign["url"], foreign["card_id"])

    assert catalogue_corrections.apply(conn) == 4
    assert conn.execute("SELECT cardmarket_url FROM cards").fetchone()[0] == SVP + "V3-SVP196"
    linked = conn.execute("SELECT url,listing_image_url FROM cardmarket_expansion_products WHERE matched=1").fetchall()
    assert [tuple(r) for r in linked] == [(SVP + "V3-SVP196", "https://product-images.s3.cardmarket.com/51/SVP/821616/821616.jpg")]
    assert conn.execute("SELECT count(*) FROM cardmarket_expansion_products WHERE card_id IS NULL").fetchone()[0] == 2

    assert catalogue_corrections.apply(conn) == 0


def test_a_listing_linked_elsewhere_by_a_later_catalogue_is_kept(tmp_path):
    conn = _catalogue(tmp_path)
    foreign = catalogue_corrections.load()[0]
    _product(conn, foreign["url"], "ja:some-card")
    assert catalogue_corrections.apply(conn) == 0
    assert tuple(conn.execute("SELECT card_id,matched FROM cardmarket_expansion_products").fetchone()) == ("ja:some-card", 1)
