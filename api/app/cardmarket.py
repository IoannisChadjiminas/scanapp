from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse, urlunparse

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


def is_verified_singles_url(url: str | None) -> bool:
    raw = (url or "").strip()
    if not raw.startswith("https://"):
        return False
    host = urlparse(raw).netloc.lower()
    path = urlparse(raw).path
    if host not in {"www.cardmarket.com", "cardmarket.com"}:
        return False
    return "/Products/Singles/" in path and path.rstrip("/").count("/") >= 5


@dataclass(frozen=True)
class CardmarketMapping:
    product_id: int | None
    url: str | None
    verified: bool
    provenance: str
    verified_at: str | None = None

    def public_url(self) -> str | None:
        if self.verified and self.url:
            return self.url
        return None


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
    del product_id, provider_id
    return cardmarket_singles_url(
        name=name or "",
        expansion=expansion or set_name or "",
        set_code=set_code or "",
        collector_number=collector_number or "",
        language=language,
    )


def mapping_from_payload(
    payload: dict[str, Any], *, language: str | None = "en"
) -> CardmarketMapping:
    product_id = extract_cardmarket_id(payload)
    pricing = payload.get("pricing") if isinstance(payload, dict) else None
    if isinstance(pricing, dict):
        market = pricing.get("cardmarket")
        if isinstance(market, dict) and isinstance(market.get("url"), str):
            candidate = market["url"].strip()
            if is_verified_singles_url(candidate):
                return CardmarketMapping(
                    product_id=product_id,
                    url=candidate,
                    verified=True,
                    provenance="tcgdex-singles-url",
                    verified_at=datetime_now(),
                )
    return CardmarketMapping(
        product_id=product_id,
        url=None,
        verified=False,
        provenance="tcgdex-id" if product_id else "none",
        verified_at=None,
    )


def mapping_from_manifest(card: dict[str, Any]) -> CardmarketMapping:
    language = str(card.get("language") or "en")
    product_id = parse_product_id(card.get("cardmarket_id"))
    raw = card.get("cardmarket_url")
    if isinstance(raw, str) and raw.strip():
        url = raw.strip()
        verified = is_verified_singles_url(url)
        return CardmarketMapping(
            product_id=product_id,
            url=url,
            verified=verified,
            provenance="manifest-url" if verified else "manifest-unverified",
            verified_at=datetime_now() if verified else None,
        )
    generated = cardmarket_singles_url(
        name=str(card.get("name") or ""),
        expansion=str(card.get("cardmarket_expansion") or ""),
        set_code=str(card.get("cardmarket_set_code") or ""),
        collector_number=str(card.get("collector_number") or ""),
        language=language,
    )
    return CardmarketMapping(
        product_id=product_id,
        url=generated,
        verified=False,
        provenance="generated-singles" if generated else "none",
        verified_at=None,
    )


def url_from_manifest_card(card: dict[str, Any]) -> tuple[int | None, str | None]:
    mapping = mapping_from_manifest(card)
    return mapping.product_id, mapping.url


def fields_from_payload(
    payload: dict[str, Any], *, language: str | None = "en"
) -> tuple[int | None, str | None]:
    mapping = mapping_from_payload(payload, language=language)
    return mapping.product_id, mapping.public_url()


def mapping_from_row(row: Any) -> CardmarketMapping:
    if isinstance(row, dict):
        keys = set(row)
        get = row.get
    else:
        try:
            keys = set(row.keys())
        except Exception:
            keys = set()
        get = lambda key, default=None: row[key] if key in keys else default  # noqa: E731
    url = str(get("cardmarket_url") or "") or None
    product_id = parse_product_id(get("cardmarket_id"))
    verified = bool(int(get("cardmarket_verified") or 0)) if "cardmarket_verified" in keys else False
    provenance = str(get("cardmarket_provenance") or "") or "unknown"
    verified_at = str(get("cardmarket_verified_at") or "") or None
    if not verified and is_verified_singles_url(url) and "cardmarket_verified" not in keys:
        verified = True
        provenance = "legacy-singles"
    return CardmarketMapping(
        product_id=product_id,
        url=url,
        verified=verified,
        provenance=provenance,
        verified_at=verified_at,
    )


def url_for_row(row: sqlite3.Row) -> str | None:
    return mapping_from_row(row).public_url()


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
    if data_dir is None:
        return []
    for language, tcgdex_id in tcgdex_price_targets(row):
        found = _prices_from_cache(data_dir, language, tcgdex_id)
        if found:
            return found
    return []


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
    mapping: CardmarketMapping,
    provider_id: str,
    language: str,
) -> int:
    prefixed = f"{language}:{provider_id}"
    cursor = conn.execute(
        """
        UPDATE cards
        SET cardmarket_id = ?,
            cardmarket_url = ?,
            cardmarket_verified = ?,
            cardmarket_provenance = ?,
            cardmarket_verified_at = ?
        WHERE language = ?
          AND (id = ? OR id = ? OR provider_id = ?)
        """,
        (
            mapping.product_id,
            mapping.url,
            int(mapping.verified),
            mapping.provenance,
            mapping.verified_at,
            language,
            provider_id,
            prefixed,
            provider_id,
        ),
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
        mapping = mapping_from_manifest(card)
        if not mapping.url and mapping.product_id is None:
            continue
        cursor = conn.execute(
            """
            UPDATE cards
            SET cardmarket_id = ?,
                cardmarket_url = ?,
                cardmarket_verified = ?,
                cardmarket_provenance = ?,
                cardmarket_verified_at = ?
            WHERE id = ?
            """,
            (
                mapping.product_id,
                mapping.url,
                int(mapping.verified),
                mapping.provenance,
                mapping.verified_at,
                str(card["id"]),
            ),
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
            mapping = mapping_from_payload(payload, language=language)
            if mapping.product_id is None and not mapping.url:
                continue
            provider_id = str(payload.get("id") or path.stem)
            updated += _update_official(conn, mapping, provider_id, language)

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
