"""Cross-process single-flight leases for paid listing reads."""
from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from app.cardmarket_queue import immediate_transaction


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds')


def acquire(conn: sqlite3.Connection, sample: str, worker: str, seconds: int, *, now: datetime | None = None) -> str | None:
    now = now or datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    with immediate_transaction(conn):
        row = conn.execute(
            "INSERT INTO paid_sample_lease (sample_key, claim_token, worker_id, expires_at, created_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(sample_key) DO UPDATE SET "
            "claim_token=excluded.claim_token, worker_id=excluded.worker_id, "
            "expires_at=excluded.expires_at, created_at=excluded.created_at "
            "WHERE paid_sample_lease.expires_at <= excluded.created_at RETURNING claim_token",
            (sample, token, worker, _stamp(now + timedelta(seconds=max(1, seconds))), _stamp(now)),
        ).fetchone()
        return token if row is not None else None


def release(conn: sqlite3.Connection, sample: str, token: str) -> bool:
    with immediate_transaction(conn):
        cursor = conn.execute('DELETE FROM paid_sample_lease WHERE sample_key=? AND claim_token=?', (sample, token))
        return cursor.rowcount == 1
