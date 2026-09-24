from __future__ import annotations

import calendar
import hashlib
import logging
import hmac
import json
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator
from urllib.parse import parse_qsl, urlparse

from app.cardmarket import (
    datetime_now,
    is_job_url,
    normalize_product_url,
    sample_key,
    singles_code_and_number,
    snapshot_prices,
    snapshot_record,
    write_snapshot,
)
from app.config import get_settings

log = logging.getLogger("cardmarket.prices")

CLAIM_LIFETIME_SECONDS = 180
HELPER_ONLINE_SECONDS = 120
MAX_JOB_ATTEMPTS = 3
RETRY_DELAYS_SECONDS = (30, 90)
LISTING_FILTER_KEYS = (
    "language",
    "minCondition",
    "sellerCountry",
    "isReverseHolo",
    "isSigned",
    "isFirstEd",
)
PARSER_VERSION = "offers-v1"


def price_source(parser_version: str | None, freshness: str | None) -> str:
    """Where the number being served was produced.

    A sample inside the fresh window is cache, whatever last wrote it.
    """
    if freshness == "fresh":
        return "cache"
    version = (parser_version or "").lower()
    if version.startswith("phone"):
        return "webview"
    if version.startswith("proxy"):
        return "paid"
    if version:
        return "helper"
    return "none"


PHONE_PARSER_VERSION = "phone-offers-v1"
PROXY_PARSER_VERSION = "proxy-offers-v1"
PROXY_WORKER_ID = "proxy"
CDP_HELPER_ID = "cdp"
FRESH_SECONDS = 15 * 60
_GUIDE_LABELS = frozenset({"From", "Trend", "7-day"})
_EURO_RE = re.compile(
    r"^(?:€|EUR)?(\d{1,3}(?:\.\d{3})+,\d{2}|\d{1,3}(?:,\d{3})+\.\d{2}|\d+[.,]\d{2})(?:€|EUR)?$",
    re.IGNORECASE,
)


class QueueError(Exception):
    status_code = 400

    def __init__(self, detail: str, status_code: int | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code


class AuthError(QueueError):
    status_code = 401


class ClaimError(QueueError):
    status_code = 409


class WrongProduct(QueueError):
    status_code = 422


def is_cdp_helper(helper_id: str | None) -> bool:
    raw = str(helper_id or "").strip().lower()
    return raw == CDP_HELPER_ID or raw.startswith(f"{CDP_HELPER_ID}-")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _filters_json(filters: dict[str, str] | None) -> str:
    payload = {key: str(value) for key, value in sorted((filters or {}).items()) if value}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def split_url_and_filters(url: str | None) -> tuple[str | None, dict[str, str]]:
    raw = (url or "").strip()
    if not raw:
        return None, {}
    parts = urlparse(raw)
    filters: dict[str, str] = {}
    for key, value in parse_qsl(parts.query, keep_blank_values=False):
        if key in LISTING_FILTER_KEYS and value:
            filters[key] = value
    return normalize_product_url(raw), filters


def classify_url(url: str | None) -> str:
    raw = (url or "").strip()
    if not raw:
        return "invalid"
    parts = urlparse(raw)
    if parts.scheme.lower() != "https":
        return "invalid"
    host = (parts.netloc or "").lower().split(":")[0]
    path = (parts.path or "").rstrip("/")
    if host in {"prices.pokemontcg.io", "www.prices.pokemontcg.io"}:
        if "/cardmarket/" in path.lower():
            return "pokemontcg"
        return "invalid"
    if host not in {"www.cardmarket.com", "cardmarket.com"}:
        return "invalid"
    lowered = path.lower()
    if "/login" in lowered or lowered.endswith("/signin"):
        return "login"
    if "/products/search" in lowered or lowered.endswith("/cards"):
        return "search"
    if "/products/singles/" in lowered:
        bits = [bit for bit in path.split("/") if bit]
        if (
            len(bits) >= 6
            and bits[1].lower() == "pokemon"
            and bits[2].lower() == "products"
            and bits[3].lower() == "singles"
            and bits[-2]
            and bits[-1]
        ):
            return "product"
        if (
            len(bits) == 5
            and bits[1].lower() == "pokemon"
            and bits[2].lower() == "products"
            and bits[3].lower() == "singles"
            and bits[4]
        ):
            return "expansion"
        return "invalid"
    if "/cdn-cgi/" in lowered or "/captcha" in lowered:
        return "challenge"
    return "other"


def product_identity_from_url(url: str | None) -> str | None:
    kind = classify_url(url)
    if kind == "pokemontcg":
        pid = (url or "").rstrip("/").split("/")[-1]
        return f"pokemontcg:{pid}" if pid else None
    if kind != "product":
        return None
    coded = singles_code_and_number(url)
    if coded:
        return f"singles:{coded[0].lower()}{coded[1]}"
    parts = urlparse(url or "")
    bits = [bit for bit in (parts.path or "").split("/") if bit]
    if len(bits) >= 2:
        return f"path:{bits[-2].lower()}/{bits[-1].lower()}"
    return None


def identities_compatible(expected: str | None, actual: str | None) -> bool:
    if not expected or not actual:
        return False
    if expected.startswith("pokemontcg:"):
        return actual.startswith("singles:") or actual.startswith("path:")
    return expected == actual


def product_url_matches_job(job_url: str, final_url: str) -> bool:
    kind = classify_url(final_url)
    if kind != "product":
        return False
    expected = product_identity_from_url(job_url)
    actual = product_identity_from_url(final_url)
    return identities_compatible(expected, actual)


@contextmanager
def immediate_transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    previous = conn.isolation_level
    conn.isolation_level = None
    started = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        started = True
        yield conn
        conn.execute("COMMIT")
    except Exception:
        if started:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.isolation_level = previous


def _row_get(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    if key not in row.keys():
        return default
    value = row[key]
    return default if value is None else value


def _parse_filters(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items() if value}
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items() if value}


def job_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "url": str(row["url"]),
        "card_id": str(_row_get(row, "card_id", "") or ""),
        "status": str(row["status"] or ""),
        "attempts": int(_row_get(row, "attempts", 0) or 0),
        "helper_id": str(_row_get(row, "helper_id", "") or "") or None,
        "claim_token": str(_row_get(row, "claim_token", "") or "") or None,
        "claim_expires_at": str(_row_get(row, "claim_expires_at", "") or "") or None,
        "next_attempt_at": str(_row_get(row, "next_attempt_at", "") or "") or None,
        "failure_reason": str(_row_get(row, "failure_reason", "") or "") or None,
        "filters": _parse_filters(_row_get(row, "filters_json", "{}")),
        "product_identity": str(_row_get(row, "product_identity", "") or "") or None,
        "submission_id": str(_row_get(row, "submission_id", "") or "") or None,
        "observed_at": str(_row_get(row, "observed_at", "") or "") or None,
    }


