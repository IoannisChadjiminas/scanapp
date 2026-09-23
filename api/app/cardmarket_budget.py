"""Paid-read budgets. Reservations are the only thing that may launch Chrome."""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from typing import Any

from app.cardmarket import datetime_now, sample_key
from app.cardmarket_queue import QueueError, immediate_transaction
from app.config import get_settings

_health_lock = threading.Lock()
_health = {"ok": False, "checked_at": 0.0, "cooldown_until": 0.0}


def note_scraper_health(ok: bool, cooldown_until: float | None = None) -> None:
    with _health_lock:
        _health["ok"] = ok
        _health["checked_at"] = time.time()
        if cooldown_until is not None:
            _health["cooldown_until"] = cooldown_until


def _hour_ago() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))


def _utc_midnight() -> str:
    return time.strftime("%Y-%m-%dT00:00:00Z", time.gmtime())


def _expire_stale_reservations(conn: sqlite3.Connection) -> None:
    settings = get_settings()
    cutoff = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ",
        time.gmtime(time.time() - settings.scraper_attempt_seconds),
    )
    conn.execute(
        """
        UPDATE cardmarket_scrapes
        SET state = 'used',
            bytes = reserved_bytes,
            outcome = 'abandoned'
        WHERE state = 'reserved' AND created_at < ?
        """,
        (cutoff,),
    )


def usage_today(conn: sqlite3.Connection) -> tuple[int, int]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS pages,
               COALESCE(SUM(CASE
                   WHEN state = 'reserved' THEN reserved_bytes
                   ELSE COALESCE(bytes, reserved_bytes)
               END), 0) AS used
        FROM cardmarket_scrapes
        WHERE created_at >= ?
          AND state IN ('reserved', 'used')
        """,
        (_utc_midnight(),),
    ).fetchone()
    return int(row["pages"] or 0), int(row["used"] or 0)


def scraper_is_ready(conn: sqlite3.Connection) -> bool:
    settings = get_settings()
    if not settings.scraper_enabled or not settings.scraper_url or not settings.scraper_api_key:
        return False
    with _health_lock:
        fresh = _health["ok"] and time.time() - _health["checked_at"] <= 90
        cooling = time.time() < _health["cooldown_until"]
    if not fresh or cooling:
        return False
    pages, used = usage_today(conn)
    return (
        pages < settings.scraper_daily_pages
        and used < settings.scraper_daily_mb * 1024 * 1024
    )


def reserve_attempt(
    conn: sqlite3.Connection, *, sample: str, session_id: str, ip: str
) -> str:
    settings = get_settings()
    reserve = settings.scraper_reserve_kb * 1024
    with immediate_transaction(conn):
        _expire_stale_reservations(conn)
        inflight = conn.execute(
            """
            SELECT 1 FROM cardmarket_scrapes
            WHERE sample_key = ? AND state = 'reserved'
            LIMIT 1
            """,
            (sample,),
        ).fetchone()
        if inflight is not None:
            raise QueueError("A paid read is already running", status_code=429)
        pages, used = usage_today(conn)
        if pages + 1 > settings.scraper_daily_pages or used + reserve > settings.scraper_daily_mb * 1024 * 1024:
            raise QueueError("Paid read budget is exhausted", status_code=429)
        reservation = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO cardmarket_scrapes (
                id, sample_key, session_id, ip, state, reserved_bytes, created_at
            ) VALUES (?, ?, ?, ?, 'reserved', ?, ?)
            """,
            (reservation, sample, session_id, ip, reserve, datetime_now()),
        )
    return reservation


def cooldown_remaining() -> float:
    with _health_lock:
        return max(0.0, float(_health["cooldown_until"]) - time.time())


def reconcile_attempt(
    conn: sqlite3.Connection,
    reservation_id: str,
    *,
    outcome: str,
    actual_bytes: int | None,
    elapsed_ms: int,
) -> None:
    """A missing measurement keeps the reserved byte estimate."""
    conn.execute(
        """
        UPDATE cardmarket_scrapes
        SET state = 'used',
            outcome = ?,
            bytes = COALESCE(?, reserved_bytes),
            elapsed_ms = ?
        WHERE id = ? AND state = 'reserved'
        """,
        (
            outcome,
            None if actual_bytes is None else max(0, int(actual_bytes)),
            int(elapsed_ms),
            reservation_id,
        ),
    )
    conn.commit()


def record_phone_challenge(
    conn: sqlite3.Connection, *, session_id: str, ip: str, url: str
) -> None:
    sample = sample_key(url)
    if not sample:
        return
    conn.execute(
        """
        INSERT INTO cardmarket_phone_challenges (id, session_id, ip, sample_key, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), session_id, ip, sample, datetime_now()),
    )
    conn.commit()


def has_recent_challenge(conn: sqlite3.Connection, session_id: str, url: str) -> bool:
    sample = sample_key(url)
    if not sample:
        return False
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 5 * 60))
    row = conn.execute(
        """
        SELECT 1 FROM cardmarket_phone_challenges
        WHERE session_id = ? AND sample_key = ? AND created_at >= ?
        LIMIT 1
        """,
        (session_id, sample, cutoff),
    ).fetchone()
    return row is not None


def url_on_cooldown(conn: sqlite3.Connection, url: str) -> bool:
    sample = sample_key(url)
    if not sample:
        return False
    cutoff = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ",
        time.gmtime(time.time() - get_settings().scraper_url_cooldown_s),
    )
    row = conn.execute(
        """
        SELECT 1 FROM cardmarket_scrapes
        WHERE sample_key = ?
          AND state = 'used'
          AND COALESCE(outcome, '') NOT IN ('offers', 'empty')
          AND created_at >= ?
        LIMIT 1
        """,
        (sample, cutoff),
    ).fetchone()
    return row is not None


def record_escalation(
    conn: sqlite3.Connection, *, session_id: str, ip: str, url: str
) -> None:
    """Count this escalation against the session and IP hourly limits."""
    settings = get_settings()
    sample = sample_key(url)
    if not sample:
        raise QueueError("Need a Cardmarket product URL")
    since = _hour_ago()
    with immediate_transaction(conn):
        session_count = conn.execute(
            """
            SELECT COUNT(*) AS n FROM cardmarket_escalations
            WHERE session_id = ? AND created_at >= ?
            """,
            (session_id, since),
        ).fetchone()
        ip_count = conn.execute(
            """
            SELECT COUNT(*) AS n FROM cardmarket_escalations
            WHERE ip = ? AND created_at >= ?
            """,
            (ip, since),
        ).fetchone()
        if int(session_count["n"] or 0) >= settings.scraper_session_hourly:
            raise QueueError("Session paid-read limit reached", status_code=429)
        if int(ip_count["n"] or 0) >= settings.scraper_ip_hourly:
            raise QueueError("Network paid-read limit reached", status_code=429)
        conn.execute(
            """
            INSERT INTO cardmarket_escalations (id, session_id, ip, sample_key, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), session_id, ip, sample, datetime_now()),
        )


def budget_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    pages, used = usage_today(conn)
    return {"pages": pages, "bytes": used, "ready": scraper_is_ready(conn)}
