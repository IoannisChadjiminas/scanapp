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
        "extra-mew-ex-205-metal": (
            "/151/Mew-ex-V4-MEW205"
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


def test_replace_overwrites_only_that_expansion(tmp_path: Path) -> None:
    from app.cardmarket import import_expansion_products
    from app.db import connect, init_catalog

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    keep = "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Bulbasaur-V1-MEW001"
    drop = "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Old-Card-MEW999"
    other = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Cyber-Judge/Pikachu-V4"
    import_expansion_products(
        conn,
        tmp_path,
        page_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/151",
        products=[{"url": keep, "name": "Bulbasaur"}, {"url": drop, "name": "Old"}],
        source="crawl",
    )
    import_expansion_products(
        conn,
        tmp_path,
        page_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/Cyber-Judge",
        products=[{"url": other, "name": "Pikachu"}],
        source="crawl",
    )
    result = import_expansion_products(
        conn,
        tmp_path,
        page_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/151",
        products=[{"url": keep, "name": "Bulbasaur"}],
        source="crawl",
        replace=True,
    )
    urls = {
        row["url"]
        for row in conn.execute("SELECT url FROM cardmarket_expansion_products").fetchall()
    }
    assert keep in urls
    assert drop not in urls
    assert other in urls
    assert result["removed"] == 1
    assert result["replaced"] is True
    crawl = conn.execute(
        "SELECT complete FROM cardmarket_expansion_crawls WHERE key = '151'"
    ).fetchone()
    assert crawl is not None
    assert crawl["complete"] == 1


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


MEW_V1 = "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Mew-ex-V1-MEW151"
MEW_V2 = "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Mew-ex-V2-MEW193"
MEW_V3 = "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Mew-ex-V3-MEW205"
MEW_V4 = "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Mew-ex-V4-MEW205"
MEW_V5 = "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Mew-ex-V5-MEW205"


def _insert_card(conn, card_id, name, set_name, number, language="en", **extra):
    conn.execute(
        """
        INSERT INTO cards (
            id, provider_id, name, set_id, set_name, collector_number,
            language, variants_json, has_image, cardmarket_url,
            cardmarket_verified, cardmarket_provenance, cardmarket_verified_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
        """,
        (
            card_id,
            card_id,
            name,
            extra.get("set_id") or "sv03.5",
            set_name,
            number,
            language,
            extra.get("variants_json") or "{}",
            extra.get("cardmarket_url"),
            extra.get("verified", 0),
            extra.get("provenance"),
            extra.get("verified_at"),
        ),
    )


def test_sku_groups_mew205_not_151_or_193() -> None:
    from app.cardmarket import product_sku_key

    assert product_sku_key(MEW_V3) == product_sku_key(MEW_V4) == product_sku_key(MEW_V5)
    assert product_sku_key(MEW_V3) == ("151", "MEW", "205")
    assert product_sku_key(MEW_V1) == ("151", "MEW", "151")
    assert product_sku_key(MEW_V2) == ("151", "MEW", "193")


def test_latin_name_slug_ignores_cjk_ex() -> None:
    from app.cardmarket import latin_name_slug

    assert latin_name_slug("ミュウex") is None
    assert latin_name_slug("夢幻ex") is None
    assert latin_name_slug("Mew ex") == "mew-ex"
    assert latin_name_slug("焚焰蚣VMAX") is None
    assert latin_name_slug("Gengar V") == "gengar-v"


def test_localized_expansion_does_not_fit_english_set() -> None:
    from app.cardmarket import name_fits_product_slug, set_fits_expansion

    assert set_fits_expansion("30th", "30th Celebration", "30th-Celebration")
    assert not set_fits_expansion("30th", "30th Celebration", "30th-Celebration-IDTH")
    assert not set_fits_expansion("30th", "30th Celebration", "30th-Celebration-JP")
    assert set_fits_expansion("ex6", "Hidden Legends", "ex-hidden-legends")
    assert name_fits_product_slug("mew", "mew-30c065")
    assert not name_fits_product_slug("mew", "mewtwo-ex-v1-ma6065")
    assert name_fits_product_slug("mewtwo-ex", "mewtwo-ex-v1-30c064")


def test_uncoded_fusion_strike_unique_name(tmp_path: Path) -> None:
    from app.cardmarket import import_expansion_products, url_for_row

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    _insert_card(
        conn,
        "en:swsh8-1",
        "Caterpie",
        "Fusion Strike",
        "1",
        set_id="swsh8",
    )
    _insert_card(
        conn,
        "en:swsh8-100",
        "Pikachu",
        "Fusion Strike",
        "100",
        set_id="swsh8",
    )
    _insert_card(
        conn,
        "en:swsh8-101",
        "Pikachu",
        "Fusion Strike",
        "101",
        set_id="swsh8",
    )
    conn.commit()
    caterpie = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/Fusion-Strike/Caterpie"
    )
    pikachu = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/Fusion-Strike/Pikachu"
    )
    import_expansion_products(
        conn,
        tmp_path,
        page_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/Fusion-Strike",
        products=[
            {"url": caterpie, "name": "Caterpie"},
            {"url": pikachu, "name": "Pikachu"},
        ],
        source="page",
    )
    bug = conn.execute("SELECT * FROM cards WHERE id = 'en:swsh8-1'").fetchone()
    pika_a = conn.execute("SELECT * FROM cards WHERE id = 'en:swsh8-100'").fetchone()
    pika_b = conn.execute("SELECT * FROM cards WHERE id = 'en:swsh8-101'").fetchone()
    assert url_for_row(bug) == caterpie
    assert url_for_row(pika_a) is None
    assert url_for_row(pika_b) is None


