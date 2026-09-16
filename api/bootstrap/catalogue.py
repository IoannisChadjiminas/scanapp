from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

from app.db import connect, init_catalog
from bootstrap.download import download_file
from bootstrap.pins import TCGDEX_BASE


def _sets_filter() -> set[str] | None:
    raw = os.environ.get("CATALOGUE_SETS", "base1,sv01,swsh3")
    if raw.strip().lower() == "all":
        return None
    return {item.strip() for item in raw.split(",") if item.strip()}


def _image_url(base: str | None, quality: str) -> str | None:
    if not base:
        return None
    return f"{base}/{quality}.webp"


def import_catalogue(data_dir: Path) -> dict:
    language = os.environ.get("TCGDEX_LANGUAGE", "en")
    quality = os.environ.get("TCGDEX_IMAGE_QUALITY", "high")
    concurrency = int(os.environ.get("BOOTSTRAP_CONCURRENCY", "8"))
    allowed = _sets_filter()
    images_dir = data_dir / "reference-images"
    cache_dir = data_dir / "cache" / "cards"
    images_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    catalog_path = data_dir / "catalog.sqlite"
    conn = connect(catalog_path)
    init_catalog(conn)

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        if allowed:
            briefs = []
            for set_id in sorted(allowed):
                print(f"fetch set {set_id}")
                payload = client.get(f"{TCGDEX_BASE}/{language}/sets/{set_id}").json()
                briefs.extend(payload.get("cards") or [])
            sets = {
                item["id"]: item
                for item in client.get(f"{TCGDEX_BASE}/{language}/sets").json()
            }
        else:
            print(f"fetch {TCGDEX_BASE}/{language}/cards")
            briefs = client.get(f"{TCGDEX_BASE}/{language}/cards").json()
            sets = {
                item["id"]: item
                for item in client.get(f"{TCGDEX_BASE}/{language}/sets").json()
            }

    def load_card(brief: dict) -> dict:
        card_id = brief["id"]
        cache_path = cache_dir / f"{card_id}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text())
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            payload = client.get(f"{TCGDEX_BASE}/{language}/cards/{card_id}").json()
        cache_path.write_text(json.dumps(payload))
        return payload

    print(f"enrich {len(briefs)} cards")
    cards: list[dict] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(load_card, brief) for brief in briefs]
        for index, future in enumerate(as_completed(futures), start=1):
            cards.append(future.result())
            if index % 50 == 0:
                print(f"  details {index}/{len(briefs)}")

    print("download reference images")
    missing = 0
    for card in cards:
        dest = images_dir / f"{card['id']}.webp"
        url = _image_url(card.get("image"), quality)
        if not url:
            missing += 1
            card["_image_path"] = None
            continue
        try:
            download_file(url, dest)
            card["_image_path"] = str(dest)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip image {card['id']}: {exc}")
            missing += 1
            card["_image_path"] = None

    conn.execute("DELETE FROM cards")
    conn.execute("DELETE FROM cards_fts")
    for card in cards:
        set_info = card.get("set") or sets.get(str(card.get("id", "")).rsplit("-", 1)[0], {})
        variants = card.get("variants") or {}
        has_image = 1 if card.get("_image_path") else 0
        conn.execute(
            """
            INSERT INTO cards (
                id, provider_id, name, set_id, set_name, collector_number,
                language, category, rarity, illustrator, variants_json,
                image_path, has_image
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card["id"],
                card["id"],
                card.get("name") or "Unknown",
                set_info.get("id") or "",
                set_info.get("name") or "",
                str(card.get("localId") or ""),
                language,
                card.get("category"),
                card.get("rarity"),
                card.get("illustrator"),
                json.dumps(variants),
                card.get("_image_path"),
                has_image,
            ),
        )
        conn.execute(
            "INSERT INTO cards_fts (id, name, set_name, collector_number) VALUES (?, ?, ?, ?)",
            (
                card["id"],
                card.get("name") or "",
                set_info.get("name") or "",
                str(card.get("localId") or ""),
            ),
        )
    conn.commit()
    indexed = sum(1 for card in cards if card.get("_image_path"))
    version = f"tcgdex-{language}-{len(cards)}"
    (data_dir / "catalogue-version.json").write_text(
        json.dumps(
            {
                "catalogue_version": version,
                "language": language,
                "cards": len(cards),
                "indexed": indexed,
                "missing_images": missing,
                "sets": sorted(allowed) if allowed else "all",
            },
            indent=2,
        )
    )
    conn.close()
    print(f"catalogue {len(cards)} cards, {indexed} images, {missing} missing")
    return {
        "catalogue_version": version,
        "cards": len(cards),
        "indexed": indexed,
        "missing_images": missing,
    }
