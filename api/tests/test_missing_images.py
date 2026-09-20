from __future__ import annotations

from pathlib import Path

from app.db import connect, init_catalog
from bootstrap.catalogue import upsert_card
from bootstrap.missing_images import missing_image_report, retry_missing_images


def _card(conn, card_id: str, **overrides) -> None:
    fields = {
        "provider_id": card_id.split(":", 1)[-1],
        "name": "Pikachu",
        "set_id": "sv-p",
        "set_name": "SV Promo",
        "collector_number": "001",
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
        "cardmarket_provenance": None,
        "cardmarket_verified_at": None,
        "remote_image_url": None,
    }
    fields.update(overrides)
    upsert_card(conn, card_id=card_id, **fields)


def test_missing_image_report_splits_retryable_and_no_cdn(tmp_path: Path) -> None:
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    present = tmp_path / "reference-images" / "en" / "ok.webp"
    present.parent.mkdir(parents=True)
    present.write_bytes(b"webp")
    _card(
        conn,
        "en:ok-1",
        name="Present",
        image_path=str(present),
        has_image=1,
        remote_image_url="https://assets.tcgdex.net/en/ok/high.webp",
    )
    _card(
        conn,
        "en:sv-p-1",
        name="Retryable",
        remote_image_url="https://assets.tcgdex.net/en/svp/1/high.webp",
        cardmarket_url="https://www.cardmarket.com/en/Pokemon/Products/Singles/SV-Black-Star-Promos/Pikachu-SVP001",
    )
    _card(conn, "ja:sv-p-2", name="No CDN", language="ja")
    conn.execute(
        """
        INSERT INTO cardmarket_expansion_products (
            url, expansion, name, source, page_url, card_id, matched, imported_at
        ) VALUES (?, ?, ?, 'page', ?, NULL, 0, '2026-09-19T00:00:00Z')
        """,
        (
            "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
            "Sword-Shield-Promos/Lugia-V-S-P324",
            "Sword-Shield-Promos",
            "Lugia V (S-P 324)",
            "https://www.cardmarket.com/en/Pokemon/Products/Singles/Sword-Shield-Promos",
        ),
    )
    conn.commit()
    report = missing_image_report(conn, tmp_path)
    assert report["with_image"] == 1
    assert report["retryable"] == 1
    assert report["no_cdn"] == 1
    assert report["retryable_cards"][0]["id"] == "en:sv-p-1"
    assert report["retryable_cards"][0]["cardmarket_url"].endswith("Pikachu-SVP001")
    assert report["no_cdn_cards"][0]["id"] == "ja:sv-p-2"
    assert report["unmatched_cardmarket"] == 1
    assert report["unmatched_cardmarket_products"][0]["url"].endswith("Lugia-V-S-P324")


def test_retry_missing_images_writes_file(tmp_path: Path, monkeypatch) -> None:
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    _card(
        conn,
        "en:swshp-SWSH301",
        name="Lugia V",
        set_id="swshp",
        set_name="SWSH Black Star Promos",
        collector_number="SWSH301",
        remote_image_url="https://assets.tcgdex.net/en/swshp/SWSH301/high.webp",
    )
    conn.commit()

    def fake_download(url: str, dest: Path, **_kwargs):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"webp")
        return dest

    monkeypatch.setattr("bootstrap.missing_images.download_file", fake_download)
    report = missing_image_report(conn, tmp_path)
    stats = retry_missing_images(conn, tmp_path, report)
    assert stats["fetched"] == 1
    dest = tmp_path / "reference-images" / "en" / "swshp-SWSH301.webp"
    assert dest.is_file()
    row = conn.execute(
        "SELECT has_image, image_path FROM cards WHERE id = 'en:swshp-SWSH301'"
    ).fetchone()
    assert int(row["has_image"]) == 1
    assert row["image_path"] == str(dest)
    after = missing_image_report(conn, tmp_path)
    assert after["retryable"] == 0
    assert after["with_image"] == 1