def test_unique_link_prefers_english_30c_over_idth(tmp_path: Path) -> None:
    from app.cardmarket import apply_cardmarket_links, import_expansion_products, url_for_row

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    _insert_card(
        conn,
        "en:30th-001",
        "Exeggcute",
        "30th Celebration",
        "001",
        set_id="30th",
        cardmarket_url=(
            "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
            "30th-Celebration-IDTH/Exeggcute-MA6001"
        ),
        provenance="helper-expansion",
        verified=1,
    )
    _insert_card(
        conn,
        "en:30th-065",
        "Mew",
        "30th Celebration",
        "065",
        set_id="30th",
        cardmarket_url=(
            "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
            "30th-Celebration-IDTH/Mewtwo-ex-V1-MA6065"
        ),
        provenance="helper-expansion",
        verified=1,
    )
    conn.commit()
    idth = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "30th-Celebration-IDTH/Exeggcute-MA6001"
    )
    idth_mew = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "30th-Celebration-IDTH/Mewtwo-ex-V1-MA6065"
    )
    en_001 = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "30th-Celebration/Exeggcute-30C001"
    )
    en_065 = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "30th-Celebration/Mew-30C065"
    )
    import_expansion_products(
        conn,
        tmp_path,
        page_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/30th-Celebration-IDTH",
        products=[
            {"url": idth, "name": "Exeggcute (MA6 001)"},
            {"url": idth_mew, "name": "Mewtwo ex (MA6 065)"},
        ],
        source="page",
    )
    import_expansion_products(
        conn,
        tmp_path,
        page_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/30th-Celebration",
        products=[
            {"url": en_001, "name": "Exeggcute (30C 001)"},
            {"url": en_065, "name": "Mew (30C 065)"},
        ],
        source="page",
    )
    stats = apply_cardmarket_links(conn, tmp_path, codes={"30C"})
    assert stats["mismatched_cleared"] >= 1
    egg = conn.execute("SELECT * FROM cards WHERE id = 'en:30th-001'").fetchone()
    mew = conn.execute("SELECT * FROM cards WHERE id = 'en:30th-065'").fetchone()
    assert url_for_row(egg) == en_001
    assert url_for_row(mew) == en_065


