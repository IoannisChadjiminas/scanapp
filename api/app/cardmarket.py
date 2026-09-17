from __future__ import annotations

import calendar
import json
import os
import re
import sqlite3
import time
import unicodedata
import uuid
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


def snapshot_prices(conn: sqlite3.Connection, url: str | None) -> list[dict[str, Any]]:
    key = normalize_product_url(url)
    if not key:
        return []
    row = conn.execute(
        "SELECT prices_json FROM cardmarket_snapshots WHERE url = ?",
        (key,),
    ).fetchone()
    if row is None:
        return []
    try:
        payload = json.loads(row["prices_json"])
    except (TypeError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def save_snapshot(
    conn: sqlite3.Connection, url: str, prices: list[dict[str, Any]]
) -> str:
    key = normalize_product_url(url) or url
    conn.execute(
        """
        INSERT INTO cardmarket_snapshots (url, prices_json, fetched_at)
        VALUES (?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            prices_json = excluded.prices_json,
            fetched_at = excluded.fetched_at
        """,
        (key, json.dumps(prices), datetime_now()),
    )
    conn.commit()
    _price_cache.clear()
    return key


def datetime_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def enqueue_job(
    conn: sqlite3.Connection, url: str, card_id: str | None = None
) -> str:
    key = normalize_product_url(url) or url
    existing = conn.execute(
        """
        SELECT id FROM cardmarket_jobs
        WHERE url = ? AND status IN ('pending', 'claimed')
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (key,),
    ).fetchone()
    if existing:
        return str(existing["id"])
    job_id = str(uuid.uuid4())
    now = datetime_now()
    conn.execute(
        """
        INSERT INTO cardmarket_jobs (id, url, card_id, status, created_at, updated_at)
        VALUES (?, ?, ?, 'pending', ?, ?)
        """,
        (job_id, key, card_id or "", now, now),
    )
    conn.commit()
    return job_id


_STALE_CLAIM_SECONDS = 90
_MAX_JOB_ATTEMPTS = 3


def _settle_stale_jobs(conn: sqlite3.Connection) -> None:
    cutoff = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - _STALE_CLAIM_SECONDS)
    )
    now = datetime_now()
    conn.execute(
        """
        UPDATE cardmarket_jobs
        SET status = 'pending', updated_at = ?
        WHERE status = 'claimed' AND updated_at < ?
        """,
        (now, cutoff),
    )


def claim_job(conn: sqlite3.Connection) -> dict[str, str] | None:
    try:
        conn.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError:
        pass
    _settle_stale_jobs(conn)
    row = conn.execute(
        """
        SELECT id, url, card_id FROM cardmarket_jobs
        WHERE status = 'pending'
        ORDER BY created_at
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        conn.commit()
        return None
    conn.execute(
        "UPDATE cardmarket_jobs SET status = 'claimed', updated_at = ? WHERE id = ?",
        (datetime_now(), row["id"]),
    )
    conn.commit()
    return {"id": str(row["id"]), "url": str(row["url"]), "card_id": str(row["card_id"] or "")}


def is_job_url(url: str | None) -> bool:
    raw = (url or "").lower()
    if "prices.pokemontcg.io/cardmarket/" in raw:
        return True
    return singles_code_and_number(url) is not None


def job_by_id(conn: sqlite3.Connection, job_id: str) -> dict[str, str] | None:
    row = conn.execute(
        "SELECT id, url, card_id, status, attempts FROM cardmarket_jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    if row is None:
        return None
    keys = set(row.keys())
    attempts = int(row["attempts"] or 0) if "attempts" in keys else 0
    return {
        "id": str(row["id"]),
        "url": str(row["url"]),
        "card_id": str(row["card_id"] or ""),
        "status": str(row["status"] or ""),
        "attempts": str(attempts),
    }


def complete_job(conn: sqlite3.Connection, job_id: str, status: str = "done") -> None:
    conn.execute(
        "UPDATE cardmarket_jobs SET status = ?, updated_at = ? WHERE id = ?",
        (status, datetime_now(), job_id),
    )
    conn.commit()


def retry_or_fail_job(conn: sqlite3.Connection, job_id: str) -> str:
    job = job_by_id(conn, job_id)
    if job is None:
        return "failed"
    attempts = int(job.get("attempts") or 0) + 1
    if attempts >= _MAX_JOB_ATTEMPTS:
        conn.execute(
            """
            UPDATE cardmarket_jobs
            SET status = 'failed', attempts = ?, updated_at = ?
            WHERE id = ?
            """,
            (attempts, datetime_now(), job_id),
        )
        conn.commit()
        return "failed"
    conn.execute(
        """
        UPDATE cardmarket_jobs
        SET status = 'pending', attempts = ?, updated_at = ?
        WHERE id = ?
        """,
        (attempts, datetime_now(), job_id),
    )
    conn.commit()
    return "pending"


def touch_helper(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        INSERT INTO cardmarket_helper (id, last_seen)
        VALUES (1, ?)
        ON CONFLICT(id) DO UPDATE SET last_seen = excluded.last_seen
        """,
        (datetime_now(),),
    )
    conn.commit()


def helper_is_online(conn: sqlite3.Connection, *, within_seconds: int = 120) -> bool:
    row = conn.execute(
        "SELECT last_seen FROM cardmarket_helper WHERE id = 1"
    ).fetchone()
    if row is None:
        return False
    try:
        last = time.strptime(str(row["last_seen"]), "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return False
    age = time.time() - calendar.timegm(last)
    return 0 <= age <= within_seconds


def latest_job_status(conn: sqlite3.Connection, url: str | None) -> str | None:
    key = normalize_product_url(url)
    if not key:
        return None
    row = conn.execute(
        """
        SELECT status FROM cardmarket_jobs
        WHERE url = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (key,),
    ).fetchone()
    if row is None:
        return None
    return str(row["status"] or "") or None


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
