from __future__ import annotations

import json
from pathlib import Path

from app.cardmarket import (
    cardmarket_product_url,
    extract_cardmarket_id,
    fields_from_payload,
    sync_cardmarket_links,
    url_for_row,
)
from app.db import connect, init_catalog


def test_extract_id_from_pricing() -> None:
    payload = {"pricing": {"cardmarket": {"idProduct": 273699}}}
    assert extract_cardmarket_id(payload) == 273699
    assert (
        cardmarket_product_url(
            273699, name="Charizard", set_name="Base Set", provider_id="base1-4"
        )
        == "https://prices.pokemontcg.io/cardmarket/base1-4"
    )
    assert (
        cardmarket_product_url(name="Gengar & Mimikyu GX", set_name="Night Unison")
        == "https://www.cardmarket.com/en/Pokemon/Products/Singles/Night-Unison/Gengar-Mimikyu-GX"
    )
    assert (
        cardmarket_product_url(273699)
        == "https://www.cardmarket.com/en/Pokemon/Products/Search?idProduct=273699"
    )


def test_extract_id_from_variant_third_party() -> None:
    payload = {
        "variants_detailed": [
            {"thirdParty": {"cardmarket": "16123"}},
        ]
    }
    assert extract_cardmarket_id(payload) == 16123


def test_prefers_explicit_pricing_url() -> None:
    payload = {
        "pricing": {
            "cardmarket": {
                "idProduct": 1,
                "url": "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Charizard",
            }
        }
    }
    product_id, url = fields_from_payload(payload)
    assert product_id == 1
    assert url.endswith("/Charizard")


def test_sync_from_cache_without_reloading_images(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.sqlite"
    conn = connect(catalog)
    init_catalog(conn)
    conn.execute(
        """
        INSERT INTO cards (
            id, provider_id, name, set_id, set_name, collector_number,
            language, category, rarity, illustrator, variants_json, has_image
        ) VALUES ('base1-4', 'base1-4', 'Charizard', 'base1', 'Base Set', '4',
                  'en', 'Pokemon', 'Rare', NULL, '{}', 1)
        """
    )
    conn.commit()
    cache = tmp_path / "cache" / "cards"
    cache.mkdir(parents=True)
    (cache / "base1-4.json").write_text(
        json.dumps(
            {
                "id": "base1-4",
                "pricing": {"cardmarket": {"idProduct": 273699}},
            }
        )
    )

    updated = sync_cardmarket_links(tmp_path, conn)
    row = conn.execute("SELECT * FROM cards").fetchone()
    assert updated == 1
    assert row["cardmarket_id"] == 273699
    assert url_for_row(row) == "https://prices.pokemontcg.io/cardmarket/base1-4"
