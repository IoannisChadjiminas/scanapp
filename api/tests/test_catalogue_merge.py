from pathlib import Path

from app.card_images import backfill_remote_image_urls, display_image_url, tcgdex_display_url
from app.db import connect, init_catalog
from bootstrap.catalogue import upsert_card, _write_catalogue_version


def _card(conn, card_id: str, **overrides) -> None:
    fields = {
        "provider_id": card_id,
        "name": "Pikachu",
        "set_id": "clc",
        "set_name": "Classic",
        "collector_number": "008",
        "language": "en",
        "category": None,
        "rarity": None,
        "illustrator": None,
        "variants_json": "{}",
        "image_path": None,
        "has_image": 0,
        "cardmarket_id": None,
        "cardmarket_url": None,
        "cardmarket_verified": 0,
        "cardmarket_provenance": "none",
        "cardmarket_verified_at": None,
    }
    fields.update(overrides)
    upsert_card(conn, card_id=card_id, **fields)


def test_upsert_keeps_other_cards_and_verified_urls(tmp_path: Path) -> None:
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    _card(
        conn,
        "extra-clc008",
        name="Pikachu",
        cardmarket_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/Classic/Pikachu-CLC008",
        cardmarket_verified=1,
        cardmarket_provenance="helper-map",
    )
    _card(conn, "en:sv03.5-001", name="Bulbasaur", set_id="sv03.5", set_name="151")
    conn.commit()
    _card(
        conn,
        "extra-clc008",
        name="Pikachu",
        cardmarket_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/Wrong/Pikachu-X",
        cardmarket_verified=0,
        cardmarket_provenance="tcgdex-id",
    )
    _card(conn, "en:sv03.5-002", name="Ivysaur", set_id="sv03.5", set_name="151")
    conn.commit()
    ids = {row[0] for row in conn.execute("SELECT id FROM cards")}
    assert ids == {"extra-clc008", "en:sv03.5-001", "en:sv03.5-002"}
    row = conn.execute("SELECT * FROM cards WHERE id = 'extra-clc008'").fetchone()
    assert row["cardmarket_verified"] == 1
    assert row["cardmarket_url"].endswith("/Pikachu-CLC008")
    assert row["cardmarket_provenance"] == "helper-map"


def test_merge_version_keeps_extras(tmp_path: Path) -> None:
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    _card(conn, "en:base1-4", set_id="base1")
    _card(conn, "extra-gengar", set_id="extra")
    conn.commit()
    version = _write_catalogue_version(
        tmp_path,
        conn,
        languages=["en"],
        allowed={"sv03.5"},
        replace=False,
        imported=1,
        indexed=1,
        missing=0,
        per_language={"en": 1},
    )
    assert version.endswith("+extra1")
    payload = (tmp_path / "catalogue-version.json").read_text()
    assert "sv03.5" in payload


def test_display_prefers_tcgdex_url() -> None:
    assert (
        tcgdex_display_url("https://assets.tcgdex.net/en/sv/sv03.5/001")
        == "https://assets.tcgdex.net/en/sv/sv03.5/001/high.webp"
    )
    row = {
        "id": "en:sv03.5-001",
        "has_image": 1,
        "image_path": "/data/reference-images/en/sv03.5-001.webp",
        "remote_image_url": "https://assets.tcgdex.net/en/sv/sv03.5/001/high.webp",
    }
    assert display_image_url(row) == row["remote_image_url"]
    extra = {
        "id": "extra-gengar",
        "has_image": 1,
        "image_path": "/data/reference-images/extra-gengar.jpg",
        "remote_image_url": None,
    }
    assert display_image_url(extra) == "/api/v1/cards/extra-gengar/image"


def test_backfill_remote_url_from_tcgdex_cache(tmp_path: Path) -> None:
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    _card(conn, "en:sv03.5-001", provider_id="sv03.5-001", language="en")
    conn.commit()
    cache = tmp_path / "cache" / "cards" / "en"
    cache.mkdir(parents=True)
    (cache / "sv03.5-001.json").write_text(
        '{"image": "https://assets.tcgdex.net/en/sv/sv03.5/001"}'
    )
    assert backfill_remote_image_urls(conn, tmp_path) == 1
    row = conn.execute(
        "SELECT remote_image_url FROM cards WHERE id = 'en:sv03.5-001'"
    ).fetchone()
    assert row["remote_image_url"].endswith("/sv03.5/001/high.webp")