def test_ambiguous_mew205_is_not_unique_linked(tmp_path: Path) -> None:
    from app.cardmarket import (
        apply_cardmarket_links,
        import_expansion_products,
        url_for_row,
        variants_for_row,
    )

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    _insert_card(conn, "en:sv03.5-205", "Mew ex", "151", "205")
    _insert_card(
        conn,
        "ja:SV2a-205",
        "ミュウex",
        "ポケモンカード151",
        "205",
        language="ja",
        set_id="SV2a",
    )
    conn.commit()
    import_expansion_products(
        conn,
        tmp_path,
        page_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/151",
        products=[
            {"url": MEW_V1, "name": "Mew ex (MEW 151)From 1,99 €"},
            {"url": MEW_V2, "name": "Mew ex (MEW 193)From 14,90 €"},
            {"url": MEW_V3, "name": "Mew ex (MEW 205)From 13,00 €"},
            {"url": MEW_V4, "name": "Mew ex (MEW 205)From 10,00 €"},
            {"url": MEW_V5, "name": "Mew ex (MEW 205)From 2.400,00 €"},
        ],
        source="page",
    )
    stats = apply_cardmarket_links(conn, tmp_path)
    assert stats["ambiguous_cleared"] >= 0
    paper = conn.execute("SELECT * FROM cards WHERE id = 'en:sv03.5-205'").fetchone()
    ja = conn.execute("SELECT * FROM cards WHERE id = 'ja:SV2a-205'").fetchone()
    assert url_for_row(paper) is None
    assert url_for_row(ja) is None
    variants = variants_for_row(conn, paper)
    slugs = {item["slug"] for item in variants}
    assert slugs == {
        "Mew-ex-V3-MEW205",
        "Mew-ex-V4-MEW205",
        "Mew-ex-V5-MEW205",
    }
    assert "Mew-ex-V1-MEW151" not in slugs
    assert variants_for_row(conn, ja) == []


def test_clears_helper_expansion_but_keeps_manifest_url(tmp_path: Path) -> None:
    from app.cardmarket import apply_cardmarket_links, import_expansion_products, url_for_row

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    _insert_card(
        conn,
        "en:sv03.5-205",
        "Mew ex",
        "151",
        "205",
        cardmarket_url=MEW_V3,
        verified=1,
        provenance="helper-expansion",
        verified_at="2026-09-19T00:00:00Z",
    )
    _insert_card(
        conn,
        "extra-mew-ex-205-metal",
        "Mew ex",
        "151 Ultra-Premium Collection",
        "205",
        cardmarket_url=MEW_V4,
        verified=1,
        provenance="manifest-url",
        verified_at="2026-09-19T00:00:00Z",
        variants_json='{"variant_label": "UPC metal"}',
        set_id="sv03.5-upc",
    )
    conn.commit()
    import_expansion_products(
        conn,
        tmp_path,
        page_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/151",
        products=[
            {"url": MEW_V3, "name": "Mew ex (MEW 205)"},
            {"url": MEW_V4, "name": "Mew ex (MEW 205)"},
            {"url": MEW_V5, "name": "Mew ex (MEW 205)"},
        ],
        source="page",
    )
    apply_cardmarket_links(conn, tmp_path)
    paper = conn.execute("SELECT * FROM cards WHERE id = 'en:sv03.5-205'").fetchone()
    metal = conn.execute(
        "SELECT * FROM cards WHERE id = 'extra-mew-ex-205-metal'"
    ).fetchone()
    assert url_for_row(paper) is None
    assert url_for_row(metal) == MEW_V4


def test_apply_variants_nulls_url_when_ambiguous(tmp_path: Path) -> None:
    from app.cardmarket import apply_variants_to_candidate, import_expansion_products

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    _insert_card(conn, "en:sv03.5-205", "Mew ex", "151", "205")
    conn.commit()
    import_expansion_products(
        conn,
        tmp_path,
        page_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/151",
        products=[
            {"url": MEW_V3, "name": "Mew ex (MEW 205)"},
            {"url": MEW_V4, "name": "Mew ex (MEW 205)"},
            {"url": MEW_V5, "name": "Mew ex (MEW 205)"},
        ],
        source="page",
    )
    item = {
        "card_id": "en:sv03.5-205",
        "cardmarket_url": MEW_V3,
        "cardmarket_prices": [{"label": "From", "amount": 13.0, "currency": "EUR"}],
    }
    apply_variants_to_candidate(conn, item)
    assert item["cardmarket_url"] is None
    assert item["cardmarket_prices"] == []
    assert len(item["cardmarket_variants"]) == 3


