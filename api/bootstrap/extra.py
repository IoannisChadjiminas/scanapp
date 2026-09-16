from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from app.db import connect, coverage, init_catalog


def extra_cards_dir() -> Path:
    raw = os.environ.get("EXTRA_CARDS_DIR", "/extra-cards")
    return Path(raw)


def import_extra_cards(data_dir: Path) -> int:
    source = extra_cards_dir()
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file():
        print(f"no extra cards at {manifest_path}")
        return 0

    payload = json.loads(manifest_path.read_text())
    cards = payload.get("cards") or []
    images_dir = data_dir / "reference-images"
    images_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = data_dir / "catalog.sqlite"
    conn = connect(catalog_path)
    init_catalog(conn)

    imported = 0
    for card in cards:
        filename = card.get("file")
        if not filename:
            continue
        src = source / str(filename)
        if not src.is_file():
            print(f"  skip extra {card.get('id')}: missing {src.name}")
            continue
        dest = images_dir / f"{card['id']}{src.suffix.lower()}"
        shutil.copy2(src, dest)
        card_id = str(card["id"])
        conn.execute(
            """
            INSERT INTO cards (
                id, provider_id, name, set_id, set_name, collector_number,
                language, category, rarity, illustrator, variants_json,
                image_path, has_image
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, 1)
            ON CONFLICT(id) DO UPDATE SET
                provider_id = excluded.provider_id,
                name = excluded.name,
                set_id = excluded.set_id,
                set_name = excluded.set_name,
                collector_number = excluded.collector_number,
                language = excluded.language,
                category = excluded.category,
                rarity = excluded.rarity,
                image_path = excluded.image_path,
                has_image = 1
            """,
            (
                card_id,
                card_id,
                card.get("name") or "Unknown",
                card.get("set_id") or "extra",
                card.get("set_name") or "Extra",
                str(card.get("collector_number") or ""),
                card.get("language") or "en",
                card.get("category"),
                card.get("rarity"),
                card.get("illustrator"),
                str(dest),
            ),
        )
        conn.execute("DELETE FROM cards_fts WHERE id = ?", (card_id,))
        conn.execute(
            "INSERT INTO cards_fts (id, name, set_name, collector_number) VALUES (?, ?, ?, ?)",
            (
                card_id,
                card.get("name") or "",
                card.get("set_name") or "",
                str(card.get("collector_number") or ""),
            ),
        )
        imported += 1
        print(f"  extra {card_id} {card.get('name')}")

    conn.commit()
    cards_n, indexed, missing = coverage(conn)
    conn.close()

    version_path = data_dir / "catalogue-version.json"
    version_info = {}
    if version_path.is_file():
        version_info = json.loads(version_path.read_text())
    base_version = str(version_info.get("catalogue_version") or "local")
    extra_tag = f"+extra{imported}"
    if "+extra" in base_version:
        base_version = base_version.split("+extra", 1)[0]
    version_info.update(
        {
            "catalogue_version": f"{base_version}{extra_tag}",
            "cards": cards_n,
            "indexed": indexed,
            "missing_images": missing,
            "extra_cards": imported,
        }
    )
    version_path.write_text(json.dumps(version_info, indent=2))
    print(f"extra catalogue {imported} cards (total {cards_n})")
    return imported
