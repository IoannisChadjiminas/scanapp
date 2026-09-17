from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse, urlunparse

import httpx

TCGDEX_BASE = "https://api.tcgdex.net/v2"
_PRICE_TTL_SECONDS = 600.0
_price_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_PRODUCT_SLUG_RE = re.compile(r"/Products/Singles/[^/]+/([^/?#]+)", re.I)
_SLUG_CODE_RE = re.compile(r"-([A-Za-z]+)(\d+)$")

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


def datetime_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def normalize_product_url(url: str | None) -> str | None:
    raw = (url or "").strip()
    if not raw:
        return None
    parts = urlparse(raw)
    path = (parts.path or "").rstrip("/")
    host = (parts.netloc or "").lower()
    if "cardmarket.com" in host and path:
        return urlunparse(("https", "www.cardmarket.com", path, "", "", ""))
    if path:
        return f"{parts.scheme}://{parts.netloc}{path}" if parts.netloc else raw.split("#")[0].split("?")[0]
    return raw.split("#")[0].split("?")[0]


def is_job_url(url: str | None) -> bool:
    raw = (url or "").lower()
    if "prices.pokemontcg.io/cardmarket/" in raw:
        return True
    return singles_code_and_number(url) is not None


def _decode_prices(raw: Any) -> list[dict[str, Any]]:
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def snapshot_record(conn: sqlite3.Connection, url: str | None) -> dict[str, Any] | None:
    key = normalize_product_url(url)
    if not key:
        return None
    row = conn.execute(
        "SELECT * FROM cardmarket_snapshots WHERE url = ?",
        (key,),
    ).fetchone()
    if row is None:
        return None
    keys = set(row.keys())
    prices = _decode_prices(row["prices_json"])
    return {
        "url": key,
        "prices": prices,
        "fetched_at": str(row["fetched_at"] or "") or None,
        "observed_at": str(row["observed_at"] or "") if "observed_at" in keys else None,
        "parser_version": str(row["parser_version"] or "") if "parser_version" in keys else None,
        "sampled_offer_count": (
            int(row["sampled_offer_count"])
            if "sampled_offer_count" in keys and row["sampled_offer_count"] is not None
            else len(prices)
        ),
        "submission_id": str(row["submission_id"] or "") if "submission_id" in keys else None,
        "empty": not prices,
    }


def snapshot_prices(conn: sqlite3.Connection, url: str | None) -> list[dict[str, Any]]:
    record = snapshot_record(conn, url)
    return list(record["prices"]) if record else []


def write_snapshot(
    conn: sqlite3.Connection,
    url: str,
    prices: list[dict[str, Any]],
    *,
    observed_at: str | None = None,
    parser_version: str | None = None,
    sampled_offer_count: int | None = None,
    submission_id: str | None = None,
    allow_empty: bool = False,
    commit: bool = True,
) -> str:
    if not prices and not allow_empty:
        raise ValueError("Need at least one price")
    key = normalize_product_url(url) or url
    stamp = observed_at or datetime_now()
    existing = snapshot_record(conn, key)
    existing_observed = str((existing or {}).get("observed_at") or "")
    if existing_observed and existing_observed > stamp:
        return key
    conn.execute(
        """
        INSERT INTO cardmarket_snapshots (
            url, prices_json, fetched_at, observed_at, parser_version,
            sampled_offer_count, submission_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            prices_json = excluded.prices_json,
            fetched_at = excluded.fetched_at,
            observed_at = excluded.observed_at,
            parser_version = excluded.parser_version,
            sampled_offer_count = excluded.sampled_offer_count,
            submission_id = excluded.submission_id
        """,
        (
            key,
            json.dumps(prices),
            datetime_now(),
            stamp,
            parser_version,
            sampled_offer_count if sampled_offer_count is not None else len(prices),
            submission_id,
        ),
    )
    if commit:
        conn.commit()
    _price_cache.clear()
    return key


def save_snapshot(
    conn: sqlite3.Connection, url: str, prices: list[dict[str, Any]]
) -> str:
    return write_snapshot(conn, url, prices, commit=True)


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        keys = row.keys()
    except Exception:
        return default
    if key not in keys:
        return default
    return row[key]


