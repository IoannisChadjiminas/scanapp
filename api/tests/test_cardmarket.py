from __future__ import annotations

import json
from pathlib import Path

from app.cardmarket import (
    cardmarket_product_url,
    cardmarket_singles_url,
    extract_cardmarket_id,
    fields_from_payload,
    sync_cardmarket_links,
    url_for_row,
    url_from_manifest_card,
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


def test_singles_url_uses_set_code_and_collector() -> None:
    assert (
        cardmarket_singles_url(
            name="Pikachu",
            expansion="Pokemon-Trading-Card-Game-Classic-Charizard-Ho-Oh-ex-Deck",
            set_code="CLC",
            collector_number="008/034",
        )
        == "https://www.cardmarket.com/en/Pokemon/Products/Singles/Pokemon-Trading-Card-Game-Classic-Charizard-Ho-Oh-ex-Deck/Pikachu-CLC008"
    )
    assert (
        cardmarket_product_url(name="Pikachu", set_name="McDonald's Collection 2022")
        is None
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


def test_manifest_card_is_one_to_one_with_url() -> None:
    product_id, url = url_from_manifest_card(
        {
            "name": "Pikachu",
            "collector_number": "008/034",
            "cardmarket_expansion": "Pokemon-Trading-Card-Game-Classic-Charizard-Ho-Oh-ex-Deck",
            "cardmarket_set_code": "CLC",
        }
    )
    assert product_id is None
    assert url.endswith("/Pikachu-CLC008")


def test_url_for_row_prefers_stored_product_page(tmp_path: Path) -> None:
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    stored = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "Pokemon-Trading-Card-Game-Classic-Charizard-Ho-Oh-ex-Deck/Pikachu-CLC008"
    )
    conn.execute(
        """
        INSERT INTO cards (
            id, provider_id, name, set_id, set_name, collector_number,
            language, variants_json, has_image, cardmarket_url
        ) VALUES (
            'extra-pikachu-classic-clc008', 'extra-pikachu-classic-clc008',
            'Pikachu', 'clc', 'Classic', '008/034', 'en', '{}', 1, ?
        )
        """,
        (stored,),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM cards").fetchone()
    assert url_for_row(row) == stored


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
