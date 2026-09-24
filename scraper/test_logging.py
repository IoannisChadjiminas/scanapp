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

URL = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Pikachu"


def test_scraper_logs_start_and_failure_without_credentials(monkeypatch, caplog):
    monkeypatch.setattr(service, "API_KEY", "test-secret")
    monkeypatch.setattr(service, "reap_stale_browsers", lambda age: None)
    monkeypatch.setattr(service, "open_session", lambda sid: SimpleNamespace(
        proxy="secret-proxy",
        stage="cdp_navigation",
        watchdog_aborted=True,
        net_summary={"www.cardmarket.com": {"tunnel": {"no reply": 2}}},
    ))
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
    assert "module=builtins stage=cdp_navigation watchdog_aborted=True elapsed_ms=" in caplog.text
    assert "test_logging.py:" in caplog.text
    assert ":fail" in caplog.text
    assert (
        'chrome net session=attempt-one {"www.cardmarket.com": {"tunnel": {"no reply": 2}}}'
    ) in caplog.text
    assert "secret-proxy" not in caplog.text
    assert "test-secret" not in caplog.text


def test_chrome_page_logs_the_last_title_and_screenshot(caplog):
    path = Path("/tmp/cardmarket-abcd1234.png")
    path.unlink(missing_ok=True)
    session = SimpleNamespace(
        last_title="Just a moment...",
        last_url="https://www.cardmarket.com/en",
        last_screenshot=b"\x89PNG\r\n",
    )
    with caplog.at_level(logging.INFO, logger="scraper"):
        service.log_chrome_page("abcd1234-rest", session)
    assert "chrome page session=abcd1234-rest title='Just a moment...' url=https://www.cardmarket.com/en" in caplog.text
    assert "screenshot_bytes=6 path=/tmp/cardmarket-abcd1234.png" in caplog.text
    assert path.read_bytes() == b"\x89PNG\r\n"
    path.unlink()


def test_proxy_exit_failure_logs_the_error_type_only(monkeypatch, caplog):
    def stalled(proxy):
        raise TimeoutError("http://login:secret-pass@gw.dataimpulse.com:823")
    monkeypatch.setattr(service, "proxy_exit", stalled)
    with caplog.at_level(logging.INFO, logger="scraper"):
        service.log_proxy_exit("attempt-two", "http://login:secret-pass@gw.dataimpulse.com:823")
    assert "proxy exit failed session=attempt-two error=TimeoutError" in caplog.text
    assert "secret-pass" not in caplog.text


def test_cardmarket_direct_reports_a_cloudflare_challenge(monkeypatch):
    import io
    import urllib.error
    from email.message import Message

    import proxy

    headers = Message()
    headers["server"] = "cloudflare"
    headers["cf-mitigated"] = "challenge"
    seen = {}

    class Opener:
        def open(self, request, timeout):
            seen["url"], seen["agent"] = request.full_url, request.get_header("User-agent")
            raise urllib.error.HTTPError(
                request.full_url, 403, "Forbidden", headers,
                io.BytesIO(b"<html><head><title>Just a moment...</title></head></html>"),
            )

    monkeypatch.setattr(proxy.urllib.request, "build_opener", lambda handler: Opener())
    page = proxy.proxy_direct("http://login:secret@gw.dataimpulse.com:823", URL)
    assert page == {
        "status": 403, "bytes": 57, "server": "cloudflare",
        "cf_mitigated": "challenge", "title": "Just a moment...",
    }
    assert seen["url"] == URL
    assert "Chrome/" in seen["agent"]


def test_cardmarket_direct_logs_only_when_enabled(monkeypatch, caplog):
    calls = []
    monkeypatch.setattr(service, "proxy_direct", lambda proxy, url: calls.append(url) or {
        "status": 403, "bytes": 57, "server": "cloudflare",
        "cf_mitigated": "challenge", "title": "Just a moment...",
    })
    monkeypatch.setattr(service, "DIRECT_PROBE", False)
    service.log_cardmarket_direct("attempt-three", "http://login:secret@gw", URL)
    assert calls == []

    monkeypatch.setattr(service, "DIRECT_PROBE", True)
    with caplog.at_level(logging.INFO, logger="scraper"):
        service.log_cardmarket_direct("attempt-three", "http://login:secret@gw", URL)
    assert calls == [URL]
    assert (
        "cardmarket direct session=attempt-three status=403 server=cloudflare "
        "cf_mitigated=challenge bytes=57 title='Just a moment...'"
    ) in caplog.text

    def stalled(proxy, url):
        raise TimeoutError("http://login:secret-pass@gw.dataimpulse.com:823")
    monkeypatch.setattr(service, "proxy_direct", stalled)
    with caplog.at_level(logging.INFO, logger="scraper"):
        service.log_cardmarket_direct("attempt-four", "http://login:secret-pass@gw", URL)
    assert "cardmarket direct failed session=attempt-four error=TimeoutError" in caplog.text
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
