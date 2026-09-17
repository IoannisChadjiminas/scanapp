from __future__ import annotations

import json
import os
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

CARDMARKET_LOCALES = {"en", "de", "fr", "es", "it"}
LANGUAGE_DIRS = {"en", "ja", "zh-cn", "zh-tw", "ko", "fr", "de", "es", "it", "pt"}


def parse_product_id(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and value.is_integer():
        parsed = int(value)
        return parsed if parsed > 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def cardmarket_locale(language: str | None) -> str:
    raw = (language or "en").lower()
    if raw in CARDMARKET_LOCALES:
        return raw
    return "en"


def cardmarket_slug(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.replace("&", " ").replace("'", "")
    text = re.sub(r"[^A-Za-z0-9]+", "-", text)
    return text.strip("-")


def cardmarket_product_url(
    product_id: object = None,
    *,
    provider_id: str | None = None,
    name: str | None = None,
    set_name: str | None = None,
    language: str | None = "en",
) -> str | None:
    locale = cardmarket_locale(language)
    pid = str(provider_id or "").split(":")[-1]
    lang = (language or "en").lower()
    # TCGdex English IDs match pokemontcg.io, which redirects to the canonical Cardmarket product page.
    if pid and not pid.startswith("extra-") and lang == "en":
        return f"https://prices.pokemontcg.io/cardmarket/{pid}"
    expansion = cardmarket_slug(set_name or "")
    product = cardmarket_slug(name or "")
    if expansion and product:
        return (
            f"https://www.cardmarket.com/{locale}/Pokemon/Products/Singles/"
            f"{expansion}/{product}"
        )
    parsed = parse_product_id(product_id)
    if parsed:
        return (
            f"https://www.cardmarket.com/{locale}/Pokemon/Products/Search"
            f"?idProduct={parsed}"
        )
    if name:
        return cardmarket_search_url(name, language=language)
    return None


def cardmarket_search_url(
    name: str,
    collector_number: str = "",
    *,
    language: str | None = "en",
) -> str | None:
    query = " ".join(
        part.strip()
        for part in (name, collector_number)
        if part and str(part).strip()
    )
    if not query:
        return None
    locale = cardmarket_locale(language)
    return (
        "https://www.cardmarket.com/"
        f"{locale}/Pokemon/Products/Search?searchString={quote_plus(query)}"
    )


def extract_cardmarket_id(payload: dict[str, Any] | None) -> int | None:
    if not isinstance(payload, dict):
        return None
    pricing = payload.get("pricing")
    if isinstance(pricing, dict):
        market = pricing.get("cardmarket")
        if isinstance(market, dict):
            found = parse_product_id(market.get("idProduct"))
            if found:
                return found
    third = payload.get("thirdParty")
    if isinstance(third, dict):
        found = parse_product_id(third.get("cardmarket"))
        if found:
            return found
    for variant in payload.get("variants_detailed") or []:
        if not isinstance(variant, dict):
            continue
        nested = extract_cardmarket_id(variant)
        if nested:
            return nested
        nested_third = variant.get("thirdParty")
        if isinstance(nested_third, dict):
            found = parse_product_id(nested_third.get("cardmarket"))
            if found:
                return found
    return None


def fields_from_payload(
    payload: dict[str, Any], *, language: str | None = "en"
) -> tuple[int | None, str | None]:
    product_id = extract_cardmarket_id(payload)
    url = None
    pricing = payload.get("pricing")
    if isinstance(pricing, dict):
        market = pricing.get("cardmarket")
        if isinstance(market, dict) and isinstance(market.get("url"), str):
            candidate = market["url"].strip()
            if candidate.startswith("https://www.cardmarket.com/") and "/Products/Singles/" in candidate:
                url = candidate
    if not url:
        set_info = payload.get("set") if isinstance(payload.get("set"), dict) else {}
        url = cardmarket_product_url(
            product_id,
            provider_id=str(payload.get("id") or ""),
            name=str(payload.get("name") or ""),
            set_name=str(set_info.get("name") or ""),
            language=language,
        )
    return product_id, url


def url_for_row(row: sqlite3.Row) -> str | None:
    keys = set(row.keys())
    language = str(row["language"] or "en") if "language" in keys else "en"
    name = str(row["name"] or "") if "name" in keys else ""
    set_name = str(row["set_name"] or "") if "set_name" in keys else ""
    provider_id = str(row["provider_id"] or "") if "provider_id" in keys else ""
    if not provider_id and "id" in keys:
        provider_id = str(row["id"] or "")
    product_id = row["cardmarket_id"] if "cardmarket_id" in keys else None
    rebuilt = cardmarket_product_url(
        product_id,
        provider_id=provider_id,
        name=name,
        set_name=set_name,
        language=language,
    )
    if rebuilt:
        return rebuilt
    if "cardmarket_url" in keys and row["cardmarket_url"]:
        return str(row["cardmarket_url"])
    return None


def _language_from_cache_path(path: Path, cache_root: Path) -> str:
    try:
        relative = path.relative_to(cache_root)
    except ValueError:
        return "en"
    if relative.parts and relative.parts[0].lower() in LANGUAGE_DIRS:
        return relative.parts[0].lower()
    return "en"


def _update_official(
    conn: sqlite3.Connection,
    product_id: int | None,
    url: str,
    provider_id: str,
    language: str,
) -> int:
    prefixed = f"{language}:{provider_id}"
    cursor = conn.execute(
        """
        UPDATE cards
        SET cardmarket_id = ?, cardmarket_url = ?
        WHERE language = ?
          AND (id = ? OR id = ? OR provider_id = ?)
        """,
        (product_id, url, language, provider_id, prefixed, provider_id),
    )
    return int(cursor.rowcount or 0)


def apply_extra_manifest(conn: sqlite3.Connection, extra_dir: Path) -> int:
    path = extra_dir / "manifest.json"
    if not path.is_file():
        return 0
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return 0
    updated = 0
    for card in payload.get("cards") or []:
        if not isinstance(card, dict) or not card.get("id"):
            continue
        language = str(card.get("language") or "en")
        product_id = parse_product_id(card.get("cardmarket_id"))
        raw_url = card.get("cardmarket_url")
        url = raw_url.strip() if isinstance(raw_url, str) and raw_url.strip() else None
        if not url:
            url = cardmarket_product_url(
                product_id,
                provider_id=str(card.get("id") or ""),
                name=str(card.get("name") or ""),
                set_name=str(card.get("set_name") or ""),
                language=language,
            )
        if not url:
            continue
        cursor = conn.execute(
            """
            UPDATE cards
            SET cardmarket_id = ?, cardmarket_url = ?
            WHERE id = ?
            """,
            (product_id, url, str(card["id"])),
        )
        updated += int(cursor.rowcount or 0)
    return updated


def sync_cardmarket_links(data_dir: Path, conn: sqlite3.Connection) -> int:
    updated = 0
    cache_root = data_dir / "cache" / "cards"
    if cache_root.is_dir():
        for path in sorted(cache_root.rglob("*.json")):
            try:
                payload = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            language = _language_from_cache_path(path, cache_root)
            product_id, url = fields_from_payload(payload, language=language)
            if not url:
                continue
            provider_id = str(payload.get("id") or path.stem)
            updated += _update_official(conn, product_id, url, provider_id, language)

    extra_rows = conn.execute(
        """
        SELECT id, name, set_name, collector_number, language
        FROM cards
        WHERE (cardmarket_url IS NULL OR cardmarket_url = '')
          AND (id LIKE 'extra-%' OR provider_id LIKE 'extra-%')
        """
    ).fetchall()
    for row in extra_rows:
        url = cardmarket_product_url(
            name=row["name"],
            set_name=row["set_name"],
            provider_id=row["id"],
            language=row["language"],
        )
        if not url:
            continue
        conn.execute(
            "UPDATE cards SET cardmarket_url = ? WHERE id = ?",
            (url, row["id"]),
        )
        updated += 1

    extra_dir = Path(os.environ.get("EXTRA_CARDS_DIR", "/extra-cards"))
    updated += apply_extra_manifest(conn, extra_dir)
    conn.commit()
    return updated
