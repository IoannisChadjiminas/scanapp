import importlib.util
import logging
from pathlib import Path
import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "api"))
spec = importlib.util.spec_from_file_location("scraper_service_logging_test", HERE / "main.py")
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


def test_scraper_logs_start_and_failure_without_credentials(monkeypatch, caplog):
    monkeypatch.setattr(service, "API_KEY", "test-secret")
    monkeypatch.setattr(service, "reap_stale_browsers", lambda age: None)
    monkeypatch.setattr(service, "open_session", lambda sid: SimpleNamespace(proxy="secret-proxy"))
    def fail(*args, **kwargs):
        raise RuntimeError("secret-proxy")
    monkeypatch.setattr(service, "run_attempt", fail)
    with caplog.at_level(logging.INFO, logger="scraper"), TestClient(service.app) as client:
        response = client.post("/scrape", headers={"Authorization": "Bearer test-secret"}, json={
            "url": "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Pikachu",
            "session_id": "attempt-one",
        })
    assert response.status_code == 500
    assert "scraper config" in caplog.text
    assert "scrape started session=attempt-one" in caplog.text
    assert "error=RuntimeError" in caplog.text
    assert "secret-proxy" not in caplog.text
    assert "test-secret" not in caplog.text
