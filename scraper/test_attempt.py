import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from browser import ChromeSession, run_attempt
from allow import cardmarket_product

URL = (
    "https://www.cardmarket.com/en/Pokemon/Products/Singles/"
    "Tag-Bolt/Gengar-Mimikyu-GX-V2-sm9102?language=1"
)


class Scripted:
    def __init__(self, probes, html="<html></html>", proxy="http://sticky"):
        self.probes = list(probes)
        self.page = html
        self.proxy = proxy
        self.bytes = 1200
        self.opened = None
        self.captcha = 0
        self.stopped = False
        self.quit_called = False

    def open(self, url):
        self.opened = url

    def block_extra_resources(self):
        return None

    def probe(self):
        if not self.probes:
            return "pending"
        return self.probes.pop(0)

    def solve_captcha(self):
        self.captcha += 1

    def html(self):
        return self.page

    def stop(self):
        self.stopped = True

    def quit(self):
        self.quit_called = True


def _parse(url, html):
    if "article-row" in html:
        return {
            "url": url,
            "title": "Gengar",
            "rows": [{"price": "2,50 €", "condition": "NM", "language": "English", "variant": ""}],
            "blocked": False,
            "empty": False,
        }
    if "no articles" in html:
        return {"url": url, "title": "Gengar", "rows": [], "blocked": False, "empty": True}
    if "challenge" in html:
        return {"url": url, "title": "Just a moment", "rows": [], "blocked": True, "empty": False}
    return {"url": url, "title": "", "rows": [], "blocked": False, "empty": False}


def test_allowlist_rejects_other_sites():
    assert cardmarket_product(URL)
    assert not cardmarket_product("https://example.com/en/Pokemon/Products/Singles/a/b")
    assert not cardmarket_product("https://www.cardmarket.com/en/Pokemon/Products/Boosters/Base")


def test_challenge_stays_on_the_same_proxy_then_reads_offers():
    session = Scripted(
        ["challenge", "offers"],
        html='<div class="article-row">2,50 €</div>',
        proxy="http://session-a",
    )
    result = run_attempt(session, URL, parse_html=_parse)
    assert session.captcha == 1
    assert session.proxy == "http://session-a"
    assert result["outcome"] == "offers"
    assert result["rows"][0]["price"] == "2,50 €"
    assert session.quit_called


def test_challenge_alone_does_not_finish_the_attempt(monkeypatch):
    monkeypatch.setattr("browser.ATTEMPT_SECONDS", 0.01)
    session = Scripted(["challenge", "challenge"], html="<html>challenge</html>")
    result = run_attempt(session, URL, parse_html=_parse)
    assert result["outcome"] == "challenge_unsolved"
    assert result["rows"] == []


def test_unmeasured_bytes_stay_unknown():
    session = Scripted(["empty"], html="<html>no articles</html>")
    session.bytes = 0
    session.bytes_measured = False
    result = run_attempt(session, URL, parse_html=_parse)
    assert result["bytes"] is None


def test_configured_proxy_is_passed_to_chrome(monkeypatch):
    monkeypatch.setenv("PROXY_HOST", "gw.dataimpulse.com:823")
    monkeypatch.setenv("PROXY_USER", "login")
    monkeypatch.setenv("PROXY_PASS", "secret")
    monkeypatch.setenv("PROXY_COUNTRY", "de")
    from browser import chrome_launch_options
    from proxy import proxy_server

    options = chrome_launch_options(proxy_server("abc"))
    assert options["log_cdp"] is True
    assert options["xvfb_metrics"] == "1920,1080"
    assert options["window_size"] == "1920,1080"
    assert options["proxy"] == "login__cr.de;sessid.abc:secret@gw.dataimpulse.com:823"
    assert "proxy" not in chrome_launch_options(None)
    assert options["chromium_arg"] == "--no-sandbox,--disable-dev-shm-usage"


def test_net_log_is_written_to_a_private_file_and_removed(tmp_path):
    from browser import chrome_launch_options

    args = chrome_launch_options(None, "/tmp/cm-netlog-x/net.json")["chromium_arg"].split(",")
    assert "--log-net-log=/tmp/cm-netlog-x/net.json" in args
    assert "--net-log-capture-mode=Default" in args

    session = ChromeSession(None, net_log=True)
    path = Path(session._net_path)
    path.write_text('{"constants":{"logEventTypes":{},"netError":{}},\n"events": [\n')
    session.quit()
    assert session.net_summary == {}
    assert not path.parent.exists()
    assert ChromeSession(None, net_log=False)._net_path is None


