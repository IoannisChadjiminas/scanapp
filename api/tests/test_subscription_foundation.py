from datetime import datetime, timedelta, timezone
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import pytest

from app.config import Settings
from app.db import connect, init_catalog, init_results
from app.paid_sample_lease import acquire, release
from app.subscription_client import SubscriptionClient, SubscriptionUnavailable
from app.scan_permit_execution import ExecutionConflict, begin, prepare, record_result
from app.scan_settlement_worker import admit, run_once


def test_schema_is_additive_and_repeatable(tmp_path):
    catalog = connect(tmp_path / 'catalog.sqlite')
    results = connect(tmp_path / 'results.sqlite')
    try:
        for _ in range(2):
            init_catalog(catalog)
            init_results(results)
        assert 'product_refresh_request_id' in {row['name'] for row in catalog.execute('PRAGMA table_info(cardmarket_jobs)')}
        assert 'product_scan_attempt_id' in {row['name'] for row in results.execute('PRAGMA table_info(scans)')}
        assert results.execute("SELECT name FROM sqlite_master WHERE name='scan_permit_settlement'").fetchone()
    finally:
        catalog.close()
        results.close()


def test_paid_lease_excludes_other_workers_and_fences_stale_releases(tmp_path):
    path = tmp_path / 'catalog.sqlite'
    first, second = connect(path), connect(path)
    try:
        init_catalog(first)
        now = datetime(2026, 10, 29, tzinfo=timezone.utc)
        old = acquire(first, 'listing', 'one', 30, now=now)
        assert old
        assert acquire(second, 'listing', 'two', 30, now=now) is None
        current = acquire(second, 'listing', 'two', 30, now=now + timedelta(seconds=31))
        assert current and current != old
        assert not release(first, 'listing', old)
        assert release(second, 'listing', current)
    finally:
        first.close()
        second.close()


