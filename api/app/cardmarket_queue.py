from __future__ import annotations

import calendar
import hashlib
import hmac
import json
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
    singles_code_and_number,
    snapshot_prices,
    snapshot_record,
    write_snapshot,
)

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
    if "challenge" in lowered or "/captcha" in lowered:
        return "challenge"
    if "/products/search" in lowered or lowered.endswith("/cards"):
        return "search"
    if "/products/singles/" in lowered:
        bits = [bit for bit in path.split("/") if bit]
        if len(bits) >= 5 and bits[-2] and bits[-1]:
            return "product"
        return "invalid"
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
    if not actual:
        return False
    if not expected or expected.startswith("pokemontcg:"):
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
) -> str:
    key, parsed = split_url_and_filters(url)
    if not key or not is_job_url(key):
        raise QueueError("Need a Cardmarket product URL")
    merged = {**parsed, **(filters or {})}
    encoded = _filters_json(merged)
    identity = product_identity_from_url(key)
    with immediate_transaction(conn):
        existing = conn.execute(
            """
            SELECT id FROM cardmarket_jobs
            WHERE url = ?
              AND COALESCE(filters_json, '{}') = ?
              AND status IN ('pending', 'claimed')
            ORDER BY created_at
            LIMIT 1
            """,
            (key, encoded),
        ).fetchone()
        if existing:
            return str(existing["id"])
        job_id = str(uuid.uuid4())
        now = datetime_now()
        conn.execute(
            """
            INSERT INTO cardmarket_jobs (
                id, url, card_id, status, created_at, updated_at, attempts,
                filters_json, product_identity, next_attempt_at
            ) VALUES (?, ?, ?, 'pending', ?, ?, 0, ?, ?, ?)
            """,
            (job_id, key, card_id or "", now, now, encoded, identity, now),
        )
        return job_id


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
        SELECT * FROM cardmarket_jobs
        WHERE helper_id = ? AND status = 'claimed'
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (helper_id,),
    ).fetchone()


def claim_job(conn: sqlite3.Connection, helper_id: str) -> dict[str, Any] | None:
    with immediate_transaction(conn):
        now = datetime_now()
        settle_expired_claims(conn, now)
        active = _active_claim_for_helper(conn, helper_id)
        if active is not None:
            return job_from_row(active)
        row = conn.execute(
            """
            SELECT * FROM cardmarket_jobs
            WHERE status = 'pending'
              AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
            ORDER BY created_at
            LIMIT 1
            """,
            (now,),
        ).fetchone()
        if row is None:
            return None
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
) -> dict[str, Any]:
    with immediate_transaction(conn):
        row = _require_claim(conn, job_id, helper_id, claim_token)
        now = datetime_now()
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
            (now, now, reason, row["id"]),
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
            record = snapshot_record(conn, job["url"]) or snapshot_record(conn, final_url)
            return {
                "url": (record or {}).get("url") or job["url"],
                "prices": (record or {}).get("prices") or [],
                "status": "done",
                "observed_at": (record or {}).get("observed_at"),
                "sampled_offer_count": (record or {}).get("sampled_offer_count"),
                "idempotent": True,
            }
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
                observed_at=stamp,
                parser_version=parser,
                sampled_offer_count=sampled,
                submission_id=submission_id,
                allow_empty=empty,
                commit=False,
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
        return {
            "url": saved,
            "prices": prices,
            "status": "done",
            "observed_at": stamp,
            "sampled_offer_count": sampled,
            "idempotent": False,
        }


def retry_or_fail_job(
    conn: sqlite3.Connection,
    job_id: str,
    *,
    helper_id: str | None = None,
    claim_token: str | None = None,
    reason: str | None = None,
    terminal: bool = False,
) -> str:
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
            return "failed"
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
        return "pending"


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
    if not stamp:
        return None
    try:
        parsed = time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return None
    return time.time() - calendar.timegm(parsed)


def helper_public_state(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute("SELECT * FROM cardmarket_helpers").fetchall()
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
    return {
        "helper_online": online,
        "helper_ready": ready,
        "helper_paused": paused,
        "helper_attention": attention,
    }


def helper_is_online(conn: sqlite3.Connection, *, within_seconds: int = HELPER_ONLINE_SECONDS) -> bool:
    del within_seconds
    return bool(helper_public_state(conn)["helper_online"])


def latest_job_status(conn: sqlite3.Connection, url: str | None) -> str | None:
    key = normalize_product_url(url)
    if not key:
        return None
    active = conn.execute(
        """
        SELECT status FROM cardmarket_jobs
        WHERE url = ?
          AND status IN ('pending', 'claimed')
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (key,),
    ).fetchone()
    if active is not None:
        return str(active["status"] or "") or None
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


def prices_payload(conn: sqlite3.Connection, url: str | None) -> dict[str, Any]:
    key = normalize_product_url(url)
    record = snapshot_record(conn, key) if key else None
    state = helper_public_state(conn)
    status = latest_job_status(conn, key)
    observed = (record or {}).get("observed_at") or (record or {}).get("fetched_at")
    freshness = None
    if record and (record.get("prices") or record.get("empty")):
        age = _age_seconds(str(observed or ""))
        if age is None:
            freshness = "live"
        elif age <= 15 * 60:
            freshness = "fresh"
        else:
            freshness = "stale"
    return {
        "url": key,
        "prices": (record or {}).get("prices") or [],
        "status": status,
        "observed_at": observed,
        "sampled_offer_count": (record or {}).get("sampled_offer_count"),
        "freshness": freshness,
        **state,
    }


def touch_helper(conn: sqlite3.Connection) -> None:
    update_helper_status(conn, "legacy", ready=False, paused=False)