def _iso_offset(seconds: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + seconds))


def issue_helper_credential(
    conn: sqlite3.Connection, helper_id: str | None = None
) -> tuple[str, str]:
    helper_id = helper_id or str(uuid.uuid4())
    token = f"{helper_id}.{secrets.token_urlsafe(32)}"
    now = datetime_now()
    with immediate_transaction(conn):
        conn.execute(
            """
            INSERT INTO cardmarket_helper_tokens (helper_id, token_hash, created_at, revoked_at)
            VALUES (?, ?, ?, NULL)
            ON CONFLICT(helper_id) DO UPDATE SET
                token_hash = excluded.token_hash,
                created_at = excluded.created_at,
                revoked_at = NULL
            """,
            (helper_id, hash_token(token), now),
        )
        conn.execute(
            """
            INSERT INTO cardmarket_helpers (
                helper_id, last_seen, ready, paused, attention
            ) VALUES (?, ?, 0, 0, NULL)
            ON CONFLICT(helper_id) DO UPDATE SET
                last_seen = excluded.last_seen
            """,
            (helper_id, now),
        )
    return helper_id, token


def revoke_helper_credential(conn: sqlite3.Connection, helper_id: str) -> None:
    with immediate_transaction(conn):
        conn.execute(
            """
            UPDATE cardmarket_helper_tokens
            SET revoked_at = ?
            WHERE helper_id = ?
            """,
            (datetime_now(), helper_id),
        )


def authenticate_helper(conn: sqlite3.Connection, token: str | None) -> dict[str, str]:
    raw = (token or "").strip()
    if not raw or "." not in raw:
        raise AuthError("Authentication required")
    helper_id = raw.split(".", 1)[0]
    row = conn.execute(
        """
        SELECT helper_id, token_hash, revoked_at
        FROM cardmarket_helper_tokens
        WHERE helper_id = ?
        """,
        (helper_id,),
    ).fetchone()
    if row is None or row["revoked_at"]:
        raise AuthError("Authentication required")
    if not hmac.compare_digest(str(row["token_hash"]), hash_token(raw)):
        raise AuthError("Authentication required")
    return {"helper_id": str(row["helper_id"])}


