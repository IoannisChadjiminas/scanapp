"""Optional real transaction tests; only a disposable loopback *_test DB is accepted."""

from concurrent.futures import ThreadPoolExecutor
import os
import time
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.config import Settings
from app.routes.internal import router


@pytest.fixture
def pg_service(monkeypatch):
    url = os.environ.get("SCANAPP_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set SCANAPP_TEST_DATABASE_URL to a disposable loopback *_test DB")
    parts = urlsplit(url)
    if parts.hostname not in {"127.0.0.1", "localhost", "::1"} or not parts.path.endswith("_test"):
        raise RuntimeError("Refusing a non-local or non-test database")
    schema = "scanapp_test_" + uuid4().hex
    admin = psycopg.connect(url, autocommit=True, row_factory=dict_row)
    admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    def connect(_url):
        return psycopg.connect(url, options=f"-c search_path={schema}", row_factory=dict_row,
                               application_name=schema)

    try:
        with connect("") as conn:
            conn.execute("""CREATE TABLE portfolio_products (
                session_id text NOT NULL, sample_key text NOT NULL,
                opened_at timestamptz NOT NULL, synced_at timestamptz,
                PRIMARY KEY (session_id, sample_key))""")
        monkeypatch.setattr("app.routes.internal.connect_portfolio", connect)
        app = FastAPI()
        token = "local-integration-test-only-" + "x" * 32
        app.state.settings = Settings(_env_file=None, scanapp_service_token=token,
                                      portfolio_database_url=url)
        app.include_router(router, prefix="/api/v1")
        with TestClient(app, raise_server_exceptions=False) as client:
            yield SimpleNamespace(client=client, connect=connect, admin=admin, schema=schema,
                                  headers={"Authorization": f"Bearer {token}"})
    finally:
        admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        admin.close()


def send(service, owner="user:member-a", suffix="One", empty=False):
    products = [] if empty else [{
        "url": "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/" + suffix,
        "opened_at": "2026-10-18T12:00:00Z",
    }]
    return service.client.post("/api/v1/internal/portfolio/products",
        json={"owner_key": owner, "products": products}, headers=service.headers)


def test_real_postgres_owner_lock_and_idempotent_cleanup(pg_service):
    service = pg_service
    send(service, owner="user:member-b").raise_for_status()
    with service.connect("") as blocker:
        blocker.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("user:member-a",))
        with ThreadPoolExecutor(max_workers=1) as pool:
            response = pool.submit(send, service)
            waiting = False
            try:
                for _ in range(100):
                    waiting = bool(service.admin.execute(
                        "SELECT 1 FROM pg_stat_activity WHERE application_name=%s AND wait_event='advisory'",
                        (service.schema,),
                    ).fetchone())
                    if waiting or response.done():
                        break
                    time.sleep(0.02)
            finally:
                blocker.commit()
            assert waiting, "Member replacement did not take the per-owner transaction lock"
            response.result(timeout=10).raise_for_status()
    for _ in range(2):
        assert send(service, empty=True).json() == {"count": 0}
    with service.connect("") as conn:
        assert conn.execute("SELECT session_id FROM portfolio_products").fetchall() == [{"session_id": "user:member-b"}]


def test_real_postgres_insert_failure_preserves_previous_snapshot(pg_service):
    service = pg_service
    send(service).raise_for_status()
    with service.connect("") as conn:
        conn.execute("ALTER TABLE portfolio_products ADD CONSTRAINT reject_bad CHECK (sample_key NOT LIKE '%Bad')")
    assert send(service, suffix="Bad").status_code == 500
    with service.connect("") as conn:
        rows = conn.execute("SELECT sample_key FROM portfolio_products").fetchall()
        assert len(rows) == 1 and rows[0]["sample_key"].endswith("One")


def test_preprovisioned_schema_supports_a_runtime_role_without_create_or_auth_access(pg_service):
    from app.cardmarket_daily import replace_portfolio
    from app.portfolio_db import ensure_portfolio_schema
    from app.price_history import ensure_schema

    service = pg_service
    role = "scanapp_runtime_" + uuid4().hex
    service.admin.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(role)))
    try:
        with service.connect("") as conn:
            ensure_portfolio_schema(conn)
            ensure_schema(conn)
            conn.execute("CREATE TABLE private_auth_fixture (id text)")
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(service.schema), sql.Identifier(role)))
            conn.execute(sql.SQL("GRANT SELECT, INSERT, DELETE ON portfolio_products TO {}").format(sql.Identifier(role)))
            conn.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE ON price_guide_import_days, price_history_daily, price_sales_daily TO {}").format(sql.Identifier(role)))
        with service.connect("") as conn:
            conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
            ensure_portfolio_schema(conn)
            ensure_schema(conn)
            assert not conn.execute("SELECT has_table_privilege(current_user, 'private_auth_fixture', 'SELECT') AS allowed").fetchone()["allowed"]
            product = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Pikachu"
            assert replace_portfolio(conn, "user:restricted", [(product, "2026-10-18T12:00:00Z")], lock_owner=True) == 1
            assert replace_portfolio(conn, "user:restricted", [], lock_owner=True) == 0
    finally:
        service.admin.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
        service.admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_price_history_writes_with_real_psycopg_cursor(pg_service):
    from app import price_history

    with pg_service.connect('') as conn:
        assert not hasattr(conn, 'executemany')
        assert price_history.record_guide(conn, '2026-10-29', [
            {'id_product': 1, 'trend': 10, 'trend_holo': 20}]) == 1
        assert price_history.record_guide(conn, '2026-10-30', [
            {'id_product': 1, 'trend': 10, 'trend_holo': 20}]) == 0
        price_history.bind(conn)
        try:
            assert price_history.record_sales(
                'https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Pikachu',
                [{'label': 'Avg 29.10.2026', 'amount': 10}]) == 1
        finally:
            price_history.bind(None)
        assert conn.execute('SELECT count(*) AS n FROM price_history_daily').fetchone()['n'] == 1
        assert conn.execute('SELECT count(*) AS n FROM price_guide_import_days').fetchone()['n'] == 2
        assert conn.execute('SELECT count(*) AS n FROM price_sales_daily').fetchone()['n'] == 1
