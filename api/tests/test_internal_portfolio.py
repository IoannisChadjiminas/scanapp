from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.routes.internal import router

TOKEN = "test-service-token-" + "x" * 32
URL = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Pikachu"
ENDPOINT = "/api/v1/internal/portfolio/products"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def service(tmp_path, monkeypatch):
    path = tmp_path / "portfolio.sqlite"

    def connect(_url):
        conn = sqlite3.connect(path, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    conn = connect("")
    conn.execute("""CREATE TABLE portfolio_products (
        session_id TEXT NOT NULL, sample_key TEXT NOT NULL, opened_at TEXT NOT NULL,
        synced_at TEXT, PRIMARY KEY (session_id, sample_key))""")
    conn.commit()
    conn.close()
    monkeypatch.setattr("app.routes.internal.connect_portfolio", connect)
    app = FastAPI()
    app.state.settings = Settings(
        _env_file=None, scanapp_service_token=TOKEN,
        portfolio_database_url="postgresql://test.invalid/unused",
    )
    app.include_router(router, prefix="/api/v1")
    with TestClient(app, raise_server_exceptions=False) as client:
        yield SimpleNamespace(client=client, settings=app.state.settings, connect=connect)


def snapshot(owner="user:member-a", urls=(URL,)):
    return {"owner_key": owner, "products": [
        {"url": url, "opened_at": "2026-10-18T12:00:00Z"} for url in urls
    ]}


def rows(service):
    with service.connect("") as conn:
        return [tuple(row) for row in conn.execute(
            "SELECT session_id, sample_key FROM portfolio_products ORDER BY session_id, sample_key"
        )]


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"X-Review-Token": TOKEN}])
def test_service_requires_dedicated_bearer_token(service, headers):
    assert service.client.post(ENDPOINT, json=snapshot(), headers=headers).status_code == 401
    assert rows(service) == []


def test_disabled_weak_or_missing_storage_fails_closed(service):
    from pydantic import SecretStr

    service.settings.scanapp_service_token = SecretStr("")
    assert service.client.post(ENDPOINT, json=snapshot(), headers=AUTH).status_code == 404
    service.settings.scanapp_service_token = SecretStr("short")
    assert service.client.post(ENDPOINT, json=snapshot(), headers=AUTH).status_code == 503
    service.settings.scanapp_service_token = SecretStr(TOKEN)
    service.settings.portfolio_database_url = SecretStr("")
    assert service.client.post(ENDPOINT, json=snapshot(), headers=AUTH).status_code == 503


def test_idempotent_snapshot_and_cleanup_preserve_other_owners_and_browser_sessions(service):
    with service.connect("") as conn:
        conn.execute("INSERT INTO portfolio_products VALUES ('browser-session', ?, '2026-10-18', NULL)", (URL,))
    for _ in range(2):
        response = service.client.post(ENDPOINT, json=snapshot(urls=(URL, URL)), headers=AUTH)
        assert response.json() == {"count": 1}
        assert "set-cookie" not in response.headers
    service.client.post(ENDPOINT, json=snapshot("user:member-b"), headers=AUTH).raise_for_status()
    for _ in range(2):
        assert service.client.post(ENDPOINT, json=snapshot(urls=()), headers=AUTH).json() == {"count": 0}
    assert rows(service) == [("browser-session", URL), ("user:member-b", URL)]


@pytest.mark.parametrize("change", [
    {"owner_key": "browser-session"},
    {"products": [{"url": "https://example.com/Pokemon/Products/Singles/Base-Set/Pikachu", "opened_at": "2026-10-18T12:00:00Z"}]},
    {"products": [{"url": URL, "opened_at": "2026-10-18T12:00:00"}]},
    {"products": [{"url": URL, "opened_at": "invalid"}]},
    {"unexpected": True},
])
def test_invalid_payload_does_not_replace_existing_portfolio(service, change):
    service.client.post(ENDPOINT, json=snapshot(), headers=AUTH).raise_for_status()
    response = service.client.post(ENDPOINT, json={**snapshot(), **change}, headers=AUTH)
    assert response.status_code == 422
    assert rows(service) == [("user:member-a", URL)]


def test_failed_insert_rolls_back_the_delete(service):
    service.client.post(ENDPOINT, json=snapshot(), headers=AUTH).raise_for_status()
    with service.connect("") as conn:
        conn.execute("""CREATE TRIGGER reject_insert BEFORE INSERT ON portfolio_products
                        BEGIN SELECT RAISE(ABORT, 'test rejection'); END""")
    response = service.client.post(ENDPOINT, json=snapshot(urls=(URL + "-Other",)), headers=AUTH)
    assert response.status_code == 500
    assert rows(service) == [("user:member-a", URL)]


def test_concurrent_first_snapshots_cannot_merge(service):
    def send(suffix):
        return service.client.post(ENDPOINT, json=snapshot(urls=(URL + suffix,)), headers=AUTH)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(send, ("-One", "-Two")))
    assert all(response.status_code == 200 for response in responses)
    assert len(rows(service)) == 1
