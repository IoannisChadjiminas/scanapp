"""Recover abandoned scan executions and retry durable quota settlements."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.config import Settings
from app.db import connect
from app.scan_permit_execution import abandon_expired_claim, acknowledge, begin, fail, heartbeat, pending_settlements, prepare
from app.subscription_client import SubscriptionClient, SubscriptionUnavailable

log = logging.getLogger('scan.quota')


def admit(settings: Settings, client: SubscriptionClient, attempt: str, session: str, permit: str) -> dict:
    conn = connect(settings.results_sqlite)
    try:
        item = prepare(conn, attempt, session)
        if item['state'] != 'claiming':
            return {**item, 'state': 'already_started'}
        permit_id = client.claim_scan(permit, item['execution_id'], session, item['attempt_id'])
        if not begin(conn, item['attempt_id'], item['execution_id'], permit_id):
            return {**item, 'state': 'already_started'}
        return {**item, 'permit_id': permit_id, 'state': 'running'}
    finally:
        conn.close()


def run_once(settings: Settings, client: SubscriptionClient) -> None:
    now = datetime.now(timezone.utc)
    stamp = now.isoformat(timespec='microseconds')
    conn = connect(settings.results_sqlite)
    try:
        stale = conn.execute("SELECT attempt_id, execution_id, scan_session_id, state FROM scan_permit_execution "
                             "WHERE state IN ('claiming','running') AND lease_expires_at<=? LIMIT 100", (stamp,)).fetchall()
        for row in stale:
            try:
                if row['state'] == 'claiming':
                    remote = client.inspect_scan(row['attempt_id'], row['execution_id'], row['scan_session_id'])
                    if remote['state'] == 'expired':
                        abandon_expired_claim(conn, row['attempt_id'], row['execution_id'], now)
                        continue
                    if remote['state'] != 'claimed':
                        continue
                    if not begin(conn, row['attempt_id'], row['execution_id'], remote['permitId'], now=now):
                        continue
                    fail(conn, row['attempt_id'], row['execution_id'], now=now)
                else:
                    fail(conn, row['attempt_id'], row['execution_id'], stale_before=now, now=now)
            except SubscriptionUnavailable:
                continue
        for item in pending_settlements(conn):
            try:
                client.settle_scan(item['attempt_id'], item['execution_id'], item['scan_session_id'],
                                   item['outcome'], item['scan_id'])
                acknowledge(conn, item['attempt_id'])
            except SubscriptionUnavailable:
                continue
    finally:
        conn.close()


async def keepalive(settings: Settings, client: SubscriptionClient, attempt: str, execution: str, session: str) -> None:
    while True:
        await asyncio.sleep(60)
        def beat() -> bool:
            conn = connect(settings.results_sqlite)
            try:
                return heartbeat(conn, attempt, execution)
            finally:
                conn.close()
        if not await asyncio.to_thread(beat):
            return
        try:
            await asyncio.to_thread(client.heartbeat_scan, attempt, execution, session)
        except SubscriptionUnavailable:
            log.info('quota heartbeat unavailable')


async def run_worker(stop: asyncio.Event, settings: Settings, client: SubscriptionClient) -> None:
    while not stop.is_set():
        try:
            await asyncio.to_thread(run_once, settings, client)
        except Exception as exc:
            log.info('quota recovery unavailable error_type=%s', type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
        except TimeoutError:
            continue
        return