def test_resolve_variant_choice_uses_extra_owner(tmp_path: Path) -> None:
    from app.cardmarket import resolve_variant_choice

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    _insert_card(conn, "en:sv03.5-205", "Mew ex", "151", "205")
    _insert_card(
        conn,
        "extra-mew-ex-205-metal",
        "Mew ex",
        "151",
        "205",
        cardmarket_url=MEW_V4,
        verified=1,
        provenance="manifest-url",
        verified_at="2026-09-19T00:00:00Z",
    )
    conn.commit()
    picked = resolve_variant_choice(
        conn, tmp_path, scanned_card_id="en:sv03.5-205", url=MEW_V4
    )
    assert picked["card_id"] == "extra-mew-ex-205-metal"
    assert picked["mapped"] is False
    paper = conn.execute("SELECT cardmarket_url FROM cards WHERE id = 'en:sv03.5-205'").fetchone()
    assert not paper["cardmarket_url"]


def test_resolve_variant_choice_saves_unowned_onto_scanned(tmp_path: Path) -> None:
    from app.cardmarket import resolve_variant_choice, url_for_row

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    _insert_card(conn, "en:sv03.5-205", "Mew ex", "151", "205")
    conn.commit()
    picked = resolve_variant_choice(
        conn, tmp_path, scanned_card_id="en:sv03.5-205", url=MEW_V3
    )
    assert picked["card_id"] == "en:sv03.5-205"
    assert picked["mapped"] is True
    row = conn.execute("SELECT * FROM cards WHERE id = 'en:sv03.5-205'").fetchone()
    assert url_for_row(row) == MEW_V3
    assert row["cardmarket_provenance"] == "helper-map"


def test_ambiguous_pick_stays_on_scan_until_extra_owns_a_sku(tmp_path: Path) -> None:
    from app.cardmarket import import_expansion_products, resolve_variant_choice, url_for_row

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    _insert_card(conn, "en:sv03.5-205", "Mew ex", "151", "205")
    conn.commit()
    import_expansion_products(
        conn,
        tmp_path,
        page_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/151",
        products=[
            {"url": MEW_V3, "name": "Mew ex (MEW 205)"},
            {"url": MEW_V4, "name": "Mew ex (MEW 205)"},
            {"url": MEW_V5, "name": "Mew ex (MEW 205)"},
        ],
        source="page",
    )
    picked = resolve_variant_choice(
        conn, tmp_path, scanned_card_id="en:sv03.5-205", url=MEW_V4
    )
    assert picked["mapped"] is False
    paper = conn.execute("SELECT * FROM cards WHERE id = 'en:sv03.5-205'").fetchone()
    assert url_for_row(paper) is None

    _insert_card(
        conn,
        "extra-mew-ex-205-metal",
        "Mew ex",
        "151",
        "205",
        cardmarket_url=MEW_V4,
        verified=1,
        provenance="manifest-url",
        verified_at="2026-09-19T00:00:00Z",
    )
    conn.commit()
    metal = resolve_variant_choice(
        conn, tmp_path, scanned_card_id="en:sv03.5-205", url=MEW_V4
    )
    assert metal["card_id"] == "extra-mew-ex-205-metal"
    pack = resolve_variant_choice(
        conn, tmp_path, scanned_card_id="en:sv03.5-205", url=MEW_V3
    )
    assert pack["mapped"] is True
    assert pack["card_id"] == "en:sv03.5-205"
    paper = conn.execute("SELECT * FROM cards WHERE id = 'en:sv03.5-205'").fetchone()
    assert url_for_row(paper) == MEW_V3


def test_promo_slug_parses_s_p_and_swsh() -> None:
    from app.cardmarket import product_sku_key, singles_code_and_number

    sp = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "Sword-Shield-Promos/Lugia-V-S-P324"
    )
    swsh_v1 = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "SWSH-Black-Star-Promos/Lugia-V-V1-SWSH301"
    )
    swsh_v2 = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "SWSH-Black-Star-Promos/Lugia-V-V2-SWSH301"
    )
    sit = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "Silver-Tempest/Lugia-V-V1-SIT138"
    )
    assert singles_code_and_number(sp) == ("S-P", "324")
    assert product_sku_key(sp) == ("sword-shield-promos", "S-P", "324")
    assert product_sku_key(swsh_v1) == product_sku_key(swsh_v2)
    assert product_sku_key(swsh_v1) == ("swsh-black-star-promos", "SWSH", "301")
    assert product_sku_key(sit) != product_sku_key(sp)
    mega = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "M-P-Promos/Pikachu-M-P020"
    )
    assert singles_code_and_number(mega) == ("M-P", "20")