def settle_expired_claims(conn: sqlite3.Connection, now: str | None = None) -> int:
    stamp = now or datetime_now()
    cursor = conn.execute(
        """
        UPDATE cardmarket_jobs
        SET status = 'pending',
            helper_id = NULL,
            claim_token = NULL,
            claim_expires_at = NULL,
            updated_at = ?,
            next_attempt_at = ?
        WHERE status = 'claimed'
          AND claim_expires_at IS NOT NULL
          AND claim_expires_at < ?
        """,
        (stamp, stamp, stamp),
    )
    return int(cursor.rowcount or 0)


def enqueue_job(
    conn: sqlite3.Connection,
    url: str,
    card_id: str | None = None,
    filters: dict[str, str] | None = None,
    tier: str = "free",
) -> str:
    if tier == "free" and not get_settings().cardmarket_helper_enabled:
        raise QueueError("PC price helper is disabled", status_code=503)
    key, parsed = split_url_and_filters(url)
    if not key or not is_job_url(key):
        raise QueueError("Need a Cardmarket product URL")
    merged = {**parsed, **(filters or {})}
    encoded = _filters_json(merged)
    identity = product_identity_from_url(key)
    with immediate_transaction(conn):
        existing = conn.execute(
            """
            SELECT id, tier FROM cardmarket_jobs
            WHERE url = ?
              AND COALESCE(filters_json, '{}') = ?
              AND status IN ('pending', 'claimed')
            ORDER BY created_at
            LIMIT 1
            """,
            (key, encoded),
        ).fetchone()
        if existing:
            job_id = str(existing["id"])
            if tier == "proxy":
                if existing["tier"] != "proxy" and not get_settings().cardmarket_helper_enabled:
                    conn.execute(
                        """
                        UPDATE cardmarket_jobs SET status = 'pending', helper_id = NULL,
                            claim_token = NULL, claim_expires_at = NULL,
                            attempts = 0, next_attempt_at = NULL
                        WHERE id = ?
                        """,
                        (job_id,),
                    )
                conn.execute(
                    "UPDATE cardmarket_jobs SET tier = 'proxy', updated_at = ? WHERE id = ?",
                    (datetime_now(), job_id),
                )
        else:
            job_id = str(uuid.uuid4())
            now = datetime_now()
            conn.execute(
                """
                INSERT INTO cardmarket_jobs (
                    id, url, card_id, status, created_at, updated_at, attempts,
                    filters_json, product_identity, next_attempt_at, tier
                ) VALUES (?, ?, ?, 'pending', ?, ?, 0, ?, ?, ?, ?)
                """,
                (job_id, key, card_id or "", now, now, encoded, identity, now, tier),
            )
    _notify_job_url(key, merged)
    return job_id


def _notify_job_url(url: str | None, filters: dict[str, str] | None = None) -> None:
    from app.cardmarket_events import notify_product

    notify_product(url, filters)


def parse_euro_offer(value: str) -> float | None:
    text = re.sub(r"\s", "", value or "")
    if "€" not in text and "EUR" not in text.upper():
        return None
    match = _EURO_RE.fullmatch(text)
    if match is None:
        return None
    number = match.group(1)
    decimal = "," if number.rfind(",") > number.rfind(".") else "."
    number = number.replace("." if decimal == "," else ",", "")
    number = number.replace(",", ".")
    try:
        amount = float(number)
    except ValueError:
        return None
    if amount <= 0 or amount > 1_000_000:
        return None
    return amount