def test_deadline_aborts_a_stalled_call(monkeypatch):
    monkeypatch.setattr("browser.ATTEMPT_SECONDS", 0.2)

    class Hung(Scripted):
        def __init__(self):
            super().__init__(["offers"])
            self.release = threading.Event()
            self.aborted = False

        def open(self, url):
            self.opened = url
            self.release.wait(timeout=5)

        def abort(self):
            self.aborted = True
            self.release.set()

    session = Hung()
    started = time.monotonic()
    result = run_attempt(session, URL, parse_html=_parse)
    assert session.aborted
    assert session.quit_called
    assert result["outcome"] == "timeout"
    assert time.monotonic() - started < 2


def test_deadline_covers_cleanup(monkeypatch):
    monkeypatch.setattr("browser.ATTEMPT_SECONDS", 0.2)

    class HungQuit(Scripted):
        def __init__(self):
            super().__init__(["offers"], html='<div class="article-row">2,50 €</div>')
            self.release = threading.Event()
            self.aborted = False

        def quit(self):
            self.quit_called = True
            self.release.wait(timeout=5)

        def abort(self):
            self.aborted = True
            self.release.set()

    session = HungQuit()
    started = time.monotonic()
    result = run_attempt(session, URL, parse_html=_parse)
    assert result["outcome"] == "offers"
    assert session.aborted
    assert time.monotonic() - started < 2


def test_empty_and_wrong_product_stop_without_a_new_ip():
    empty = Scripted(["empty"], html="<html>no articles</html>", proxy="http://one")
    assert run_attempt(empty, URL, parse_html=_parse)["outcome"] == "empty"
    assert empty.captcha == 0
    wrong = Scripted(["wrong_product"], proxy="http://one")
    assert run_attempt(wrong, URL, parse_html=_parse)["outcome"] == "wrong_product"


@pytest.fixture
def chrome_processes(monkeypatch):
    """UC Chrome and ChromeDriver are siblings, each with their own children."""
    killed = set()
    on_kill = {}
    children = {101: [102], 102: [], 201: [202], 202: [], 301: []}

    class Process:
        def __init__(self, pid):
            if pid not in children:
                raise ProcessLookupError(pid)
            self.pid = pid

        def children(self, recursive=False):
            return [Process(pid) for pid in children[self.pid]]

        def kill(self):
            killed.add(self.pid)
            if callback := on_kill.get(self.pid):
                callback()

    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace(Process=Process))
    driver = SimpleNamespace(
        service=SimpleNamespace(process=SimpleNamespace(pid=101)),
        browser_pid=201,
    )
    return SimpleNamespace(driver=driver, killed=killed, children=children, on_kill=on_kill)


@pytest.mark.parametrize("driver_state", ["running", "exited", "missing"])
def test_abort_kills_separate_chrome_tree(chrome_processes, driver_state):
    processes = chrome_processes
    if driver_state == "exited":
        del processes.children[101]
    elif driver_state == "missing":
        processes.driver.service.process = None
    session = ChromeSession(None)
    session._sb = SimpleNamespace(driver=processes.driver)

    session.abort()

    assert {201, 202} <= processes.killed
    if driver_state == "running":
        assert {101, 102} <= processes.killed
    assert 301 not in processes.killed


def test_watchdog_can_target_chrome_during_context_cleanup(monkeypatch, chrome_processes):
    monkeypatch.setattr("browser.ATTEMPT_SECONDS", 0.2)
    release = threading.Event()
    chrome_processes.on_kill[201] = release.set
    session = ChromeSession(None)
    session._sb = SimpleNamespace(driver=chrome_processes.driver)

    class Context:
        def __exit__(self, *args):
            assert release.wait(timeout=3), "watchdog did not terminate Chrome"

    session._context = Context()
    monkeypatch.setattr(session, "open", lambda url: None)
    monkeypatch.setattr(session, "block_extra_resources", lambda: None)
    monkeypatch.setattr(session, "probe", lambda: "empty")
    monkeypatch.setattr(session, "html", lambda: "no articles")
    monkeypatch.setattr(session, "stop", lambda: None)
    started = time.monotonic()

    result = run_attempt(session, URL, parse_html=_parse)

    assert result["outcome"] == "empty"
    assert {201, 202} <= chrome_processes.killed
    assert 301 not in chrome_processes.killed
    assert session._sb is None
    assert session._context is None
    assert time.monotonic() - started < 2
