from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

from app.cardmarket import apply_cardmarket_links, mapping_from_payload
from app.db import connect, coverage, coverage_by_language, init_catalog
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


def upsert_card(
    conn,
    *,
    card_id: str,
    provider_id: str,
    name: str,
    set_id: str,
    set_name: str,
    collector_number: str,
    language: str,
    category: str | None,
    rarity: str | None,
    illustrator: str | None,
    variants_json: str,
    image_path: str | None,
    has_image: int,
    cardmarket_id: int | None,
    cardmarket_url: str | None,
    cardmarket_verified: int,
    cardmarket_provenance: str | None,
    cardmarket_verified_at: str | None,
    remote_image_url: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO cards (
            id, provider_id, name, set_id, set_name, collector_number,
            language, category, rarity, illustrator, variants_json,
            image_path, has_image, cardmarket_id, cardmarket_url,
            cardmarket_verified, cardmarket_provenance, cardmarket_verified_at,
            remote_image_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            provider_id = excluded.provider_id,
            name = excluded.name,
            set_id = excluded.set_id,
            set_name = excluded.set_name,
            collector_number = excluded.collector_number,
            language = excluded.language,
            category = excluded.category,
            rarity = excluded.rarity,
            illustrator = excluded.illustrator,
            variants_json = excluded.variants_json,
            image_path = COALESCE(excluded.image_path, cards.image_path),
            has_image = CASE
                WHEN excluded.image_path IS NOT NULL THEN excluded.has_image
                WHEN cards.image_path IS NOT NULL THEN cards.has_image
                ELSE excluded.has_image
            END,
            cardmarket_id = CASE
                WHEN cards.cardmarket_verified = 1 THEN cards.cardmarket_id
                ELSE excluded.cardmarket_id
            END,
            cardmarket_url = CASE
                WHEN cards.cardmarket_verified = 1 THEN cards.cardmarket_url
                ELSE excluded.cardmarket_url
            END,
            cardmarket_verified = CASE
                WHEN cards.cardmarket_verified = 1 THEN cards.cardmarket_verified
                ELSE excluded.cardmarket_verified
            END,
            cardmarket_provenance = CASE
                WHEN cards.cardmarket_verified = 1 THEN cards.cardmarket_provenance
                ELSE excluded.cardmarket_provenance
            END,
            cardmarket_verified_at = CASE
                WHEN cards.cardmarket_verified = 1 THEN cards.cardmarket_verified_at
                ELSE excluded.cardmarket_verified_at
            END,
            remote_image_url = COALESCE(excluded.remote_image_url, cards.remote_image_url)
        """,
        (
            card_id,
            provider_id,
            name,
            set_id,
            set_name,
            collector_number,
            language,
            category,
            rarity,
            illustrator,
            variants_json,
            image_path,
            has_image,
            cardmarket_id,
            cardmarket_url,
            cardmarket_verified,
            cardmarket_provenance,
            cardmarket_verified_at,
            remote_image_url,
        ),
    )
    conn.execute("DELETE FROM cards_fts WHERE id = ?", (card_id,))
    conn.execute(
        "INSERT INTO cards_fts (id, name, set_name, collector_number) VALUES (?, ?, ?, ?)",
        (card_id, name, set_name, collector_number),
    )


def _write_catalogue_version(
    data_dir: Path,
    conn,
    *,
    languages: list[str],
    allowed: set[str] | None,
    replace: bool,
    imported: int,
    indexed: int,
    missing: int,
    per_language: dict[str, int],
) -> str:
    path = data_dir / "catalogue-version.json"
    existing: dict = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text())
            if isinstance(loaded, dict):
                existing = loaded
        except json.JSONDecodeError:
            existing = {}
    if replace:
        version = f"tcgdex-{'+'.join(languages)}-{imported}"
        payload = {
            "catalogue_version": version,
            "language": languages[0] if len(languages) == 1 else languages,
            "languages": per_language,
            "cards": imported,
            "indexed": indexed,
            "missing_images": missing,
            "sets": sorted(allowed) if allowed else "all",
        }
    else:
        cards_n, indexed_n, missing_n = coverage(conn)
        language_counts = {
            str(item["language"]): int(item["cards"])
            for item in coverage_by_language(conn)
        }
        extra_n = int(
            conn.execute(
                "SELECT COUNT(*) FROM cards WHERE id LIKE 'extra-%'"
            ).fetchone()[0]
        )
        official = max(cards_n - extra_n, 0)
        langs = list(language_counts) or languages
        version = f"tcgdex-{'+'.join(langs)}-{official}"
        if extra_n:
            version += f"+extra{extra_n}"
        added = existing.get("added_sets") if isinstance(existing.get("added_sets"), list) else []
        for set_id in sorted(allowed or []):
            if set_id not in added:
                added.append(set_id)
        payload = {
            **existing,
            "catalogue_version": version,
            "language": langs[0] if len(langs) == 1 else langs,
            "languages": language_counts,
            "cards": cards_n,
            "indexed": indexed_n,
            "missing_images": missing_n,
            "extra_cards": extra_n,
            "added_sets": added,
        }
    path.write_text(json.dumps(payload, indent=2))
    return version


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


_UNSET = object()


def import_catalogue(
    data_dir: Path,
    *,
    replace: bool = True,
    sets: set[str] | None | object = _UNSET,
) -> dict:
    languages = _languages()
    quality = os.environ.get("TCGDEX_IMAGE_QUALITY", "high")
    concurrency = int(os.environ.get("BOOTSTRAP_CONCURRENCY", "8"))
    allowed = _sets_filter() if sets is _UNSET else sets
    images_dir = data_dir / "reference-images"
    cache_dir = data_dir / "cache" / "cards"
    images_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    catalog_path = data_dir / "catalog.sqlite"
    conn = connect(catalog_path)
    init_catalog(conn)
    if replace:
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
                card["_remote_image_url"] = url
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
                mapping = mapping_from_payload(card, language=language)
                upsert_card(
                    conn,
                    card_id=card_id,
                    provider_id=provider_id,
                    name=card.get("name") or "Unknown",
                    set_id=set_info.get("id") or "",
                    set_name=set_info.get("name") or "",
                    collector_number=str(card.get("localId") or ""),
                    language=language,
                    category=card.get("category"),
                    rarity=card.get("rarity"),
                    illustrator=card.get("illustrator"),
                    variants_json=json.dumps(variants),
                    image_path=card.get("_image_path"),
                    has_image=has_image,
                    cardmarket_id=mapping.product_id,
                    cardmarket_url=mapping.url,
                    cardmarket_verified=int(mapping.verified),
                    cardmarket_provenance=mapping.provenance,
                    cardmarket_verified_at=mapping.verified_at,
                    remote_image_url=card.get("_remote_image_url"),
                )
            total_cards += len(cards)
            per_language[language] = len(cards)
            conn.commit()

    stats = apply_cardmarket_links(conn, data_dir)
    print(
        f"cardmarket maps {stats['helper_maps']}, "
        f"expansion linked {stats['expansion_linked']}, "
        f"unmatched {stats['expansion_unmatched']}"
    )
    version = _write_catalogue_version(
        data_dir,
        conn,
        languages=languages,
        allowed=allowed,
        replace=replace,
        imported=total_cards,
        indexed=total_indexed,
        missing=missing,
        per_language=per_language,
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
