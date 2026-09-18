from __future__ import annotations

import json
from pathlib import Path

from app.cardmarket import (
    cardmarket_product_url,
    cardmarket_singles_url,
    extract_cardmarket_id,
    fields_from_payload,
    is_job_url,
    prices_from_market,
    singles_code_and_number,
    sync_cardmarket_links,
    tcgdex_price_targets,
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
        is None
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


def test_gengar_extra_uses_explicit_tag_bolt_url() -> None:
    product_id, url = url_from_manifest_card(
        {
            "id": "extra-gengar-mimikyu-gx-103-095",
            "name": "Gengar & Mimikyu GX",
            "collector_number": "103/095",
            "cardmarket_id": 558478,
            "cardmarket_url": (
                "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
                "Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102"
            ),
        }
    )
    assert product_id == 558478
    assert url.endswith("/Gengar-Mimikyu-GX-V2-sm9102")


def test_extra_manifest_verified_singles_urls() -> None:
    from app.cardmarket import is_verified_singles_url, mapping_from_manifest

    manifest_path = Path(__file__).resolve().parents[2] / "extra-cards" / "manifest.json"
    cards = json.loads(manifest_path.read_text())["cards"]
    expected = {
        "extra-blaziken-vmax-217-184": (
            "/VMAX-Climax/Blaziken-VMAX-V2-s8b217"
        ),
        "extra-charmander-001-032": (
            "/Pokemon-Card-Game-Classic-Charizard-Ho-Oh-ex-Deck/Charmander-CLL001"
        ),
        "extra-gengar-mimikyu-gx-103-095": (
            "/Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102"
        ),
        "extra-pikachu-mcdonalds-2022-008-015": (
            "/McDonalds-Collection-2022/Pikachu-MCD227"
        ),
        "extra-pikachu-classic-clc008": (
            "/Pokemon-Trading-Card-Game-Classic-Charizard-Ho-Oh-ex-Deck/Pikachu-CLC008"
        ),
    }
    by_id = {card["id"]: card for card in cards}
    assert by_id["extra-lugia-v-326-s-p"]["collector_number"] == "324/S-P"
    assert by_id["extra-m-tyranitar-ex-089-081"]["set_id"] == "xy7"
    for card_id, suffix in expected.items():
        mapping = mapping_from_manifest(by_id[card_id])
        assert mapping.verified
        assert mapping.url.endswith(suffix)
        assert is_verified_singles_url(mapping.url)
    for card_id in ("extra-lugia-v-326-s-p", "extra-m-tyranitar-ex-089-081"):
        mapping = mapping_from_manifest(by_id[card_id])
        assert mapping.url is None
        assert mapping.verified is False


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
            language, variants_json, has_image, cardmarket_url,
            cardmarket_verified, cardmarket_provenance, cardmarket_verified_at
        ) VALUES (
            'extra-pikachu-classic-clc008', 'extra-pikachu-classic-clc008',
            'Pikachu', 'clc', 'Classic', '008/034', 'en', '{}', 1, ?,
            1, 'manifest-url', '2026-09-17T00:00:00Z'
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
    assert url_for_row(row) is None
    assert int(row["cardmarket_verified"] or 0) == 0


def test_prices_from_market_are_from_trend_and_7day() -> None:
    prices = prices_from_market(
        {
            "unit": "EUR",
            "low": 129.9,
            "trend": 233.74,
            "avg7": 224.14,
            "avg": 239.83,
        }
    )
    assert [item["label"] for item in prices] == ["From", "Trend", "7-day"]
    assert prices[0]["amount"] == 129.9
    assert prices[0]["currency"] == "EUR"


def test_price_targets_prefer_singles_slug() -> None:
    assert singles_code_and_number(
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102"
    ) == ("sm9", "102")
    blaziken = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "VMAX-Climax/Blaziken-VMAX-V2-s8b217"
    )
    assert is_job_url(blaziken)
    targets = tcgdex_price_targets(
        {
            "id": "extra-gengar-mimikyu-gx-103-095",
            "provider_id": "extra-gengar-mimikyu-gx-103-095",
            "language": "ja",
            "set_id": "sm9",
            "collector_number": "103/095",
            "cardmarket_url": (
                "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
                "Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102"
            ),
        }
    )
    assert targets[0] == ("ja", "sm9-102")