def test_product_api_checks_fail_closed_and_validate_responses():
    with pytest.raises(SubscriptionUnavailable):
        SubscriptionClient(Settings())
    settings = Settings(product_api_url='https://product.example', scanapp_service_token='x' * 32)
    def handler(request):
        assert request.headers['authorization'] == 'Bearer ' + 'x' * 32
        if request.url.path.endswith('/eligible'):
            return httpx.Response(200, json={'samples': ['sample']})
        return httpx.Response(200, json={'items': ['sample'], 'next': None, 'refresh': {}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        client = SubscriptionClient(settings, client=transport)
        assert client.eligible('sample')
        assert not client.eligible('other')
        assert client.candidates()[0] == ['sample']
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as transport:
        with pytest.raises(SubscriptionUnavailable):
            SubscriptionClient(settings, client=transport).eligible('sample')


def test_scan_attempt_is_single_execution_and_result_and_outbox_commit_together(tmp_path):
    conn = connect(tmp_path / 'results.sqlite')
    init_results(conn)
    session, attempt = str(uuid.uuid4()), str(uuid.uuid4())
    conn.execute('INSERT INTO sessions(id,created_at,last_seen) VALUES (?, ?, ?)', (session, 'now', 'now'))
    conn.commit()
    execution = prepare(conn, attempt, session)
    assert prepare(conn, attempt, session)['execution_id'] == execution['execution_id']
    with pytest.raises(ExecutionConflict):
        prepare(conn, attempt, str(uuid.uuid4()))
    assert begin(conn, attempt, execution['execution_id'], '42')
    assert not begin(conn, attempt, execution['execution_id'], '42')
    conn.execute("INSERT INTO scans(id,session_id,created_at,status,preprocessing) VALUES ('scan', ?, 'now', 'matched', 'pad')", (session,))
    record_result(conn, attempt, execution['execution_id'], 'scan', 'usable')
    conn.rollback()
    assert conn.execute('SELECT id FROM scans').fetchone() is None
    assert conn.execute('SELECT attempt_id FROM scan_permit_settlement').fetchone() is None
    assert conn.execute('SELECT state FROM scan_permit_execution').fetchone()['state'] == 'running'
    conn.execute("INSERT INTO scans(id,session_id,created_at,status,preprocessing) VALUES ('scan', ?, 'now', 'matched', 'pad')", (session,))
    record_result(conn, attempt, execution['execution_id'], 'scan', 'usable')
    conn.commit()
    assert conn.execute('SELECT product_scan_attempt_id FROM scans').fetchone()[0] == attempt
    assert conn.execute('SELECT outcome FROM scan_permit_settlement').fetchone()[0] == 'usable'
    with pytest.raises(ExecutionConflict):
        record_result(conn, attempt, execution['execution_id'], 'scan', 'usable')
    conn.close()


def test_scan_service_requires_matching_attempt_and_confirmed_settlement():
    settings = Settings(product_api_url='https://product.example', scanapp_service_token='x' * 32)
    def handler(request):
        if request.url.path.endswith('/claim'):
            return httpx.Response(200, json={'state': 'claimed', 'attemptId': 'attempt', 'permitId': '42'})
        if request.url.path.endswith('/heartbeat'):
            return httpx.Response(200, json={'state': 'claimed'})
        return httpx.Response(200, json={'state': 'settled', 'outcome': 'usable'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        client = SubscriptionClient(settings, client=transport)
        assert client.claim_scan('secret', 'execution', 'session', 'attempt') == '42'
        with pytest.raises(SubscriptionUnavailable):
            client.claim_scan('secret', 'execution', 'session', 'other')
        client.heartbeat_scan('attempt', 'execution', 'session')
        client.settle_scan('attempt', 'execution', 'session', 'usable', 'scan')
        with pytest.raises(SubscriptionUnavailable):
            client.settle_scan('attempt', 'execution', 'session', 'retake')


def test_simultaneous_admissions_start_only_one_recognition(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    conn = connect(settings.results_sqlite)
    init_results(conn)
    session, attempt = str(uuid.uuid4()), str(uuid.uuid4())
    conn.execute('INSERT INTO sessions(id,created_at,last_seen) VALUES (?, ?, ?)', (session, 'now', 'now'))
    conn.commit()
    barrier = Barrier(2)
    class Product:
        def claim_scan(self, *_args):
            barrier.wait(timeout=3)
            return '99'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(admit, settings, Product(), attempt, session, 'secret') for _ in range(2)]
        states = sorted(f.result()['state'] for f in futures)
    assert states == ['already_started', 'running']
    conn.close()


def test_recovery_releases_abandoned_claim_and_retries_settlement(tmp_path):
    settings = Settings(_env_file=None, data_dir=tmp_path)
    conn = connect(settings.results_sqlite)
    init_results(conn)
    session, attempt = str(uuid.uuid4()), str(uuid.uuid4())
    conn.execute('INSERT INTO sessions(id,created_at,last_seen) VALUES (?, ?, ?)', (session, 'now', 'now'))
    conn.commit()
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    prepared = prepare(conn, attempt, session, now=old)
    class Product:
        def __init__(self): self.calls = 0
        def inspect_scan(self, a, e, s):
            assert (a, e, s) == (attempt, prepared['execution_id'], session)
            return {'state': 'claimed', 'permitId': '99'}
        def settle_scan(self, a, e, s, outcome, scan_id):
            assert (a, e, s, outcome, scan_id) == (attempt, prepared['execution_id'], session, 'failed', None)
            self.calls += 1
            if self.calls == 1:
                raise SubscriptionUnavailable('offline')
    client = Product()
    run_once(settings, client)
    row = conn.execute('SELECT outcome,state FROM scan_permit_settlement').fetchone()
    assert (row['outcome'], row['state']) == ('failed', 'pending')
    run_once(settings, client)
    run_once(settings, client)
    assert client.calls == 2
    assert conn.execute('SELECT state FROM scan_permit_settlement').fetchone()['state'] == 'acknowledged'
    conn.close()