def test_slug_parses_digit_prefixed_set_code_30c() -> None:
    from app.cardmarket import product_sku_key, singles_code_and_number

    url = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "30th-Celebration/Mewtwo-ex-V1-30C064"
    )
    assert singles_code_and_number(url) == ("30C", "64")
    assert product_sku_key(url) == ("30th-celebration", "30C", "64")


def test_unique_link_30c064_mewtwo_ex(tmp_path: Path) -> None:
    from app.cardmarket import import_expansion_products, url_for_row

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    _insert_card(
        conn,
        "en:30th-064",
        "Mewtwo ex",
        "30th Celebration",
        "064",
        set_id="30th",
    )
    conn.commit()
    url = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "30th-Celebration/Mewtwo-ex-V1-30C064"
    )
    import_expansion_products(
        conn,
        tmp_path,
        page_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/30th-Celebration",
        products=[{"url": url, "name": "Mewtwo ex (30C 064)"}],
        source="page",
    )
    row = conn.execute("SELECT * FROM cards WHERE id = 'en:30th-064'").fetchone()
    assert url_for_row(row) == url


def test_promo_unique_link_and_swsh301_variants(tmp_path: Path) -> None:
    from app.cardmarket import import_expansion_products, url_for_row, variants_for_row

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    _insert_card(
        conn,
        "extra-lugia-v-326-s-p",
        "Lugia V",
        "SWSH Promo",
        "324/S-P",
        language="ja",
        set_id="s-p",
    )
    _insert_card(
        conn,
        "en:swshp-SWSH301",
        "Lugia V",
        "SWSH Black Star Promos",
        "SWSH301",
        set_id="swshp",
    )
    _insert_card(
        conn,
        "en:swsh12-138",
        "Lugia V",
        "Silver Tempest",
        "138",
        set_id="swsh12",
    )
    conn.commit()
    sp = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "Sword-Shield-Promos/Lugia-V-S-P324"
    )
    v1 = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "SWSH-Black-Star-Promos/Lugia-V-V1-SWSH301"
    )
    v2 = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "SWSH-Black-Star-Promos/Lugia-V-V2-SWSH301"
    )
    sit = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "Silver-Tempest/Lugia-V-V1-SIT138"
    )
    import_expansion_products(
        conn,
        tmp_path,
        page_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/Sword-Shield-Promos",
        products=[
            {"url": sp, "name": "Lugia V (S-P 324)"},
            {"url": v1, "name": "Lugia V (SWSH 301)"},
            {"url": v2, "name": "Lugia V (SWSH 301)"},
            {"url": sit, "name": "Lugia V (SIT 138)"},
        ],
        source="page",
    )
    extra = conn.execute(
        "SELECT * FROM cards WHERE id = 'extra-lugia-v-326-s-p'"
    ).fetchone()
    promo = conn.execute(
        "SELECT * FROM cards WHERE id = 'en:swshp-SWSH301'"
    ).fetchone()
    tempest = conn.execute(
        "SELECT * FROM cards WHERE id = 'en:swsh12-138'"
    ).fetchone()
    assert url_for_row(extra) == sp
    assert url_for_row(promo) is None
    slugs = {item["slug"] for item in variants_for_row(conn, promo)}
    assert slugs == {"Lugia-V-V1-SWSH301", "Lugia-V-V2-SWSH301"}
    assert url_for_row(tempest) == sit
    assert variants_for_row(conn, extra) == []
    assert variants_for_row(conn, tempest) == []