def test_normalize_and_snapshot_roundtrip(tmp_path: Path) -> None:
    from app.cardmarket import (
        normalize_product_url,
        save_snapshot,
        snapshot_prices,
    )
    from app.cardmarket_queue import claim_job, enqueue_job

    dirty = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102?utm_source=x#offers"
    )
    key = normalize_product_url(dirty)
    assert key.endswith("/Gengar-Mimikyu-GX-V2-sm9102")
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    job_id = enqueue_job(conn, dirty, "extra-gengar")
    assert enqueue_job(conn, key, "extra-gengar") == job_id
    claimed = claim_job(conn, "helper-a")
    assert claimed is not None
    assert claimed["id"] == job_id
    assert claimed["claim_token"]
    assert claim_job(conn, "helper-a")["id"] == job_id
    assert claim_job(conn, "helper-b") is None
    prices = [{"label": "NM", "amount": 449.99, "currency": "EUR"}]
    save_snapshot(conn, dirty, prices)
    assert snapshot_prices(conn, key) == prices


def test_job_retries_up_to_three_times(tmp_path: Path) -> None:
    from app.cardmarket_queue import claim_job, enqueue_job, retry_or_fail_job

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    job_id = enqueue_job(
        conn,
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102",
        "extra-gengar",
    )
    helper = "helper-a"
    for _ in range(2):
        claimed = claim_job(conn, helper)
        assert claimed is not None
        assert claimed["id"] == job_id
        assert retry_or_fail_job(
            conn,
            job_id,
            helper_id=helper,
            claim_token=claimed["claim_token"],
            reason="network",
        ) == "pending"
        conn.execute(
            "UPDATE cardmarket_jobs SET next_attempt_at = '2020-01-01T00:00:00Z' WHERE id = ?",
            (job_id,),
        )
        conn.commit()
    claimed = claim_job(conn, helper)
    assert claimed is not None
    assert (
        retry_or_fail_job(
            conn,
            job_id,
            helper_id=helper,
            claim_token=claimed["claim_token"],
            reason="network",
        )
        == "failed"
    )
    assert claim_job(conn, helper) is None


def test_stale_claim_does_not_burn_retries(tmp_path: Path) -> None:
    from app.cardmarket_queue import claim_job, enqueue_job

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    job_id = enqueue_job(
        conn,
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102",
        "extra-gengar",
    )
    first = claim_job(conn, "helper-a")
    assert first is not None
    conn.execute(
        "UPDATE cardmarket_jobs SET claim_expires_at = '2020-01-01T00:00:00Z' WHERE id = ?",
        (job_id,),
    )
    conn.commit()
    again = claim_job(conn, "helper-b")
    assert again is not None
    assert again["id"] == job_id
    row = conn.execute(
        "SELECT status, attempts, helper_id FROM cardmarket_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    assert row is not None
    assert row["status"] == "claimed"
    assert int(row["attempts"] or 0) == 0
    assert row["helper_id"] == "helper-b"


def test_helper_online_after_ping(tmp_path: Path) -> None:
    from app.cardmarket_queue import helper_is_online, issue_helper_credential, update_helper_status

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    assert helper_is_online(conn) is False
    helper_id, _token = issue_helper_credential(conn)
    update_helper_status(conn, helper_id, ready=True)
    assert helper_is_online(conn) is True


def test_prices_for_row_prefers_snapshot(tmp_path: Path) -> None:
    from app.cardmarket import prices_for_row, save_snapshot

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    url = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102"
    )
    save_snapshot(
        conn,
        url,
        [{"label": "NM", "amount": 449.99, "currency": "EUR"}],
    )
    found = prices_for_row({"id": "extra-gengar", "cardmarket_url": url}, catalog=conn)
    assert found == [{"label": "NM", "amount": 449.99, "currency": "EUR"}]


def test_job_url_accepts_pokemontcg_price_link() -> None:
    from app.cardmarket import is_job_url

    assert is_job_url(
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102"
    )
    assert is_job_url(
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/VMAX-Climax/Blaziken-VMAX-V2-s8b217"
    )
    assert is_job_url(
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/McDonalds-Collection-2022/Pikachu"
    )
    assert is_job_url("https://prices.pokemontcg.io/cardmarket/base1-4")
    assert not is_job_url("https://www.cardmarket.com/en/Pokemon/Cards")
    assert not is_job_url(
        "https://www.cardmarket.com/en/Pokemon/Products/Search?searchString=Blaziken"
    )


