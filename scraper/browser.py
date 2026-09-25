"""One Cardmarket attempt on one sticky IP.

A challenge is solved without changing IP. The attempt stops only on offers,
a confirmed empty page, the wrong product, a rate limit, or the deadline.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from typing import Protocol

BLOCKED = [
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.webp",
    "*.svg",
    "*.mp4",
    "*.webm",
    "*.woff",
    "*.woff2",
    "*google-analytics*",
    "*googletagmanager*",
    "*facebook.com*",
    "*doubleclick*",
]

PROBE_JS = r"""
(() => {
  const title = document.title || "";
  const href = location.href || "";
  const text = String((document.body && document.body.innerText) || "").slice(0, 1500);
  const blob = (title + " " + href + " " + text).toLowerCase();
  if (/error 1015|you are being rate limited|access denied/.test(blob)) return "rate_limited";
  const challenge = Boolean(document.querySelector("#challenge-form, .cf-turnstile, iframe[src*='challenges.cloudflare.com']"))
    || /just a moment|verify you are human|checking your browser|attention required/.test(blob);
  if (challenge) return "challenge";
  const rows = document.querySelectorAll(".article-row, tr.article");
  if (rows.length) return "offers";
  if (document.querySelector("[data-test-empty-articles], .noArticles, .no-articles")
      || /there are currently no articles|no articles available/.test(blob)) return "empty";
  if (href && !/\/products\/singles\//i.test(href)) return "wrong_product";
  return "pending";
})()
"""

ATTEMPT_SECONDS = float(os.environ.get("SCRAPER_ATTEMPT_SECONDS", "25"))
CLICK_EVERY_S = float(os.environ.get("SCRAPER_CLICK_EVERY_S", "4"))
NET_LOG = os.environ.get("SCRAPER_NET_LOG", "true").strip().lower() not in {"0", "false", "no"}
# DataImpulse keeps one sessid for about 30 minutes. The clearance cookie is
# bound to that exit, so the window lives for the same stretch.
BROWSER_LIFETIME_S = float(os.environ.get("SCRAPER_BROWSER_LIFETIME_S", "1800"))
_held: ChromeSession | None = None
_held_at = 0.0
_held_lock = threading.Lock()
TERMINAL = {"offers", "empty", "wrong_product", "rate_limited"}


class PageSession(Protocol):
    proxy: str | None

    def open(self, url: str) -> None: ...
    def block_extra_resources(self) -> None: ...
    def probe(self) -> str: ...
    def solve_captcha(self) -> None: ...
    def html(self) -> str: ...
    def stop(self) -> None: ...
    def quit(self) -> None: ...


def held_pids() -> list[int]:
    with _held_lock:
        if _held is None or _held._sb is None:
            return []
        return _process_tree(_held._sb)


def reap_stale_browsers(max_age: float, keep: list[int] | None = None) -> None:
    """Kill Chrome processes this service started and then left behind."""
    try:
        import psutil
    except ImportError:
        return
    spared = set(keep or [])
    now = time.time()
    try:
        children = psutil.Process().children(recursive=True)
    except Exception:
        return
    for child in children:
        if child.pid in spared or "chrom" not in child.name().lower():
            continue
        try:
            if now - child.create_time() > max_age:
                child.kill()
        except Exception:
            continue


def _process_tree(sb: object) -> list[int]:
    """Collect Chrome and ChromeDriver: UC launches them as separate processes."""
    driver = getattr(sb, "driver", None)
    service = getattr(driver, "service", None)
    process = getattr(service, "process", None)
    roots = [
        pid for pid in (getattr(driver, "browser_pid", None), getattr(process, "pid", None))
        if isinstance(pid, int) and pid > 0
    ]
    try:
        import psutil
    except ImportError:
        return roots
    pids = []
    for pid in roots:
        try:
            parent = psutil.Process(pid)
            pids.extend(child.pid for child in reversed(parent.children(recursive=True)))
        except Exception:
            pass
        pids.append(pid)
    return list(dict.fromkeys(pids))


def _kill_pids(pids: list[int]) -> None:
    try:
        import psutil
    except ImportError:
        return
    for pid in pids:
        try:
            psutil.Process(pid).kill()
        except Exception:
            continue


class _AttemptDeadline(Exception):
    pass


def _before_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise _AttemptDeadline()


def _kill_chrome_children() -> None:
    """Kill Chrome this process started when the driver handle is not ready yet."""
    try:
        import psutil

        children = psutil.Process().children(recursive=True)
    except Exception:
        return
    for child in children:
        try:
            if "chrom" not in child.name().lower():
                continue
            child.kill()
        except Exception:
            continue


def _abort_attempt(session: object) -> None:
    abort = getattr(session, "abort", None)
    if callable(abort):
        try:
            abort()
        except Exception:
            return
        return
    sb = getattr(session, "_sb", None)
    if sb is not None:
        _kill_pids(_process_tree(sb))


def _watch_attempt(session: object, deadline: float, stop: threading.Event) -> None:
    """Kill the attempt's browser if any call is still running at the deadline."""
    remaining = deadline - time.monotonic()
    if stop.wait(max(0.0, remaining)):
        return
    while not stop.is_set():
        _abort_attempt(session)
        if stop.wait(1.0):
            return


def chrome_launch_options(proxy: str | None, net_log: str | None = None) -> dict:
    """Headed UC Chrome. ``log_cdp`` turns on the performance log used for bytes."""
    from proxy import seleniumbase_proxy

    args = ["--no-sandbox", "--disable-dev-shm-usage"]
    if net_log:
        # Default capture mode leaves credentials and cookies out of the file.
        args += [f"--log-net-log={net_log}", "--net-log-capture-mode=Default"]
    options = {
        "uc": True,
        "xvfb": True,
        "xvfb_metrics": "1920,1080",
        "window_size": "1920,1080",
        "headed": True,
        "locale": "en",
        "log_cdp": True,
        "chromium_arg": ",".join(args),
    }
    formatted = seleniumbase_proxy(proxy)
    if formatted:
        options["proxy"] = formatted
    return options


def _sample_page(session: object, stop: threading.Event) -> None:
    """Keep the latest title and screenshot while the page load is blocked."""
    while not stop.wait(2.0):
        capture = getattr(session, "capture_page", None)
        if not callable(capture):
            return
        try:
            capture()
        except Exception:
            continue


def run_attempt(session: PageSession, url: str, *, parse_html) -> dict:
    """Drive one page. `parse_html(url, html)` returns the scanapp parser dict.

    Navigation, captcha handling, and cleanup all share one deadline. A stalled
    call is aborted by the watchdog so the browser slot cannot outlive it.
    """
    started = time.monotonic()
    deadline = started + ATTEMPT_SECONDS
    outcome = "timeout"
    page = ""
    failed = False
    stop = threading.Event()
    watcher = threading.Thread(
        target=_watch_attempt,
        args=(session, deadline, stop),
        name="cardmarket-attempt-watch",
        daemon=True,
    )
    watcher.start()
    sampler = threading.Thread(
        target=_sample_page, args=(session, stop), name="cardmarket-page-sample", daemon=True,
    )
    sampler.start()
    try:
        try:
            _before_deadline(deadline)
            session.open(url)
            _before_deadline(deadline)
            session.block_extra_resources()
            next_click = 0.0
            while time.monotonic() < deadline:
                _before_deadline(deadline)
                outcome = session.probe() or "pending"
                if outcome in TERMINAL:
                    break
                if outcome == "challenge" and time.monotonic() >= next_click:
                    _before_deadline(deadline)
                    session.solve_captcha()
                    next_click = time.monotonic() + CLICK_EVERY_S
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                wait = min(0.25, remaining)
                if outcome == "challenge":
                    wait = min(wait, max(0.0, next_click - time.monotonic()))
                time.sleep(wait)
            if time.monotonic() < deadline:
                if outcome in {"offers", "empty", "wrong_product"}:
                    page = session.html() or ""
                session.stop()
        except _AttemptDeadline:
            pass
        except Exception:
            failed = True
            raise
    finally:
        try:
            keep = not failed and getattr(session, "alive", lambda: False)()
            close = getattr(session, "finish", None) if keep else None
            (close or session.quit)()
        except Exception:
            pass
        stop.set()
        watcher.join(timeout=2)
        sampler.join(timeout=2)
    if outcome not in TERMINAL:
        outcome = "challenge_unsolved" if outcome == "challenge" else "timeout"
    parsed = parse_html(url, page) if page else {}
    if outcome == "offers" and not parsed.get("rows"):
        outcome = "timeout"
    if parsed.get("blocked") and outcome not in {"rate_limited", "wrong_product"}:
        outcome = "challenge_unsolved"
    rows = list(parsed.get("rows") or []) if outcome == "offers" else []
    header = parsed.get("header") if isinstance(parsed.get("header"), dict) else {}
    return {
        "outcome": outcome if outcome != "challenge" else "challenge_unsolved",
        "url": str(parsed.get("url") or url),
        "title": str(parsed.get("title") or ""),
        "rows": rows,
        "header": header,
        "bytes": (
            int(getattr(session, "bytes", 0) or 0)
            if getattr(session, "bytes_measured", True)
            else None
        ),
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


class ChromeSession:
    """Headed undetected Chrome under Xvfb. Imported only when a real attempt runs."""

    def __init__(self, proxy: str | None, net_log: bool = NET_LOG) -> None:
        self.proxy = proxy
        self.bytes = 0
        self.bytes_measured = False
        self.net_summary: dict | None = None
        self.last_title = ""
        self.last_url = ""
        self.last_screenshot = b""
        self.stage = "created"
        self.watchdog_aborted = False
        self.reused = False
        self._sb = None
        self._context = None
        self._net_dir = tempfile.mkdtemp(prefix="cm-netlog-") if net_log else None

    @property
    def _net_path(self) -> str | None:
        return os.path.join(self._net_dir, "net.json") if self._net_dir else None

    def capture_page(self) -> None:
        import psutil

        from page_shot import capture_screenshot, chrome_pages, debug_port, page_target

        port = None
        try:
            children = psutil.Process().children(recursive=True)
        except Exception:
            return
        for child in children:
            try:
                port = debug_port(child.cmdline())
            except Exception:
                continue
            if port:
                break
        if not port:
            return
        try:
            target = page_target(chrome_pages(port))
        except Exception:
            return
        if not target:
            return
        self.last_title = " ".join(str(target.get("title") or "").split())[:120]
        self.last_url = str(target.get("url") or "")[:500]
        socket_url = str(target.get("webSocketDebuggerUrl") or "")
        if socket_url:
            try:
                self.last_screenshot = capture_screenshot(socket_url)
            except Exception:
                return

    def alive(self) -> bool:
        return (
            self._sb is not None
            and not self.watchdog_aborted
            and getattr(self._sb, "cdp", None) is not None
        )

    def open(self, url: str) -> None:
        self.bytes = 0
        self.bytes_measured = False
        self.last_title = ""
        self.last_url = ""
        self.last_screenshot = b""
        self.watchdog_aborted = False
        if self._sb is not None:
            self.reused = True
            self.stage = "cdp_navigation"
            self._sb.cdp.get(url)
            return
        from seleniumbase import SB

        self.reused = False
        self.stage = "browser_start"
        self._context = SB(**chrome_launch_options(self.proxy, self._net_path))
        self._sb = self._context.__enter__()
        self.stage = "cdp_navigation"
        self._sb.activate_cdp_mode(url)

    def block_extra_resources(self) -> None:
        import mycdp.network as network

        self.stage = "resource_blocking"
        # BaseCase.execute_cdp_cmd reconnects WebDriver. Keep these commands on
        # the same CDP tab and event loop used by navigation and page probing.
        cdp = self._sb.cdp
        tab = cdp.get_active_tab()
        loop = cdp.get_event_loop()
        try:
            loop.run_until_complete(tab.send(network.enable()))
            loop.run_until_complete(tab.send(network.set_blocked_urls(urls=BLOCKED)))
        except Exception:
            return

    def probe(self) -> str:
        self.stage = "page_probe"
        # Keep page reads on the existing CDP connection.
        value = self._sb.cdp.evaluate(PROBE_JS)
        return str(value or "pending")

    def solve_captcha(self) -> None:
        self.stage = "challenge_interaction"
        click = getattr(self._sb, "uc_gui_click_captcha", None)
        if callable(click):
            click()

    def html(self) -> str:
        self.stage = "read_html"
        self._account_bytes()
        return str(self._sb.cdp.get_page_source(include_shadow_dom=False) or "")

    def stop(self) -> None:
        try:
            self._sb.cdp.evaluate("window.stop()")
        except Exception:
            return

    def _account_bytes(self) -> None:
        """Sum CDP encodedDataLength when Chrome performance logs are enabled."""
        if getattr(self._sb, "cdp", None) is not None:
            return
        driver = getattr(self._sb, "driver", None)
        if driver is None:
            return
        try:
            entries = driver.get_log("performance")
        except Exception:
            return
        self.bytes_measured = True
        for entry in entries:
            try:
                message = json.loads(entry.get("message") or "{}").get("message") or {}
            except (TypeError, ValueError):
                continue
            if message.get("method") != "Network.loadingFinished":
                continue
            length = (message.get("params") or {}).get("encodedDataLength")
            if isinstance(length, (int, float)) and length > 0:
                self.bytes += int(length)

    def abort(self) -> None:
        """Unblock a stalled driver call by killing this attempt's Chrome."""
        self.watchdog_aborted = True
        pids = _process_tree(self._sb) if self._sb is not None else []
        if pids:
            _kill_pids(pids)
            return
        _kill_chrome_children()

    def finish(self) -> None:
        """Leave the window open. A dead browser is closed instead."""
        self._account_bytes()
        if not self.alive():
            self.quit()
            return
        self._read_net_log(keep=True)

    def quit(self) -> None:
        self._account_bytes()
        pids = _process_tree(self._sb) if self._sb is not None else []
        context = self._context
        try:
            if context is not None:
                context.__exit__(None, None, None)
        except Exception:
            _kill_pids(pids)
        finally:
            # Keep the handle available to the watchdog until shutdown finishes.
            self._context = None
            self._sb = None
            self._read_net_log()

    def _read_net_log(self, keep: bool = False) -> None:
        if not self._net_dir:
            return
        from netlog import read_net_log

        try:
            self.net_summary = read_net_log(self._net_path)
        finally:
            if not keep:
                shutil.rmtree(self._net_dir, ignore_errors=True)
                self._net_dir = None


def acquire_browser(proxy: str | None) -> ChromeSession:
    """The one Chrome window. A later card is loaded in its open tab."""
    global _held, _held_at
    with _held_lock:
        expired = _held is not None and time.time() - _held_at >= BROWSER_LIFETIME_S
        if _held is not None and (expired or not _held.alive()):
            _held.quit()
            _held = None
        if _held is None:
            _held = ChromeSession(proxy)
            _held.reused = False
            _held_at = time.time()
        else:
            _held.reused = True
        return _held