def test_link_promo_codes_skips_regular_set_sku(tmp_path: Path) -> None:
    from app.cardmarket import apply_cardmarket_links, url_for_row

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    _insert_card(
        conn,
        "extra-lugia-v-326-s-p",
        "Lugia V",
        "SWSH Promo",
        "324/S-P",
        language="ja",
        set_id="s-p",
    )
    _insert_card(
        conn,
        "extra-clc008",
        "Pikachu",
        "Pokemon Trading Card Game Classic Charizard Ho-Oh ex Deck",
        "008/034",
        set_id="clc",
    )
    conn.commit()
    dump_dir = tmp_path / "expansion-imports"
    dump_dir.mkdir()
    (dump_dir / "mix.json").write_text(
        json.dumps(
            {
                "page_url": (
                    "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
                    "Sword-Shield-Promos"
                ),
                "source": "page",
                "products": [
                    {
                        "url": (
                            "https://www.cardmarket.com/en/Pokemon/Products/"
                            "Singles/Sword-Shield-Promos/Lugia-V-S-P324"
                        ),
                        "name": "Lugia V (S-P 324)",
                    },
                    {
                        "url": (
                            "https://www.cardmarket.com/en/Pokemon/Products/"
                            "Singles/Pokemon-Trading-Card-Game-Classic-"
                            "Charizard-Ho-Oh-ex-Deck/Pikachu-CLC008"
                        ),
                        "name": "Pikachu",
                    },
                ],
            }
        )
    )
    stats = apply_cardmarket_links(conn, tmp_path, codes={"S-P"})
    extra = conn.execute(
        "SELECT * FROM cards WHERE id = 'extra-lugia-v-326-s-p'"
    ).fetchone()
    classic = conn.execute(
        "SELECT * FROM cards WHERE id = 'extra-clc008'"
    ).fetchone()
    assert stats["expansion_linked"] == 1
    assert stats["considered"] == 1
    assert url_for_row(extra) is not None
    assert url_for_row(classic) is None


def test_unmatched_listing_stores_image_url_not_file(tmp_path: Path) -> None:
    from app.cardmarket import list_unmatched_products, store_unmatched_product_image

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    official = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "Silver-Tempest/Lugia-V-V1-SIT138"
    )
    unmatched = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "Sword-Shield-Promos/Lugia-V-S-P324"
    )
    image_url = "https://product-images.s3.cardmarket.com/52/818570/818570.jpg"
    _insert_card(
        conn,
        "en:swsh12-138",
        "Lugia V",
        "Silver Tempest",
        "138",
        set_id="swsh12",
    )
    conn.commit()
    skip = store_unmatched_product_image(
        conn, tmp_path, url=official, image_url=image_url, name="Lugia V"
    )
    assert skip["stored"] is True
    assert skip["reason"] == "url"
    assert skip["image_url"] == image_url
    extras = conn.execute("SELECT id FROM cards WHERE id LIKE 'cm-%'").fetchall()
    assert extras == []
    stored = store_unmatched_product_image(
        conn, tmp_path, url=unmatched, image_url=image_url, name="Lugia V"
    )
    assert stored["stored"] is True
    assert stored["url"] == unmatched
    extras = conn.execute("SELECT id FROM cards WHERE id LIKE 'cm-%'").fetchall()
    assert extras == []
    listed = conn.execute(
        "SELECT listing_image_url, matched FROM cardmarket_expansion_products WHERE url = ?",
        (unmatched,),
    ).fetchone()
    assert listed["listing_image_url"] == image_url
    assert int(listed["matched"]) == 0
    images = list((tmp_path / "reference-images").glob("*.jpg")) if (tmp_path / "reference-images").exists() else []
    assert images == []
    page = list_unmatched_products(conn)
    assert unmatched not in [item["url"] for item in page["products"]]