def test_helper_map_saves_verified_singles_url(tmp_path: Path) -> None:
    from app.cardmarket import map_card_product, url_for_row
    from app.db import connect, init_catalog

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    conn.execute(
        """
        INSERT INTO cards (
            id, provider_id, name, set_id, set_name, collector_number,
            language, variants_json, has_image
        ) VALUES (
            'extra-lugia-v-326-s-p', 'extra-lugia-v-326-s-p', 'Lugia V', 's-p',
            'SWSH Promo', '324/S-P', 'ja', '{}', 1
        )
        """
    )
    conn.commit()
    url = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "SWSH-Promos/Lugia-V-sP324?utm_source=x"
    )
    mapped = map_card_product(conn, tmp_path, "extra-lugia-v-326-s-p", url)
    assert mapped["verified"] is True
    assert mapped["url"].endswith("/Lugia-V-sP324")
    row = conn.execute(
        "SELECT * FROM cards WHERE id = 'extra-lugia-v-326-s-p'"
    ).fetchone()
    assert url_for_row(row) == mapped["url"]
    assert row["cardmarket_provenance"] == "helper-map"


def test_helper_map_rejects_search_and_unknown_card(tmp_path: Path) -> None:
    from app.cardmarket import MappingError, map_card_product
    from app.db import connect, init_catalog

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    conn.execute(
        """
        INSERT INTO cards (
            id, provider_id, name, set_id, set_name, collector_number,
            language, variants_json, has_image
        ) VALUES (
            'extra-lugia-v-326-s-p', 'extra-lugia-v-326-s-p', 'Lugia V', 's-p',
            'SWSH Promo', '324/S-P', 'ja', '{}', 1
        )
        """
    )
    conn.commit()
    try:
        map_card_product(
            conn,
            tmp_path,
            "extra-lugia-v-326-s-p",
            "https://www.cardmarket.com/en/Pokemon/Products/Search?searchString=Lugia",
        )
        raise AssertionError("search URL must not map")
    except MappingError as exc:
        assert exc.status_code == 400
    try:
        map_card_product(
            conn,
            tmp_path,
            "missing-card",
            "https://www.cardmarket.com/en/Pokemon/Products/Singles/SWSH-Promos/Lugia-V-sP324",
        )
        raise AssertionError("unknown card must not map")
    except MappingError as exc:
        assert exc.status_code == 404


def test_job_url_rejects_set_list() -> None:
    from app.cardmarket_queue import classify_url

    set_list = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt"
    assert classify_url(set_list) == "expansion"
    assert classify_url(f"{set_list}?site=2") == "expansion"
    assert (
        classify_url(
            "https://www.cardmarket.com/en/Pokemon/Products/Singles/Challenge-from-the-Darkness"
        )
        == "expansion"
    )
    assert (
        classify_url(
            "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
            "Challenge-from-the-Darkness/Pikachu-V4"
        )
        == "product"
    )
    assert not is_job_url(set_list)
    assert is_job_url(
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102"
    )


def test_expansion_import_links_unique_name_and_number(tmp_path: Path) -> None:
    from app.cardmarket import import_expansion_products, url_for_row
    from app.db import connect, init_catalog

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    conn.execute(
        """
        INSERT INTO cards (
            id, provider_id, name, set_id, set_name, collector_number,
            language, variants_json, has_image
        ) VALUES
        (
            'extra-clc008', 'extra-clc008', 'Pikachu', 'clc',
            'Pokemon Trading Card Game Classic Charizard Ho-Oh ex Deck',
            '008/034', 'en', '{}', 1
        ),
        (
            'extra-gengar', 'extra-gengar', 'Gengar & Mimikyu GX', 'sm9',
            'Tag Bolt', '103/095', 'ja', '{}', 1
        )
        """
    )
    conn.commit()
    pikachu = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "Pokemon-Trading-Card-Game-Classic-Charizard-Ho-Oh-ex-Deck/Pikachu-CLC008"
    )
    gengar = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102"
    )
    result = import_expansion_products(
        conn,
        tmp_path,
        page_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/Tag-Bolt",
        products=[
            {"url": pikachu, "name": "Pikachu"},
            {"url": gengar, "name": "Gengar & Mimikyu GX"},
        ],
        source="page",
    )
    assert result["stored"] == 2
    assert result["linked"] == 1
    assert result["unmatched"] == 1
    assert result["links"][0]["card_id"] == "extra-clc008"
    assert gengar in result["unmatched_urls"]
    pikachu_row = conn.execute("SELECT * FROM cards WHERE id = 'extra-clc008'").fetchone()
    gengar_row = conn.execute("SELECT * FROM cards WHERE id = 'extra-gengar'").fetchone()
    assert url_for_row(pikachu_row) == pikachu
    assert pikachu_row["cardmarket_provenance"] == "helper-expansion"
    assert url_for_row(gengar_row) is None
    stored = conn.execute("SELECT url, matched FROM cardmarket_expansion_products ORDER BY url").fetchall()
    assert {row["url"]: row["matched"] for row in stored}[gengar] == 0
    dumps = list((tmp_path / "expansion-imports").glob("*.json"))
    assert dumps