def _positive_amount(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        amount = float(value)
        return amount if amount > 0 else None
    return None


def prices_from_market(market: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Cardmarket From / Trend / 7-day average (latest published guide)."""
    if not isinstance(market, dict):
        return []
    currency = str(market.get("unit") or "EUR")
    prices: list[dict[str, Any]] = []
    for label, key, holo_key in (
        ("From", "low", "low-holo"),
        ("Trend", "trend", "trend-holo"),
        ("7-day", "avg7", "avg7-holo"),
    ):
        amount = _positive_amount(market.get(key)) or _positive_amount(
            market.get(holo_key)
        )
        if amount is None:
            continue
        prices.append(
            {"label": label, "amount": round(amount, 2), "currency": currency}
        )
    return prices[:3]


def singles_code_and_number(url: str | None) -> tuple[str, str] | None:
    if not url:
        return None
    match = _PRODUCT_SLUG_RE.search(url)
    if not match:
        return None
    slug = match.group(1)
    coded = _SLUG_CODE_RE.search(slug)
    if not coded:
        return None
    letters, digits = coded.group(1), coded.group(2)
    if len(digits) > 3:
        letters += digits[:-3]
        digits = digits[-3:]
    number = digits.lstrip("0") or "0"
    return letters, number


def tcgdex_price_targets(row: Any) -> list[tuple[str, str]]:
    language = str(_row_value(row, "language") or "en").lower()
    provider = str(_row_value(row, "provider_id") or _row_value(row, "id") or "")
    pid = provider.split(":")[-1]
    set_id = str(_row_value(row, "set_id") or "")
    collector = collector_digits(str(_row_value(row, "collector_number") or ""))
    url = str(_row_value(row, "cardmarket_url") or "")
    seen: list[tuple[str, str]] = []

    def add(lang: str, card_id: str) -> None:
        item = (lang, card_id)
        if card_id and item not in seen:
            seen.append(item)

    parsed = singles_code_and_number(url)
    if parsed:
        code, number = parsed
        add(language, f"{code}-{number}")
        add(language, f"{code.lower()}-{number}")
        add(language, f"{code.upper()}-{number}")
    if pid and not pid.startswith("extra-"):
        add(language, pid)
    if set_id and collector:
        number = collector.lstrip("0") or collector
        add(language, f"{set_id}-{number}")
        add(language, f"{set_id.lower()}-{number}")
        add(language, f"{set_id.upper()}-{number}")
    return seen


def _market_from_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    pricing = payload.get("pricing")
    if not isinstance(pricing, dict):
        return None
    market = pricing.get("cardmarket")
    return market if isinstance(market, dict) else None


def _prices_from_cache(data_dir: Path, language: str, card_id: str) -> list[dict[str, Any]]:
    path = data_dir / "cache" / "cards" / language / f"{card_id}.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return prices_from_market(_market_from_payload(payload))


def _prices_from_tcgdex(language: str, card_id: str) -> list[dict[str, Any]]:
    url = f"{TCGDEX_BASE}/{language}/cards/{card_id}"
    with httpx.Client(timeout=2.5, follow_redirects=True) as client:
        response = client.get(url, headers={"User-Agent": "scanapp"})
        if response.status_code == 404:
            return []
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        return []
    return prices_from_market(_market_from_payload(payload))


def prices_for_row(
    row: Any, *, data_dir: Path | None = None, catalog: sqlite3.Connection | None = None
) -> list[dict[str, Any]]:
    url = None
    try:
        url = url_for_row(row)
    except Exception:
        url = str(_row_value(row, "cardmarket_url") or "") or None
    if catalog is not None:
        stored = snapshot_prices(catalog, url)
        if stored:
            return stored
    card_id = str(_row_value(row, "id") or "")
    now = time.monotonic()
    cached = _price_cache.get(card_id)
    if card_id and cached and now - cached[0] < _PRICE_TTL_SECONDS:
        return cached[1]
    found: list[dict[str, Any]] = []
    for language, tcgdex_id in tcgdex_price_targets(row):
        try:
            found = _prices_from_tcgdex(language, tcgdex_id)
        except Exception:  # noqa: BLE001 - scan must not fail if prices are down
            found = []
        if not found and data_dir is not None:
            found = _prices_from_cache(data_dir, language, tcgdex_id)
        if found:
            break
    if card_id:
        _price_cache[card_id] = (now, found)
    return found


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


from app.cardmarket_queue import (  # noqa: E402
    claim_job,
    enqueue_job,
    helper_is_online,
    job_by_id,
    latest_job_status,
    retry_or_fail_job,
    touch_helper,
)
