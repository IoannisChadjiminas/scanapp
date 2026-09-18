from __future__ import annotations

import json
import tarfile
from pathlib import Path

import numpy as np

from app.db import connect, init_catalog
from bootstrap.catalogue import upsert_card
from bootstrap.offload import apply_bundle, export_bundle


def _card(conn, card_id: str, **overrides) -> None:
    fields = {
        "provider_id": card_id,
        "name": "Bulbasaur",
        "set_id": "sv03.5",
        "set_name": "151",
        "collector_number": "001",
        "language": "en",
        "category": None,
        "rarity": None,
        "illustrator": None,
        "variants_json": "{}",
        "image_path": "/data/reference-images/en/sv03.5-001.webp",
        "has_image": 1,
        "cardmarket_id": 1,
        "cardmarket_url": None,
        "cardmarket_verified": 0,
        "cardmarket_provenance": "tcgdex-id",
        "cardmarket_verified_at": None,
        "remote_image_url": "https://assets.tcgdex.net/en/sv/sv03.5/001/high.webp",
    }
    fields.update(overrides)
    upsert_card(conn, card_id=card_id, **fields)


def _vector_bundle(root: Path, name: str, card_id: str) -> None:
    bundle = root / name
    bundle.mkdir(parents=True)
    embeddings = np.ones((1, 4), dtype=np.float32)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    np.save(bundle / "embeddings.npy", embeddings)
    np.save(bundle / "embedding_card_ids.npy", np.array([card_id]))
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "preprocess_config": root.name,
                "use_ocr": True,
                "catalogue_version": "test",
                "model_revision": "r",
                "embedding_dim": 4,
            }
        )
    )
    (root / "ACTIVE").write_text(name + "\n")


def test_offload_roundtrip_skips_official_scans_and_packs_extras(tmp_path: Path) -> None:
    source = tmp_path / "src"
    dest = tmp_path / "dst"
    source.mkdir()
    dest.mkdir()
    extra_src = source / "reference-images" / "extra-gengar.jpg"
    extra_src.parent.mkdir(parents=True)
    extra_src.write_bytes(b"extra-bytes")
    (source / "reference-images" / "en").mkdir(parents=True)
    (source / "reference-images" / "en" / "sv03.5-001.webp").write_bytes(b"official")
    conn = connect(source / "catalog.sqlite")
    init_catalog(conn)
    _card(conn, "en:sv03.5-001")
    _card(
        conn,
        "extra-gengar",
        name="Gengar",
        set_id="extra",
        image_path=str(extra_src),
        remote_image_url=None,
    )
    conn.execute(
        """
        INSERT INTO cardmarket_expansion_products (
            url, expansion, name, source, page_url, card_id, matched, imported_at
        ) VALUES (?, '151', 'Bulbasaur', 'page', ?, NULL, 0, '2026-01-01T00:00:00Z')
        """,
        (
            "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Bulbasaur-mew11",
            "https://www.cardmarket.com/en/Pokemon/Products/Singles/151",
        ),
    )
    conn.commit()
    conn.close()
    (source / "catalogue-version.json").write_text('{"catalogue_version":"test-151"}')
    dump_dir = source / "expansion-imports"
    dump_dir.mkdir()
    (dump_dir / "151-page.json").write_text(
        json.dumps(
            {
                "page_url": "https://www.cardmarket.com/en/Pokemon/Products/Singles/151",
                "source": "page",
                "products": [
                    "https://www.cardmarket.com/en/Pokemon/Products/Singles/151/Bulbasaur-mew11"
                ],
            }
        )
    )
    (source / "cardmarket-maps.json").write_text(
        json.dumps(
            {
                "cards": {
                    "extra-gengar": {
                        "cardmarket_url": "https://www.cardmarket.com/en/Pokemon/Products/Singles/X/Gengar"
                    }
                }
            }
        )
    )
    _vector_bundle(source / "vectors" / "pad", "snap-pad", "en:sv03.5-001")
    _vector_bundle(source / "vectors" / "square", "snap-square", "en:sv03.5-001")

    archive = export_bundle(source, tmp_path / "bundle.tar")
    with tarfile.open(archive) as tar:
        names = set(tar.getnames())
    assert "cards.jsonl" in names
    assert "expansion-products.jsonl" in names
    assert "expansion-imports/151-page.json" in names
    assert any(name.endswith("extra-gengar.jpg") for name in names)
    assert not any(name.endswith(".webp") for name in names)

    apply_bundle(archive, dest)
    applied = connect(dest / "catalog.sqlite")
    official = applied.execute("SELECT * FROM cards WHERE id = 'en:sv03.5-001'").fetchone()
    extra = applied.execute("SELECT * FROM cards WHERE id = 'extra-gengar'").fetchone()
    stored = applied.execute(
        "SELECT COUNT(*) AS n FROM cardmarket_expansion_products"
    ).fetchone()
    assert official["remote_image_url"].endswith("/001/high.webp")
    assert official["image_path"] is None
    assert extra["cardmarket_url"].endswith("/X/Gengar")
    assert extra["cardmarket_verified"] == 1
    assert stored["n"] == 1
    assert (dest / "vectors" / "pad" / "ACTIVE").read_text().strip() == "snap-pad"
    assert (dest / "cardmarket-maps.json").is_file()
    assert (dest / "expansion-imports" / "151-page.json").is_file()