def rows_to_prices(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prices: list[dict[str, Any]] = []
    for row in rows:
        amount = parse_euro_offer(str(row.get("price") or ""))
        if amount is None:
            continue
        labels = []
        for field in ("condition", "language", "variant"):
            label = str(row.get(field) or "").strip()
            if label and len(label) <= 60 and not any(ord(ch) < 32 for ch in label):
                labels.append(label)
        prices.append(
            {"label": " · ".join(labels), "amount": amount, "currency": "EUR"}
        )
    return prices


def _same_prices(existing: list[dict[str, Any]], prices: list[dict[str, Any]]) -> bool:
    def key(item: dict[str, Any]) -> tuple[str, float, str]:
        return (
            str(item.get("label") or ""),
            round(float(item.get("amount") or 0), 2),
            str(item.get("currency") or "EUR"),
        )

    return [key(item) for item in existing] == [key(item) for item in prices]


def remember_phone_offers(
    conn: sqlite3.Connection,
    url: str,
    rows: list[dict[str, Any]],
    parser_version: str | None = None,
) -> bool:
    """Store a phone offer table when it is new or the fresh window has passed.

    Challenge pages, empty tables, and an unchanged sample inside the fresh
    window leave ``observed_at`` alone.
    """
    prices = rows_to_prices(rows)
    if not prices:
        return False
    key = sample_key(url)
    if not key:
        return False
    existing = snapshot_record(conn, url)
    existing_prices = list((existing or {}).get("prices") or [])
    observed = (existing or {}).get("observed_at") or (existing or {}).get("fetched_at")
    age = _age_seconds(str(observed or ""))
    if _same_prices(existing_prices, prices) and age is not None and age <= FRESH_SECONDS:
        return False
    version = parser_version or PHONE_PARSER_VERSION
    write_snapshot(
        conn,
        url,
        prices,
        parser_version=version,
        sampled_offer_count=len(prices),
    )
    log.info("price source=webview parser=%s offers=%s url=%s", version, len(prices), key)
    _notify_job_url(url)
    return True


def _stamp_epoch(stamp: str | None) -> int | None:
    if not stamp:
        return None
    try:
        return calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


def event_should_stop(payload: dict[str, Any], since: str | None) -> bool:
    """End a price stream once the sample the caller is waiting for arrives.

    ``attempted_at`` is the last empty read. It stays newer than the price the
    caller already has, so it must not close a job that is still pending or
    claimed. A newer price, or a failed job, still ends the wait.
    """
    if since:
        status = str(payload.get("status") or "")
        if status == "failed":
            return True
        start = _stamp_epoch(since)
        if start is None:
            return False
        observed = _stamp_epoch(str(payload.get("observed_at") or ""))
        if observed is not None and observed > start:
            return True
        if status in {"pending", "claimed"}:
            return False
        attempted = _stamp_epoch(str(payload.get("attempted_at") or ""))
        return attempted is not None and attempted > start
    prices = payload.get("prices") or []
    live = bool(prices) and not all(
        str(item.get("label") or "") in _GUIDE_LABELS for item in prices
    )
    return live or payload.get("status") == "done"


def job_by_id(conn: sqlite3.Connection, job_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM cardmarket_jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    if row is None:
        return None
    return job_from_row(row)


def _queue_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT status, COUNT(*) AS n
        FROM cardmarket_jobs
        GROUP BY status
        """
    ).fetchall()
    counts = {"pending": 0, "claimed": 0, "done": 0, "failed": 0}
    for row in rows:
        status = str(row["status"] or "")
        if status in counts:
            counts[status] = int(row["n"] or 0)
    counts["queued"] = counts["pending"] + counts["claimed"]
    return counts


def queue_counts(conn: sqlite3.Connection) -> dict[str, int]:
    with immediate_transaction(conn):
        settle_expired_claims(conn)
        return _queue_counts(conn)


def _active_claim_for_helper(conn: sqlite3.Connection, helper_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT rowid AS queue_row, *
        FROM cardmarket_jobs
        WHERE helper_id = ? AND status = 'claimed'
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (helper_id,),
    ).fetchone()


def _newest_pending_job(conn: sqlite3.Connection, now: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT rowid AS queue_row, *
        FROM cardmarket_jobs
        WHERE status = 'pending'
          AND COALESCE(tier, 'free') != 'proxy'
          AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
        ORDER BY created_at DESC, queue_row DESC
        LIMIT 1
        """,
        (now,),
    ).fetchone()


def _job_is_newer(candidate: sqlite3.Row, current: sqlite3.Row) -> bool:
    created = str(candidate["created_at"] or "")
    current_created = str(current["created_at"] or "")
    if created != current_created:
        return created > current_created
    return int(candidate["queue_row"] or 0) > int(_row_get(current, "queue_row", 0) or 0)


def _take_pending_job(
    conn: sqlite3.Connection, helper_id: str, row: sqlite3.Row, now: str
) -> dict[str, Any] | None:
    token = str(uuid.uuid4())
    expires = _iso_offset(CLAIM_LIFETIME_SECONDS)
    conn.execute(
        """
        UPDATE cardmarket_jobs
        SET status = 'claimed',
            helper_id = ?,
            claim_token = ?,
            claim_expires_at = ?,
            updated_at = ?,
            failure_reason = NULL
        WHERE id = ? AND status = 'pending'
        """,
        (helper_id, token, expires, now, row["id"]),
    )
    claimed = conn.execute(
        "SELECT * FROM cardmarket_jobs WHERE id = ?",
        (row["id"],),
    ).fetchone()
    return job_from_row(claimed) if claimed is not None else None


def claim_job(conn: sqlite3.Connection, helper_id: str) -> dict[str, Any] | None:
    if not get_settings().cardmarket_helper_enabled:
        return None
    parked_url = None
    with immediate_transaction(conn):
        now = datetime_now()
        settle_expired_claims(conn, now)
        active = _active_claim_for_helper(conn, helper_id)
        newest = _newest_pending_job(conn, now)
        if active is not None and newest is not None and _job_is_newer(newest, active):
            parked_url = str(active["url"] or "")
            conn.execute(
                """
                UPDATE cardmarket_jobs
                SET status = 'pending',
                    helper_id = NULL,
                    claim_token = NULL,
                    claim_expires_at = NULL,
                    updated_at = ?,
                    next_attempt_at = ?
                WHERE id = ?
                """,
                (now, now, active["id"]),
            )
            job = _take_pending_job(conn, helper_id, newest, now)
        elif active is not None:
            job = job_from_row(active)
        elif newest is None:
            job = None
        else:
            job = _take_pending_job(conn, helper_id, newest, now)
    if parked_url:
        _notify_job_url(parked_url)
    if job is not None:
        _notify_job_url(job.get("url"), job.get("filters"))
    return job


def _require_claim(
    conn: sqlite3.Connection,
    job_id: str,
    helper_id: str,
    claim_token: str,
    *,
    allow_done_submission: str | None = None,
) -> sqlite3.Row:
    now = datetime_now()
    settle_expired_claims(conn, now)
    row = conn.execute(
        "SELECT * FROM cardmarket_jobs WHERE id = ?",
        (job_id,),
    ).fetchone()
    if row is None:
        raise ClaimError("Unknown job")
    if allow_done_submission and str(row["status"] or "") == "done":
        stored = str(_row_get(row, "submission_id", "") or "")
        if stored and stored == allow_done_submission:
            if str(_row_get(row, "helper_id", "") or "") in {"", helper_id}:
                return row
        raise ClaimError("Job already completed")
    if str(row["status"] or "") != "claimed":
        raise ClaimError("Claim is not active")
    if str(_row_get(row, "helper_id", "") or "") != helper_id:
        raise ClaimError("Another helper owns this job")
    if str(_row_get(row, "claim_token", "") or "") != claim_token:
        raise ClaimError("Invalid claim")
    expires = str(_row_get(row, "claim_expires_at", "") or "")
    if expires and expires < now:
        raise ClaimError("Claim expired")
    return row


def recover_job(
    conn: sqlite3.Connection, helper_id: str, job_id: str | None, claim_token: str | None
) -> dict[str, Any] | None:
    if not get_settings().cardmarket_helper_enabled:
        return None
    with immediate_transaction(conn):
        now = datetime_now()
        settle_expired_claims(conn, now)
        if job_id and claim_token:
            try:
                row = _require_claim(conn, job_id, helper_id, claim_token)
            except ClaimError:
                return None
            return job_from_row(row)
        active = _active_claim_for_helper(conn, helper_id)
        return job_from_row(active) if active is not None else None


def renew_claim(
    conn: sqlite3.Connection, helper_id: str, job_id: str, claim_token: str
) -> dict[str, Any]:
    with immediate_transaction(conn):
        row = _require_claim(conn, job_id, helper_id, claim_token)
        expires = _iso_offset(CLAIM_LIFETIME_SECONDS)
        now = datetime_now()
        conn.execute(
            """
            UPDATE cardmarket_jobs
            SET claim_expires_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (expires, now, row["id"]),
        )
        updated = conn.execute(
            "SELECT * FROM cardmarket_jobs WHERE id = ?",
            (row["id"],),
        ).fetchone()
        return job_from_row(updated)


def release_job(
    conn: sqlite3.Connection,
    helper_id: str,
    job_id: str,
    claim_token: str,
    reason: str | None = None,
    *,
    delay_seconds: float = 0,
) -> dict[str, Any]:
    with immediate_transaction(conn):
        row = _require_claim(conn, job_id, helper_id, claim_token)
        now = datetime_now()
        if delay_seconds > 0:
            next_at = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + delay_seconds)
            )
        else:
            next_at = now
        conn.execute(
            """
            UPDATE cardmarket_jobs
            SET status = 'pending',
                helper_id = NULL,
                claim_token = NULL,
                claim_expires_at = NULL,
                updated_at = ?,
                next_attempt_at = ?,
                failure_reason = ?
            WHERE id = ?
            """,
            (now, next_at, reason, row["id"]),
        )
        return {"id": str(row["id"]), "status": "pending", "url": str(row["url"])}


def complete_job(
    conn: sqlite3.Connection,
    helper_id: str,
    job_id: str,
    claim_token: str,
    *,
    submission_id: str,
    url: str,
    prices: list[dict[str, Any]],
    empty: bool = False,
    observed_at: str | None = None,
    parser_version: str | None = None,
    sampled_offer_count: int | None = None,
) -> dict[str, Any]:
    final_url = normalize_product_url(url)
    if not final_url:
        raise QueueError("Need a Cardmarket URL")
    kind = classify_url(final_url)
    if kind in {"login", "challenge"}:
        raise QueueError("Cardmarket needs attention", status_code=409)
    if kind != "product":
        raise WrongProduct("Wrong product")
    with immediate_transaction(conn):
        row = _require_claim(
            conn,
            job_id,
            helper_id,
            claim_token,
            allow_done_submission=submission_id,
        )
        job = job_from_row(row)
        if job["status"] == "done" and job["submission_id"] == submission_id:
            record = snapshot_record(conn, job["url"], job.get("filters"))
            result = {
                "url": (record or {}).get("url")
                or sample_key(job["url"], job.get("filters"))
                or job["url"],
                "prices": (record or {}).get("prices") or [],
                "status": "done",
                "observed_at": (record or {}).get("observed_at"),
                "sampled_offer_count": (record or {}).get("sampled_offer_count"),
                "idempotent": True,
            }
        else:
            if not product_url_matches_job(job["url"], final_url):
                raise WrongProduct("Wrong product")
            if not prices and not empty:
                raise QueueError("Need at least one price or an explicit empty observation")
            stamp = observed_at or datetime_now()
            parser = parser_version or PARSER_VERSION
            sampled = sampled_offer_count if sampled_offer_count is not None else len(prices)
            urls = [job["url"]]
            if final_url not in urls:
                urls.append(final_url)
            saved = final_url
            for target in urls:
                saved = write_snapshot(
                    conn,
                    target,
                    prices,
                    filters=job["filters"] if target == job["url"] else None,
                    observed_at=stamp,
                    parser_version=parser,
                    sampled_offer_count=sampled,
                    submission_id=submission_id,
                    allow_empty=empty,
                    empty_source=parser,
                    commit=False,
                )
            log.info(
                "price source=%s parser=%s offers=%s empty=%s url=%s",
                price_source(parser, None),
                parser,
                len(prices),
                empty,
                saved,
            )
            now = datetime_now()
            conn.execute(
                """
                UPDATE cardmarket_jobs
                SET status = 'done',
                    updated_at = ?,
                    submission_id = ?,
                    observed_at = ?,
                    failure_reason = NULL,
                    claim_expires_at = NULL
                WHERE id = ?
                """,
                (now, submission_id, stamp, job_id),
            )
            result = {
                "url": saved,
                "prices": prices,
                "status": "done",
                "observed_at": stamp,
                "sampled_offer_count": sampled,
                "idempotent": False,
            }
    _notify_job_url(job["url"] if job else None, (job or {}).get("filters"))
    _notify_job_url(final_url)
    return result


def retry_or_fail_job(
    conn: sqlite3.Connection,
    job_id: str,
    *,
    helper_id: str | None = None,
    claim_token: str | None = None,
    reason: str | None = None,
    terminal: bool = False,
) -> str:
    product_url = None
    with immediate_transaction(conn):
        if helper_id and claim_token:
            row = _require_claim(conn, job_id, helper_id, claim_token)
        else:
            fetched = conn.execute(
                "SELECT * FROM cardmarket_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if fetched is None:
                return "failed"
            row = fetched
        product_url = str(row["url"] or "")
        product_filters = _parse_filters(_row_get(row, "filters_json", "{}"))
        attempts = int(_row_get(row, "attempts", 0) or 0) + 1
        now = datetime_now()
        if terminal or attempts >= MAX_JOB_ATTEMPTS:
            conn.execute(
                """
                UPDATE cardmarket_jobs
                SET status = 'failed',
                    attempts = ?,
                    updated_at = ?,
                    helper_id = NULL,
                    claim_token = NULL,
                    claim_expires_at = NULL,
                    failure_reason = ?
                WHERE id = ?
                """,
                (attempts, now, reason, job_id),
            )
            status = "failed"
        else:
            delay = RETRY_DELAYS_SECONDS[min(attempts, len(RETRY_DELAYS_SECONDS)) - 1]
            conn.execute(
                """
                UPDATE cardmarket_jobs
                SET status = 'pending',
                    attempts = ?,
                    updated_at = ?,
                    helper_id = NULL,
                    claim_token = NULL,
                    claim_expires_at = NULL,
                    next_attempt_at = ?,
                    failure_reason = ?
                WHERE id = ?
                """,
                (attempts, now, _iso_offset(delay), reason, job_id),
            )
            status = "pending"
    log.info(
        "job %s reason=%s attempt=%s url=%s",
        status,
        (reason or "none")[:80],
        attempts,
        product_url,
    )
    _notify_job_url(product_url, product_filters)
    return status


def complete_job_status(conn: sqlite3.Connection, job_id: str, status: str = "done") -> None:
    conn.execute(
        "UPDATE cardmarket_jobs SET status = ?, updated_at = ? WHERE id = ?",
        (status, datetime_now(), job_id),
    )
    conn.commit()


def update_helper_status(
    conn: sqlite3.Connection,
    helper_id: str,
    *,
    ready: bool | None = None,
    paused: bool | None = None,
    attention: str | None = None,
    current_job_id: str | None = None,
    success: bool | None = None,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    now = datetime_now()
    with immediate_transaction(conn):
        row = conn.execute(
            "SELECT * FROM cardmarket_helpers WHERE helper_id = ?",
            (helper_id,),
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO cardmarket_helpers (
                    helper_id, last_seen, ready, paused, attention, current_job_id
                ) VALUES (?, ?, 0, 0, NULL, NULL)
                """,
                (helper_id, now),
            )
            row = conn.execute(
                "SELECT * FROM cardmarket_helpers WHERE helper_id = ?",
                (helper_id,),
            ).fetchone()
        ready_value = int(row["ready"] or 0) if ready is None else int(bool(ready))
        paused_value = int(row["paused"] or 0) if paused is None else int(bool(paused))
        attention_value = row["attention"] if attention is None else attention
        current = row["current_job_id"] if current_job_id is None else current_job_id
        last_success = row["last_success_at"]
        last_failure = row["last_failure_at"]
        last_failure_reason = row["last_failure_reason"]
        if success is True:
            last_success = now
        if success is False:
            last_failure = now
            last_failure_reason = failure_reason
        conn.execute(
            """
            UPDATE cardmarket_helpers
            SET last_seen = ?,
                ready = ?,
                paused = ?,
                attention = ?,
                current_job_id = ?,
                last_success_at = ?,
                last_failure_at = ?,
                last_failure_reason = ?
            WHERE helper_id = ?
            """,
            (
                now,
                ready_value,
                paused_value,
                attention_value,
                current,
                last_success,
                last_failure,
                last_failure_reason,
                helper_id,
            ),
        )
        counts = _queue_counts(conn)
        state = helper_public_state(conn)
        return {**state, **counts, "helper_id": helper_id}


def _age_seconds(stamp: str | None) -> float | None:
    epoch = _stamp_epoch(stamp)
    if epoch is None:
        return None
    return time.time() - epoch


def helper_public_state(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = (
        conn.execute("SELECT * FROM cardmarket_helpers").fetchall()
        if get_settings().cardmarket_helper_enabled else []
    )
    online_rows = []
    for row in rows:
        age = _age_seconds(str(row["last_seen"] or ""))
        if age is not None and 0 <= age <= HELPER_ONLINE_SECONDS:
            online_rows.append(row)
    online = bool(online_rows)
    paused = bool(online_rows) and all(int(row["paused"] or 0) for row in online_rows)
    ready = any(
        int(row["ready"] or 0) and not int(row["paused"] or 0) and not row["attention"]
        for row in online_rows
    )
    attention = next(
        (str(row["attention"]) for row in online_rows if row["attention"]),
        None,
    )
    cdp_rows = [row for row in online_rows if is_cdp_helper(row["helper_id"])]
    cdp_online = bool(cdp_rows)
    cdp_ready = any(
        int(row["ready"] or 0) and not int(row["paused"] or 0) and not row["attention"]
        for row in cdp_rows
    )
    return {
        "helper_online": online,
        "helper_ready": ready,
        "helper_paused": paused,
        "helper_attention": attention,
        "cdp_online": cdp_online,
        "cdp_ready": cdp_ready,
    }


def helper_is_online(conn: sqlite3.Connection, *, within_seconds: int = HELPER_ONLINE_SECONDS) -> bool:
    del within_seconds
    return bool(helper_public_state(conn)["helper_online"])


def latest_job_status(conn: sqlite3.Connection, url: str | None) -> str | None:
    key, filters = split_url_and_filters(url)
    if not key:
        return None
    encoded = _filters_json(filters)
    helpers_enabled = get_settings().cardmarket_helper_enabled
    active = conn.execute(
        """
        SELECT status FROM cardmarket_jobs
        WHERE url = ?
          AND COALESCE(filters_json, '{}') = ?
          AND (? OR COALESCE(tier, 'free') = 'proxy')
          AND status IN ('pending', 'claimed')
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (key, encoded, helpers_enabled),
    ).fetchone()
    if active is not None:
        return str(active["status"] or "") or None
    row = conn.execute(
        """
        SELECT status FROM cardmarket_jobs
        WHERE url = ?
          AND COALESCE(filters_json, '{}') = ?
          AND (? OR COALESCE(tier, 'free') = 'proxy')
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (key, encoded, helpers_enabled),
    ).fetchone()
    if row is None:
        return None
    return str(row["status"] or "") or None


def prices_payload(
    conn: sqlite3.Connection, url: str | None, *, announce: bool = False
) -> dict[str, Any]:
    from app.cardmarket_budget import scraper_block_reason, scraper_is_ready, scraper_online

    sample = sample_key(url)
    record = snapshot_record(conn, url) if sample else None
    state = helper_public_state(conn)
    status = latest_job_status(conn, url)
    unlisted = bool((record or {}).get("unlisted"))
    prices = [] if unlisted else list((record or {}).get("prices") or [])
    observed = (record or {}).get("observed_at") or (record or {}).get("fetched_at")
    if unlisted or (not prices and (record or {}).get("empty_count")):
        observed = (record or {}).get("empty_observed_at") or observed
    freshness = None
    if record and (prices or unlisted or record.get("empty")):
        age = _age_seconds(str(observed or ""))
        if age is None:
            freshness = "live"
        elif age <= FRESH_SECONDS:
            freshness = "fresh"
        else:
            freshness = "stale"
    parser = (record or {}).get("parser_version")
    if announce:
        block = scraper_block_reason(conn)
        log.info(
            "price source=%s freshness=%s parser=%s scraper=%s reason=%s url=%s",
            price_source(str(parser) if parser else None, freshness),
            freshness or "none",
            parser or "none",
            "online" if scraper_online() else "offline",
            block or "ready",
            sample or "",
        )
    return {
        "url": sample,
        "prices": prices,
        "status": status,
        "observed_at": observed,
        "sampled_offer_count": (record or {}).get("sampled_offer_count"),
        "freshness": freshness,
        "unlisted": unlisted,
        "attempted_at": (record or {}).get("empty_observed_at"),
        "scraper_ready": scraper_is_ready(conn),
        "webview_enabled": get_settings().cardmarket_webview_enabled,
        **state,
    }


def touch_helper(conn: sqlite3.Connection) -> None:
    update_helper_status(conn, "legacy", ready=False, paused=False)


def claim_proxy_job(conn: sqlite3.Connection, worker_id: str = PROXY_WORKER_ID) -> dict[str, Any] | None:
    with immediate_transaction(conn):
        now = datetime_now()
        settle_expired_claims(conn, now)
        row = conn.execute(
            """
            SELECT rowid AS queue_row, *
            FROM cardmarket_jobs
            WHERE status = 'pending'
              AND COALESCE(tier, 'free') = 'proxy'
              AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
            ORDER BY created_at ASC, rowid ASC
            LIMIT 1
            """,
            (now,),
        ).fetchone()
        if row is None:
            return None
        job = _take_pending_job(conn, worker_id, row, now)
    if job is not None:
        _notify_job_url(job.get("url"), job.get("filters"))
    return job


def renew_proxy_job(
    conn: sqlite3.Connection, job_id: str, claim_token: str, worker_id: str = PROXY_WORKER_ID
) -> dict[str, Any]:
    return renew_claim(conn, worker_id, job_id, claim_token)


def complete_proxy_job(
    conn: sqlite3.Connection,
    job_id: str,
    claim_token: str,
    *,
    url: str,
    prices: list[dict[str, Any]],
    empty: bool = False,
    submission_id: str,
    observed_at: str | None = None,
    worker_id: str = PROXY_WORKER_ID,
    sampled_offer_count: int | None = None,
) -> dict[str, Any]:
    return complete_job(
        conn,
        worker_id,
        job_id,
        claim_token,
        submission_id=submission_id,
        url=url,
        prices=prices,
        empty=empty,
        observed_at=observed_at,
        parser_version=PROXY_PARSER_VERSION,
        sampled_offer_count=sampled_offer_count,
    )


def fail_proxy_job(
    conn: sqlite3.Connection,
    job_id: str,
    claim_token: str,
    reason: str,
    *,
    terminal: bool = False,
    worker_id: str = PROXY_WORKER_ID,
) -> str:
    return retry_or_fail_job(
        conn,
        job_id,
        helper_id=worker_id,
        claim_token=claim_token,
        reason=reason,
        terminal=terminal,
    )


def sample_is_fresh(conn: sqlite3.Connection, url: str) -> bool:
    record = snapshot_record(conn, url)
    if not record or record.get("unlisted") or not record.get("prices"):
        return False
    age = _age_seconds(str(record.get("observed_at") or ""))
    return age is not None and 0 <= age <= FRESH_SECONDS
