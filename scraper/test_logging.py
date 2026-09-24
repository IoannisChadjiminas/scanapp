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
    monkeypatch.setattr(
        service, "proxy_exit",
        lambda proxy: {"ip": "203.0.113.7", "country": "DE", "org": "AS3320 Deutsche Telekom AG"},
    )
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
    assert "proxy exit session=attempt-one ip=203.0.113.7 country=DE org=AS3320 Deutsche Telekom AG" in caplog.text
    assert "error=RuntimeError" in caplog.text
    assert "secret-proxy" not in caplog.text
    assert "test-secret" not in caplog.text


def test_proxy_exit_failure_logs_the_error_type_only(monkeypatch, caplog):
    def stalled(proxy):
        raise TimeoutError("http://login:secret-pass@gw.dataimpulse.com:823")
    monkeypatch.setattr(service, "proxy_exit", stalled)
    with caplog.at_level(logging.INFO, logger="scraper"):
        service.log_proxy_exit("attempt-two", "http://login:secret-pass@gw.dataimpulse.com:823")
    assert "proxy exit failed session=attempt-two error=TimeoutError" in caplog.text
    assert "secret-pass" not in caplog.text


def test_proxy_exit_uses_the_sticky_login_for_https(monkeypatch):
    import io
    import proxy

    seen = {}

    class Opener:
        def open(self, url, timeout):
            seen["url"], seen["timeout"] = url, timeout
            return io.BytesIO(b'{"ip": "203.0.113.7", "country": "DE", "org": "AS3320 Deutsche Telekom AG"}')

    def build_opener(handler):
        seen["proxies"] = handler.proxies
        return Opener()

    monkeypatch.setattr(proxy.urllib.request, "build_opener", build_opener)
    sticky = "http://login__cr.de%3Bsessid.abc:secret@gw.dataimpulse.com:823"
    assert proxy.proxy_exit(sticky) == {
        "ip": "203.0.113.7", "country": "DE", "org": "AS3320 Deutsche Telekom AG",
    }
    assert seen["proxies"] == {"http": sticky, "https": sticky}
    assert seen["url"] == "https://ipinfo.io/json"
    assert seen["timeout"] == 8.0
