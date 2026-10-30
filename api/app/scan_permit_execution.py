"""Durable scan admission and settlement state, without storing permit secrets.

Callers prepare before claiming the product API permit and must atomically move
to running before starting recognition. A running attempt is never restarted.
The recognition insert and ``record_result`` must share one SQLite transaction.
"""
from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from app.cardmarket_queue import immediate_transaction


class ExecutionConflict(Exception):
    pass


def _timestamp(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat(timespec='microseconds')


def _uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError) as exc:
        raise ExecutionConflict('invalid execution identity') from exc


def prepare(conn: sqlite3.Connection, attempt_id: str, session_id: str, *, now: datetime | None = None) -> dict:
    attempt_id, session_id = _uuid(attempt_id), _uuid(session_id)
    now = now or datetime.now(timezone.utc)
    digest = hashlib.sha256(session_id.encode()).hexdigest()
    with immediate_transaction(conn):
        conn.execute(
            "INSERT INTO scan_permit_execution "
            "(attempt_id, execution_id, scan_session_id, scan_session_hash, state, lease_expires_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'claiming', ?, ?, ?) ON CONFLICT(attempt_id) DO NOTHING",
            (attempt_id, str(uuid.uuid4()), session_id, digest, _timestamp(now + timedelta(minutes=5)),
             _timestamp(now), _timestamp(now)),
        )
        row = conn.execute('SELECT * FROM scan_permit_execution WHERE attempt_id=?', (attempt_id,)).fetchone()
        if row is None or row['scan_session_id'] != session_id or row['scan_session_hash'] != digest:
            raise ExecutionConflict('attempt is owned by another session')
        return dict(row)


def begin(conn: sqlite3.Connection, attempt_id: str, execution_id: str, permit_id: str,
          *, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    with immediate_transaction(conn):
        row = conn.execute(
            "UPDATE scan_permit_execution SET state='running', permit_id=?, updated_at=?, lease_expires_at=? "
            "WHERE attempt_id=? AND execution_id=? AND state='claiming' RETURNING attempt_id",
            (permit_id, _timestamp(now), _timestamp(now + timedelta(minutes=5)), attempt_id, execution_id),
        ).fetchone()
        return row is not None


def record_result(conn: sqlite3.Connection, attempt_id: str, execution_id: str, scan_id: str,
                  outcome: str, *, now: datetime | None = None) -> None:
    """Add the outbox record in the same transaction as the persisted scan."""
    if outcome not in {'usable', 'retake', 'no_match', 'failed', 'cancelled'}:
        raise ValueError('invalid scan outcome')
    now = now or datetime.now(timezone.utc)
    stamp = _timestamp(now)
    row = conn.execute(
        "UPDATE scan_permit_execution SET state='completed', scan_id=?, outcome=?, updated_at=? "
        "WHERE attempt_id=? AND execution_id=? AND state='running' RETURNING permit_id, scan_session_id",
        (scan_id, outcome, stamp, attempt_id, execution_id),
    ).fetchone()
    if row is None:
        raise ExecutionConflict('attempt is not running')
    updated = conn.execute(
        'UPDATE scans SET product_scan_attempt_id=?, product_scan_permit_id=? WHERE id=? AND session_id=?',
        (attempt_id, row['permit_id'], scan_id, row['scan_session_id']),
    )
    if updated.rowcount != 1:
        raise ExecutionConflict('scan does not belong to attempt session')
    conn.execute(
        'INSERT INTO scan_permit_settlement (attempt_id, permit_id, scan_id, outcome, retry_at, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (attempt_id, row['permit_id'], scan_id, outcome, stamp, stamp),
    )


def fail(conn: sqlite3.Connection, attempt_id: str, execution_id: str, *, stale_before: datetime | None = None,
         now: datetime | None = None) -> bool:
    """Durably release an admitted execution; stale recovery is fenced by its lease."""
    now = now or datetime.now(timezone.utc)
    stamp = _timestamp(now)
    with immediate_transaction(conn):
        row = conn.execute(
            "UPDATE scan_permit_execution SET state='failed', outcome='failed', updated_at=? "
            "WHERE attempt_id=? AND execution_id=? AND state='running' "
            "AND (? IS NULL OR lease_expires_at<=?) RETURNING permit_id",
            (stamp, attempt_id, execution_id, None if stale_before is None else _timestamp(stale_before),
             None if stale_before is None else _timestamp(stale_before)),
        ).fetchone()
        if row is None:
            return False
        conn.execute(
            "INSERT INTO scan_permit_settlement (attempt_id, permit_id, outcome, retry_at, created_at) "
            "VALUES (?, ?, 'failed', ?, ?)", (attempt_id, row['permit_id'], stamp, stamp),
        )
        return True


def heartbeat(conn: sqlite3.Connection, attempt_id: str, execution_id: str, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    with immediate_transaction(conn):
        row = conn.execute(
            "UPDATE scan_permit_execution SET lease_expires_at=?, updated_at=? "
            "WHERE attempt_id=? AND execution_id=? AND state='running' RETURNING attempt_id",
            (_timestamp(now + timedelta(minutes=5)), _timestamp(now), attempt_id, execution_id),
        ).fetchone()
        return row is not None


def abandon_expired_claim(conn: sqlite3.Connection, attempt_id: str, execution_id: str, now: datetime) -> None:
    with immediate_transaction(conn):
        conn.execute("UPDATE scan_permit_execution SET state='failed', outcome='failed', updated_at=? "
                     "WHERE attempt_id=? AND execution_id=? AND state='claiming' AND lease_expires_at<=?",
                     (_timestamp(now), attempt_id, execution_id, _timestamp(now)))


def pending_settlements(conn: sqlite3.Connection, *, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        "SELECT s.attempt_id, s.scan_id, s.outcome, e.execution_id, e.scan_session_id "
        "FROM scan_permit_settlement s JOIN scan_permit_execution e ON e.attempt_id=s.attempt_id "
        "WHERE s.state='pending' ORDER BY s.created_at LIMIT ?", (max(1, min(limit, 500)),),
    ).fetchall()
    return [dict(row) for row in rows]


def acknowledge(conn: sqlite3.Connection, attempt_id: str, *, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    with immediate_transaction(conn):
        conn.execute("UPDATE scan_permit_settlement SET state='acknowledged', acknowledged_at=? "
                     "WHERE attempt_id=? AND state='pending'", (_timestamp(now), attempt_id))
