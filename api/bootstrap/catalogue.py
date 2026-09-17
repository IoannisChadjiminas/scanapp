from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

from app.cardmarket import fields_from_payload
from app.db import connect, init_catalog
from bootstrap.download import download_file
from bootstrap.pins import TCGDEX_BASE


def _sets_filter() -> set[str] | None:
    raw = os.environ.get("CATALOGUE_SETS", "base1,sv01,swsh3")
    if raw.strip().lower() == "all":
        return None
    return {item.strip() for item in raw.split(",") if item.strip()}


def _languages() -> list[str]:
    raw = os.environ.get("TCGDEX_LANGUAGES") or os.environ.get("TCGDEX_LANGUAGE", "en")
    languages: list[str] = []
    for item in raw.split(","):
        code = item.strip().lower().replace("_", "-")
        if code and code not in languages:
            languages.append(code)
    return languages or ["en"]


def _image_url(base: str | None, quality: str) -> str | None:
    if not base:
        return None
    return f"{base}/{quality}.webp"


def _card_pk(language: str, provider_id: str) -> str:
    if provider_id.startswith(f"{language}:"):
        return provider_id
    return f"{language}:{provider_id}"


def _get_json(client: httpx.Client, url: str) -> dict | list | None:
    response = client.get(url)
    if response.status_code == 404:
        print(f"skip missing {url}")
        return None
    response.raise_for_status()
    return response.json()


def _briefs_for_language(
    client: httpx.Client,
    language: str,
    allowed: set[str] | None,
) -> tuple[list[dict], dict]:
    sets_payload = _get_json(client, f"{TCGDEX_BASE}/{language}/sets")
    sets = {
        item["id"]: item
        for item in (sets_payload or [])
        if isinstance(item, dict) and item.get("id")
    }
    if allowed:
        briefs: list[dict] = []
        for set_id in sorted(allowed):
            payload = _get_json(client, f"{TCGDEX_BASE}/{language}/sets/{set_id}")
            if not isinstance(payload, dict):
                continue
            briefs.extend(payload.get("cards") or [])
        return briefs, sets
    print(f"fetch {TCGDEX_BASE}/{language}/cards")
    cards_payload = _get_json(client, f"{TCGDEX_BASE}/{language}/cards")
    briefs = [item for item in (cards_payload or []) if isinstance(item, dict)]
    return briefs, sets


def import_catalogue(data_dir: Path) -> dict:
    languages = _languages()
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
    conn.execute("DELETE FROM cards")
    conn.execute("DELETE FROM cards_fts")

    total_cards = 0
    total_indexed = 0
    missing = 0
    per_language: dict[str, int] = {}

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        for language in languages:
            print(f"== catalogue {language}")
            briefs, sets = _briefs_for_language(client, language, allowed)
            if not briefs:
                print(f"  no cards for {language}")
                per_language[language] = 0
                continue

            def load_card(brief: dict, lang: str = language) -> dict:
                card_id = brief["id"]
                cache_path = cache_dir / lang / f"{card_id}.json"
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                if cache_path.exists():
                    return json.loads(cache_path.read_text())
                with httpx.Client(timeout=60.0, follow_redirects=True) as inner:
                    payload = inner.get(f"{TCGDEX_BASE}/{lang}/cards/{card_id}")
                    payload.raise_for_status()
                    body = payload.json()
                cache_path.write_text(json.dumps(body))
                return body

            print(f"  enrich {len(briefs)} cards")
            cards: list[dict] = []
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = [pool.submit(load_card, brief) for brief in briefs]
                for index, future in enumerate(as_completed(futures), start=1):
                    cards.append(future.result())
                    if index % 50 == 0:
                        print(f"  details {language} {index}/{len(briefs)}")

            print(f"  download {language} reference images")
            lang_dir = images_dir / language
            lang_dir.mkdir(parents=True, exist_ok=True)
            for card in cards:
                provider_id = str(card["id"])
                dest = lang_dir / f"{provider_id}.webp"
                url = _image_url(card.get("image"), quality)
                if not url:
                    missing += 1
                    card["_image_path"] = None
                    continue
                try:
                    download_file(url, dest)
                    card["_image_path"] = str(dest)
                    total_indexed += 1
                except Exception as exc:  # noqa: BLE001
                    print(f"  skip image {language}:{provider_id}: {exc}")
                    missing += 1
                    card["_image_path"] = None

            for card in cards:
                provider_id = str(card["id"])
                card_id = _card_pk(language, provider_id)
                set_info = card.get("set") or sets.get(
                    str(provider_id).rsplit("-", 1)[0], {}
                )
                variants = card.get("variants") or {}
                has_image = 1 if card.get("_image_path") else 0
                cardmarket_id, cardmarket_url = fields_from_payload(
                    card, language=language
                )
                conn.execute(
                    """
                    INSERT INTO cards (
                        id, provider_id, name, set_id, set_name, collector_number,
                        language, category, rarity, illustrator, variants_json,
                        image_path, has_image, cardmarket_id, cardmarket_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        card_id,
                        provider_id,
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
                        cardmarket_id,
                        cardmarket_url,
                    ),
                )
                conn.execute(
                    "INSERT INTO cards_fts (id, name, set_name, collector_number) VALUES (?, ?, ?, ?)",
                    (
                        card_id,
                        card.get("name") or "",
                        set_info.get("name") or "",
                        str(card.get("localId") or ""),
                    ),
                )
            total_cards += len(cards)
            per_language[language] = len(cards)
            conn.commit()

    version = f"tcgdex-{'+'.join(languages)}-{total_cards}"
    (data_dir / "catalogue-version.json").write_text(
        json.dumps(
            {
                "catalogue_version": version,
                "language": languages[0] if len(languages) == 1 else languages,
                "languages": per_language,
                "cards": total_cards,
                "indexed": total_indexed,
                "missing_images": missing,
                "sets": sorted(allowed) if allowed else "all",
            },
            indent=2,
        )
    )
    conn.close()
    print(f"catalogue {total_cards} cards, {total_indexed} images, {missing} missing")
    return {
        "catalogue_version": version,
        "cards": total_cards,
        "indexed": total_indexed,
        "missing_images": missing,
        "languages": per_language,
    }