def test_listing_image_url_saved_on_existing_expansion_product(tmp_path: Path) -> None:
    from app.cardmarket import store_unmatched_product_image, url_for_row

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    v1 = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "Fusion-Strike/Tsareena-V-V1"
    )
    _insert_card(
        conn,
        "en:swsh8-21",
        "Tsareena V",
        "Fusion Strike",
        "21",
        set_id="swsh8",
    )
    conn.execute(
        """
        INSERT INTO cardmarket_expansion_products (
            url, expansion, name, source, page_url, card_id, matched, imported_at
        ) VALUES (?, 'Fusion-Strike', 'Tsareena V', 'page', ?, NULL, 0, '2026-01-01T00:00:00Z')
        """,
        (v1, v1),
    )
    conn.commit()
    image_url = "https://product-images.s3.cardmarket.com/52/818570/818570.jpg"
    result = store_unmatched_product_image(
        conn,
        tmp_path,
        url=v1,
        name="Tsareena V",
        image_url=image_url,
    )
    assert result["stored"] is True
    assert result["reason"] == "url"
    assert result["image_url"] == image_url
    row = conn.execute("SELECT * FROM cards WHERE id = 'en:swsh8-21'").fetchone()
    assert url_for_row(row) is None
    listed = conn.execute(
        "SELECT listing_image_url, matched, card_id, source FROM cardmarket_expansion_products WHERE url = ?",
        (v1,),
    ).fetchone()
    assert listed["listing_image_url"] == image_url
    assert int(listed["matched"]) == 0
    assert listed["card_id"] is None
    assert listed["source"] == "page"


def test_list_unmatched_products_pages_after_cursor(tmp_path: Path) -> None:
    from app.cardmarket import list_unmatched_products

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    matched = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "Tag-Bolt/Aaa-ABC001"
    )
    first = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102"
    )
    second = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "Tag-Bolt/Zzz-ZZZ001"
    )
    conn.execute(
        """
        INSERT INTO cardmarket_expansion_products (
            url, expansion, name, source, page_url, card_id, matched, imported_at
        ) VALUES
        (?, 'Tag-Bolt', 'Aaa', 'page', ?, 'en:abc-1', 1, '2026-09-19T00:00:00Z'),
        (?, 'Tag-Bolt', 'Gengar', 'page', ?, NULL, 0, '2026-09-19T00:00:00Z'),
        (?, 'Tag-Bolt', 'Zzz', 'page', ?, '', 0, '2026-09-19T00:00:00Z')
        """,
        (
            matched,
            matched,
            first,
            first,
            second,
            second,
        ),
    )
    conn.commit()
    page = list_unmatched_products(conn, limit=1)
    assert page["total"] == 2
    assert page["products"][0]["url"] == first
    assert page["products"][0]["name"] == "Gengar"
    next_page = list_unmatched_products(conn, after=first, limit=10)
    assert [row["url"] for row in next_page["products"]] == [second]
    assert list_unmatched_products(conn, after=second)["products"] == []
    conn.execute(
        """
        UPDATE cardmarket_expansion_products
        SET listing_image_url = ?
        WHERE url = ?
        """,
        ("https://product-images.s3.cardmarket.com/1/gengar/gengar.jpg", first),
    )
    conn.commit()
    skipped = list_unmatched_products(conn, limit=10)
    assert skipped["total"] == 1
    assert [row["url"] for row in skipped["products"]] == [second]


def test_list_unmatched_products_skips_official_151_abra(tmp_path: Path) -> None:
    from app.cardmarket import list_unmatched_products

    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    v1 = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "151/Abra-V1-MEW063"
    )
    v2 = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "151/Abra-V2-MEW063"
    )
    movie = (
        "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
        "10th-Movie-Commemoration-Set/Alto-Mares-Latias"
    )
    _insert_card(
        conn,
        "en:sv03.5-063",
        "Abra",
        "151",
        "063",
        set_id="sv03.5",
        cardmarket_url=v1,
        provenance="helper-expansion",
    )
    conn.execute(
        """
        INSERT INTO cardmarket_expansion_products (
            url, expansion, name, source, page_url, card_id, matched, imported_at
        ) VALUES
        (?, '151', 'Abra', 'page', ?, NULL, 0, '2026-09-19T00:00:00Z'),
        (?, '151', 'Abra', 'page', ?, NULL, 0, '2026-09-19T00:00:00Z'),
        (?, '10th-Movie-Commemoration-Set', 'Latias', 'page', ?, NULL, 0, '2026-09-19T00:00:00Z')
        """,
        (v1, v1, v2, v2, movie, movie),
    )
    conn.commit()
    page = list_unmatched_products(conn, limit=10)
    urls = [row["url"] for row in page["products"]]
    assert v1 not in urls
    assert v2 not in urls
    assert urls == [movie]

