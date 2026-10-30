"""Durable links between authorized price requests and shared jobs."""
from __future__ import annotations

from contextlib import nullcontext

from app.cardmarket import datetime_now
from app.cardmarket_queue import immediate_transaction


class PriceRequestConflict(Exception):
    pass


def register(conn, request_id: str, permit_id: str, sample: str) -> str | None:
    now = datetime_now()
    with getattr(conn, '_cache_lock', nullcontext()), immediate_transaction(conn):
        conn.execute("INSERT INTO paid_refresh_request (request_id,permit_id,sample_key,state,created_at,updated_at) "
                     "VALUES (?,?,?,'accepted',?,?) ON CONFLICT(request_id) DO NOTHING",
                     (request_id, permit_id, sample, now, now))
        row = conn.execute('SELECT permit_id,sample_key,job_id FROM paid_refresh_request WHERE request_id=?',
                           (request_id,)).fetchone()
        if row is None or row['permit_id'] != permit_id or row['sample_key'] != sample:
            raise PriceRequestConflict('request identity conflict')
        return row['job_id']


def attach(conn, request_id: str, job_id: str) -> None:
    with getattr(conn, '_cache_lock', nullcontext()), immediate_transaction(conn):
        conn.execute("UPDATE paid_refresh_request SET job_id=?,state='queued',updated_at=? "
                     "WHERE request_id=? AND (job_id IS NULL OR job_id=?)",
                     (job_id, datetime_now(), request_id, job_id))


def requests_for_job(conn, job_id: str, sample: str) -> list[tuple[str, str]]:
    rows = conn.execute("SELECT request_id,permit_id FROM paid_refresh_request "
                        "WHERE job_id=? AND sample_key=? AND state IN ('accepted','queued') "
                        "ORDER BY created_at LIMIT 100", (job_id, sample)).fetchall()
    return [(row['request_id'], row['permit_id']) for row in rows]
