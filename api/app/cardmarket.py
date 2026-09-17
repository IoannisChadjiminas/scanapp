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


def collector_digits(collector_number: str) -> str:
    head = (collector_number or "").split("/")[0].strip()
    return re.sub(r"\D", "", head)


def cardmarket_singles_url(
    *,
    name: str,
    expansion: str,
    set_code: str,
    collector_number: str = "",
    language: str | None = "en",
) -> str | None:
    """Canonical Cardmarket product page: /Singles/{expansion}/{Name}-{CODE}{number}."""
    expansion_slug = cardmarket_slug(expansion)
    name_slug = cardmarket_slug(name)
    code = re.sub(r"[^A-Za-z0-9]", "", set_code or "").upper()
    number = collector_digits(collector_number)
    if not expansion_slug or not name_slug or not code or not number:
        return None
    locale = cardmarket_locale(language)
    return (
        f"https://www.cardmarket.com/{locale}/Pokemon/Products/Singles/"
        f"{expansion_slug}/{name_slug}-{code}{number}"
    )


def cardmarket_product_url(
    product_id: object = None,
    *,
    provider_id: str | None = None,
    name: str | None = None,
    set_name: str | None = None,
    language: str | None = "en",
    expansion: str | None = None,
    set_code: str | None = None,
    collector_number: str | None = None,
) -> str | None:
    del product_id
    pid = str(provider_id or "").split(":")[-1]
    lang = (language or "en").lower()
    # One official English catalogue id maps to one Cardmarket product via pokemontcg.io.
    if pid and not pid.startswith("extra-") and lang == "en":
        return f"https://prices.pokemontcg.io/cardmarket/{pid}"
    return cardmarket_singles_url(
        name=name or "",
        expansion=expansion or set_name or "",
        set_code=set_code or "",
        collector_number=collector_number or "",
        language=language,
    )


def url_from_manifest_card(card: dict[str, Any]) -> tuple[int | None, str | None]:
    """1-to-1 extra image → Cardmarket URL. Explicit URL wins; else expansion+set code."""
    language = str(card.get("language") or "en")
    product_id = parse_product_id(card.get("cardmarket_id"))
    raw = card.get("cardmarket_url")
    if isinstance(raw, str) and raw.strip():
        return product_id, raw.strip()
    url = cardmarket_singles_url(
        name=str(card.get("name") or ""),
        expansion=str(card.get("cardmarket_expansion") or ""),
        set_code=str(card.get("cardmarket_set_code") or ""),
        collector_number=str(card.get("collector_number") or ""),
        language=language,
    )
    return product_id, url


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
            if (
                candidate.startswith("https://www.cardmarket.com/")
                and "/Products/Singles/" in candidate
            ):
                url = candidate
    if not url:
        url = cardmarket_product_url(
            product_id,
            provider_id=str(payload.get("id") or ""),
            language=language,
        )
    return product_id, url


def url_for_row(row: sqlite3.Row) -> str | None:
    keys = set(row.keys())
    if "cardmarket_url" in keys and row["cardmarket_url"]:
        return str(row["cardmarket_url"])
    language = str(row["language"] or "en") if "language" in keys else "en"
    provider_id = str(row["provider_id"] or "") if "provider_id" in keys else ""
    if not provider_id and "id" in keys:
        provider_id = str(row["id"] or "")
    product_id = row["cardmarket_id"] if "cardmarket_id" in keys else None
    return cardmarket_product_url(
        product_id,
        provider_id=provider_id,
        language=language,
    )


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
        product_id, url = url_from_manifest_card(card)
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

    extra_dir = Path(os.environ.get("EXTRA_CARDS_DIR", "/extra-cards"))
    updated += apply_extra_manifest(conn, extra_dir)
    conn.commit()
    return updated
