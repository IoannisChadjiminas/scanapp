"""One Cardmarket attempt on one sticky IP.

A challenge is solved without changing IP. The attempt stops only on offers,
a confirmed empty page, the wrong product, a rate limit, or the deadline.
"""

from __future__ import annotations

import json
import os
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


def reap_stale_browsers(max_age: float) -> None:
    """Kill Chrome processes this service started and then left behind."""
    try:
        import psutil
    except ImportError:
        return
    now = time.time()
    try:
        children = psutil.Process().children(recursive=True)
    except Exception:
        return
    for child in children:
        if "chrom" not in child.name().lower():
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


def chrome_launch_options(proxy: str | None) -> dict:
    """Headed UC Chrome. ``log_cdp`` turns on the performance log used for bytes."""
    from proxy import seleniumbase_proxy

    options = {
        "uc": True,
        "xvfb": True,
        "headed": True,
        "locale": "en",
        "log_cdp": True,
        "chromium_arg": "--no-sandbox,--disable-dev-shm-usage",
    }
    formatted = seleniumbase_proxy(proxy)
    if formatted:
        options["proxy"] = formatted
    return options


def run_attempt(session: PageSession, url: str, *, parse_html) -> dict:
    """Drive one page. `parse_html(url, html)` returns the scanapp parser dict.

    Navigation, captcha handling, and cleanup all share one deadline. A stalled
    call is aborted by the watchdog so the browser slot cannot outlive it.
    """
    started = time.monotonic()
    deadline = started + ATTEMPT_SECONDS
    outcome = "timeout"
    page = ""
    stop = threading.Event()
    watcher = threading.Thread(
        target=_watch_attempt,
        args=(session, deadline, stop),
        name="cardmarket-attempt-watch",
        daemon=True,
    )
    watcher.start()
    try:
        try:
            _before_deadline(deadline)
            session.open(url)
            _before_deadline(deadline)
            session.block_extra_resources()
            solved = False
            while time.monotonic() < deadline:
                _before_deadline(deadline)
                outcome = session.probe() or "pending"
                if outcome in TERMINAL:
                    break
                if outcome == "challenge" and not solved:
                    _before_deadline(deadline)
                    session.solve_captcha()
                    solved = True
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(0.25, remaining))
            if time.monotonic() < deadline:
                if outcome in {"offers", "empty", "wrong_product"}:
                    page = session.html() or ""
                session.stop()
        except _AttemptDeadline:
            pass
    finally:
        try:
            session.quit()
        except Exception:
            pass
        stop.set()
        watcher.join(timeout=2)
    if outcome not in TERMINAL:
        outcome = "challenge_unsolved" if outcome == "challenge" else "timeout"
    parsed = parse_html(url, page) if page else {}
    if outcome == "offers" and not parsed.get("rows"):
        outcome = "timeout"
    if parsed.get("blocked") and outcome not in {"rate_limited", "wrong_product"}:
        outcome = "challenge_unsolved"
    rows = list(parsed.get("rows") or []) if outcome == "offers" else []
    return {
        "outcome": outcome if outcome != "challenge" else "challenge_unsolved",
        "url": str(parsed.get("url") or url),
        "title": str(parsed.get("title") or ""),
        "rows": rows,
        "bytes": (
            int(getattr(session, "bytes", 0) or 0)
            if getattr(session, "bytes_measured", True)
            else None
        ),
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


class ChromeSession:
    """Headed undetected Chrome under Xvfb. Imported only when a real attempt runs."""

    def __init__(self, proxy: str | None) -> None:
        self.proxy = proxy
        self.bytes = 0
        self.bytes_measured = False
        self._sb = None
        self._context = None

    def open(self, url: str) -> None:
        from seleniumbase import SB

        self._context = SB(**chrome_launch_options(self.proxy))
        self._sb = self._context.__enter__()
        self._sb.activate_cdp_mode(url)

    def block_extra_resources(self) -> None:
        driver = self._sb
        try:
            driver.execute_cdp_cmd("Network.enable", {})
            driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": BLOCKED})
        except Exception:
            return

    def probe(self) -> str:
        value = self._sb.execute_script(f"return {PROBE_JS}")
        return str(value or "pending")

    def solve_captcha(self) -> None:
        click = getattr(self._sb, "uc_gui_click_captcha", None)
        if callable(click):
            click()

    def html(self) -> str:
        self._account_bytes()
        return str(self._sb.get_page_source() or "")

    def stop(self) -> None:
        try:
            self._sb.execute_script("window.stop()")
        except Exception:
            return

    def _account_bytes(self) -> None:
        """Sum CDP encodedDataLength when Chrome performance logs are enabled."""
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
        pids = _process_tree(self._sb) if self._sb is not None else []
        if pids:
            _kill_pids(pids)
            return
        _kill_chrome_children()

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