def test_marks_and_lists_completed_expansion_crawls(tmp_path: Path) -> None:
    from app.cardmarket import import_expansion_products, list_expansion_crawls, mark_expansion_complete
    from app.db import connect, init_catalog

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    product = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Bulbasaur-V1-MEW001"
    )
    import_expansion_products(
        conn,
        tmp_path,
        page_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/151",
        products=[{"url": product, "name": "Bulbasaur"}],
        source="crawl",
    )
    mark_expansion_complete(
        conn,
        expansion="151",
        expansion_id="2770",
        page_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/151",
    )
    mark_expansion_complete(
        conn,
        expansion="Battle Party Set",
        expansion_id="6549",
        page_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/Battle-Party-Set",
    )
    rows = list_expansion_crawls(conn)
    keys = {row["key"] for row in rows}
    assert "151" in keys
    assert "2770" in keys
    assert "Battle Party Set" in keys
    assert "Battle-Party-Set" in keys
    assert "6549" in keys
    assert all(row["complete"] for row in rows)


def test_backfill_marks_older_stored_sets_complete(tmp_path: Path) -> None:
    from app.cardmarket import import_expansion_products, list_expansion_crawls
    from app.db import connect, init_catalog

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    first = "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Bulbasaur-V1-MEW001"
    second = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "Cyber-Judge/Pikachu-V4"
    )
    import_expansion_products(
        conn,
        tmp_path,
        page_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/151",
        products=[{"url": first, "name": "Bulbasaur"}],
        source="crawl",
    )
    import_expansion_products(
        conn,
        tmp_path,
        page_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/Cyber-Judge",
        products=[{"url": second, "name": "Pikachu"}],
        source="crawl",
    )
    rows = {row["expansion"]: row for row in list_expansion_crawls(conn)}
    assert rows["151"]["complete"] is True
    assert rows["151"]["products"] >= 1
    assert rows["Cyber-Judge"]["complete"] is False


def test_relink_writes_url_after_catalogue_card_exists(tmp_path: Path) -> None:
    from app.cardmarket import apply_cardmarket_links, url_for_row
    from app.db import connect, init_catalog

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    product = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "Pokemon-Trading-Card-Game-Classic-Charizard-Ho-Oh-ex-Deck/Pikachu-CLC008"
    )
    dump_dir = tmp_path / "expansion-imports"
    dump_dir.mkdir()
    (dump_dir / "classic-page.json").write_text(
        json.dumps(
            {
                "page_url": (
                    "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
                    "Pokemon-Trading-Card-Game-Classic-Charizard-Ho-Oh-ex-Deck"
                ),
                "source": "page",
                "expansion": "Pokemon-Trading-Card-Game-Classic-Charizard-Ho-Oh-ex-Deck",
                "products": [{"url": product, "name": "Pikachu"}],
            }
        )
    )
    first = apply_cardmarket_links(conn, tmp_path)
    assert first["dumps"] == 1
    assert first["expansion_linked"] == 0
    conn.execute(
        """
        INSERT INTO cards (
            id, provider_id, name, set_id, set_name, collector_number,
            language, variants_json, has_image
        ) VALUES (
            'extra-clc008', 'extra-clc008', 'Pikachu', 'clc',
            'Pokemon Trading Card Game Classic Charizard Ho-Oh ex Deck',
            '008/034', 'en', '{}', 1
        )
        """
    )
    conn.commit()
    second = apply_cardmarket_links(conn, tmp_path)
    assert second["expansion_linked"] == 1
    row = conn.execute("SELECT * FROM cards WHERE id = 'extra-clc008'").fetchone()
    assert url_for_row(row) == product
    maps = json.loads((tmp_path / "cardmarket-maps.json").read_text())
    assert maps["cards"]["extra-clc008"]["cardmarket_url"] == product

