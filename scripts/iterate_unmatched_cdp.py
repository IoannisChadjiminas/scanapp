#!/usr/bin/env python3
"""Iterate unmatched Cardmarket product URLs with SeleniumBase CDP Mode.

One Chrome tab. Cloudflare captcha uses one OS mouse click. Error 1015
closes Chrome, waits, then resumes the same URL. Touch
/tmp/scanapp-unmatched-cdp.stop to halt.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp_listing import listing_image_helpers  # noqa: E402

API_BASE = os.environ.get("SCANAPP_API_BASE", "http://127.0.0.1:8000/api/v1")
TOKEN_PATH = Path(os.environ.get("SCANAPP_CDP_TOKEN_FILE", "/tmp/scanapp-cdp-helper.token"))
STATE_PATH = Path("/tmp/scanapp-unmatched-cdp.state.json")
LOG_PATH = Path("/tmp/scanapp-unmatched-cdp.log")
STOP_PATH = Path("/tmp/scanapp-unmatched-cdp.stop")
BATCH = 50
PAGE_DEADLINE_S = 12.0
NAV_GAP_MIN_S = float(os.environ.get("SCANAPP_CDP_NAV_GAP_MIN_S", "2"))
NAV_GAP_MAX_S = float(os.environ.get("SCANAPP_CDP_NAV_GAP_MAX_S", "10"))
POLL_S = 0.03
CF_MAX_S = 40.0
RATE_LIMIT_PAUSE_S = float(os.environ.get("SCANAPP_CDP_RATE_LIMIT_S", "900"))
RATE_LIMIT_MAX_S = float(os.environ.get("SCANAPP_CDP_RATE_LIMIT_MAX_S", "3600"))
COOLDOWN_PATH = Path("/tmp/scanapp-unmatched-cdp.cooldown")

INSPECT_JS = (
    "(() => {\n"
    + listing_image_helpers()
    + r"""
  const picked = pickListingImage(document, location.href) || {};
  const title = document.title || "";
  const href = location.href || "";
  const src = String(picked.listingSrc || "");
  const listing = Boolean(picked.hasListingImage);
  if (listing) {
    return {title, url: href, cf: false, rateLimited: false, listingSrc: src, listingReady: Boolean(picked.listingReady), hasListingImage: true, listingHow: picked.listingHow || "", idProduct: picked.idProduct || ""};
  }
  const blob = (title + " " + href + " " + String(document.body && document.body.innerText || "").slice(0, 800)).toLowerCase();
  const rateLimited = /error 1015|you are being rate limited|banned you temporarily|access denied/.test(blob);
  if (rateLimited) {
    return {title, url: href, cf: false, rateLimited: true, listingSrc: src, listingReady: false, hasListingImage: false, listingHow: picked.listingHow || "", idProduct: picked.idProduct || ""};
  }
  const cf = /just a moment|einen moment|verify you are human|checking your browser|attention required/.test(blob);
  return {title, url: href, cf, rateLimited: false, listingSrc: src, listingReady: false, hasListingImage: false, listingHow: picked.listingHow || "", idProduct: picked.idProduct || ""};
})()
"""
)


def log(event: str, **fields: object) -> None:
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event, **fields}
    line = json.dumps(row, ensure_ascii=False)
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"after": "", "stored": 0, "skipped": 0, "failed": 0}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"after": "", "stored": 0, "skipped": 0, "failed": 0}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def issue_token() -> str:
    if TOKEN_PATH.exists():
        token = TOKEN_PATH.read_text(encoding="utf-8").strip()
        if token:
            return token
    proc = subprocess.run(
        ["docker", "compose", "exec", "-T", "api", "python", "-m", "app.helper_credential"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    token = ""
    for line in proc.stdout.splitlines():
        if line.startswith("token="):
            token = line.split("=", 1)[1].strip()
    if not token:
        raise RuntimeError("helper_credential did not print a token")
    TOKEN_PATH.write_text(token + "\n", encoding="utf-8")
    TOKEN_PATH.chmod(0o600)
    return token


def api(
    token: str,
    method: str,
    path: str,
    body: dict | None = None,
    timeout: int = 30,
    attempts: int = 5,
) -> dict:
    data = None
    headers = {"Authorization": f"Bearer {token}"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(f"{API_BASE}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} -> {exc.code} {detail}") from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            last_error = exc
            log("api-retry", method=method, path=path, attempt=attempt, error=str(exc))
            time.sleep(min(8, 1.5 * attempt))
    raise RuntimeError(f"{method} {path} failed after {attempts} attempts: {last_error}") from last_error


def js(sb, expression: str):
    driver = getattr(sb, "cdp", None)
    if driver is not None and hasattr(driver, "evaluate"):
        return driver.evaluate(expression)
    execute = getattr(sb, "execute_script", None)
    if callable(execute):
        return execute(f"return {expression}")
    raise RuntimeError("no JS evaluate on this SeleniumBase driver")


def inspect(sb) -> dict:
    payload = js(sb, INSPECT_JS) or {}
    if not isinstance(payload, dict):
        return {"cf": True, "rateLimited": False, "listingSrc": "", "listingReady": False, "url": "", "title": ""}
    return payload


def interruptible_sleep(seconds: float) -> bool:
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        if STOP_PATH.exists():
            return False
        time.sleep(min(1.0, deadline - time.monotonic()))
    return True


def cooldown_remaining() -> float:
    if not COOLDOWN_PATH.exists():
        return 0.0
    try:
        until = float(COOLDOWN_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0.0
    return max(0.0, until - time.time())


def set_cooldown(seconds: float) -> None:
    COOLDOWN_PATH.write_text(str(time.time() + seconds), encoding="utf-8")


def cdp_api(sb):
    return getattr(sb, "cdp", None)


def listing_ok(src: str) -> bool:
    if not src or any(token in src.lower() for token in ("logo", "favicon", "icon", "placeholder", "sprite", "notavailable")):
        return False
    try:
        parsed = urllib.parse.urlparse(src)
        host = (parsed.hostname or "").lower()
        path = (parsed.path or "").lower()
    except Exception:
        return False
    if host == "product-images.s3.cardmarket.com" or host.endswith(".product-images.s3.cardmarket.com"):
        return True
    return (host == "static.cardmarket.com" or host.endswith(".static.cardmarket.com")) and path.endswith(
        (".jpg", ".jpeg", ".png", ".webp")
    )


def example_solve_captcha(sb) -> dict:
    """Same sequence as examples/cdp_mode/raw_cf.py and raw_gitlab.py."""
    sb.sleep(2.5)
    attempts = [
        ("uc_gui_handle_captcha", getattr(sb, "uc_gui_handle_captcha", None)),
        ("uc_gui_click_captcha", getattr(sb, "uc_gui_click_captcha", None)),
        ("solve_captcha", getattr(sb, "solve_captcha", None)),
        ("cdp.gui_click_captcha", getattr(cdp_api(sb), "gui_click_captcha", None)),
        ("cdp.solve_captcha", getattr(cdp_api(sb), "solve_captcha", None)),
    ]
    seen: set[int] = set()
    for how, fn in attempts:
        if not callable(fn) or id(fn) in seen:
            continue
        seen.add(id(fn))
        log("captcha", how=how)
        try:
            fn()
        except Exception as exc:
            log("captcha-click-error", how=how, error=str(exc))
            continue
        sb.sleep(3)
        snap = inspect(sb)
        if snap.get("rateLimited"):
            log("captcha-click", how=how, result="rate-limited")
            return snap
        if snap.get("hasListingImage") or not snap.get("cf"):
            log("captcha-click", how=how, result="ok")
            return snap
        log("captcha-click", how=how, result="still-cf")
    return inspect(sb)


def goto_url(sb, url: str, first: bool) -> None:
    if first:
        sb.activate_cdp_mode(url)
        return
    if callable(getattr(sb, "goto", None)):
        sb.goto(url)
        return
    cdp_api(sb).goto(url)


@dataclass
class ProductQueue:
    token: str
    fetch_after: str
    items: deque = field(default_factory=deque)
    remaining: int = 0
    done: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def pop(self) -> dict | None:
        with self.lock:
            if self.items:
                return self.items.popleft()
        return None

    def pending(self) -> int:
        with self.lock:
            return len(self.items)

    def fill(self) -> None:
        with self.lock:
            if self.done or len(self.items) >= BATCH:
                return
            after = self.fetch_after
        batch = api(
            self.token,
            "GET",
            f"/cardmarket/helper/unmatched-products?after={urllib.parse.quote(after, safe='')}&limit={BATCH}",
            timeout=90,
        )
        products = list(batch.get("products") or [])
        remaining = int(batch.get("total") or 0)
        examined = str(batch.get("examined") or after)
        with self.lock:
            self.remaining = remaining
            if not products:
                if batch.get("has_more") and examined and examined != self.fetch_after:
                    self.fetch_after = examined
                    return
                if not self.items:
                    self.done = True
                return
            for item in products:
                self.items.append(item)
            self.fetch_after = str(products[-1].get("url") or self.fetch_after)
        log("batch", remaining=remaining, count=len(products), after=after, examined=self.fetch_after)


def prefetch_loop(queue: ProductQueue) -> None:
    while not STOP_PATH.exists() and not queue.done:
        if queue.pending() >= 20:
            time.sleep(0.25)
            continue
        try:
            queue.fill()
        except Exception as exc:
            log("prefetch-error", error=str(exc))
            time.sleep(3)
            continue
        if queue.pending() == 0 and not queue.done:
            time.sleep(0.25)


class Totals:
    def __init__(self, stored: int, skipped: int, failed: int) -> None:
        self.stored = stored
        self.skipped = skipped
        self.failed = failed
        self.lock = threading.Lock()
        self.started = time.monotonic()

    def snapshot(self) -> dict:
        with self.lock:
            return {"stored": self.stored, "skipped": self.skipped, "failed": self.failed}

    def persist(self, after: str) -> None:
        save_state({**self.snapshot(), "after": after})

    def rate(self) -> float:
        elapsed = max(1.0, time.monotonic() - self.started)
        with self.lock:
            return round(self.stored / elapsed * 60.0, 1)


def save_listing(token: str, item: dict, src: str, totals: Totals) -> None:
    url = str(item.get("url") or "")
    name = str(item.get("name") or "")
    try:
        result = api(
            token,
            "POST",
            "/cardmarket/helper/unmatched-image",
            {"url": url, "name": name, "image_url": src},
        )
        with totals.lock:
            if result.get("stored"):
                totals.stored += 1
            else:
                totals.skipped += 1
            stored = totals.stored
        totals.persist(url)
        log("stored", url=url, name=name or url, image_url=src, stored=result.get("stored"), total=stored, rpm=totals.rate())
    except Exception as exc:
        with totals.lock:
            totals.failed += 1
        totals.persist(url)
        log("fail", url=url, name=name, error=str(exc))


def mark_fail(item: dict, totals: Totals, **fields: object) -> None:
    url = str(item.get("url") or "")
    with totals.lock:
        totals.failed += 1
        failed = totals.failed
    totals.persist(url)
    log("fail", url=url, name=item.get("name") or "", failed=failed, **fields)


def pace_wait(pages_done: int) -> float:
    lo = min(NAV_GAP_MIN_S, NAV_GAP_MAX_S)
    hi = max(NAV_GAP_MIN_S, NAV_GAP_MAX_S)
    delay = random.uniform(lo, hi)
    log("pace", seconds=round(delay, 1), pages=pages_done)
    time.sleep(delay)
    return delay


def wait_for_listing(sb, item: dict, previous_src: str) -> dict:
    url = str(item.get("url") or "")
    wanted = url.rstrip("/")
    started = time.monotonic()
    tried_cf = False
    while not STOP_PATH.exists():
        now = time.monotonic()
        snap = inspect(sb)
        if snap.get("rateLimited"):
            return snap
        if snap.get("cf") and not snap.get("hasListingImage"):
            if not tried_cf:
                log("captcha-wait", url=url)
                snap = example_solve_captcha(sb)
                tried_cf = True
                started = time.monotonic()
                if snap.get("rateLimited"):
                    return snap
                src = str(snap.get("listingSrc") or "")
                if listing_ok(src) and src != previous_src:
                    return snap
                if snap.get("hasListingImage") or not snap.get("cf"):
                    continue
            if time.monotonic() - started > CF_MAX_S:
                return inspect(sb)
            time.sleep(0.4)
            continue
        href = str(snap.get("url") or "").rstrip("/")
        src = str(snap.get("listingSrc") or "")
        if wanted and href and wanted not in href and href not in wanted:
            if now - started > PAGE_DEADLINE_S:
                return snap
            time.sleep(POLL_S)
            continue
        if listing_ok(src) and src != previous_src:
            return snap
        if now - started > PAGE_DEADLINE_S:
            return snap
        time.sleep(POLL_S)
    return inspect(sb)


def crawl_session(sb, token: str, after: str, totals: Totals) -> str:
    queue = ProductQueue(token=token, fetch_after=after)
    queue.fill()
    worker = threading.Thread(target=prefetch_loop, args=(queue,), daemon=True)
    worker.start()
    item = queue.pop()
    if item is None:
        log("done", **totals.snapshot())
        return "done"

    goto_url(sb, str(item["url"]), first=True)
    previous_src = ""
    first = False
    pages_done = 0
    log("visit", url=item.get("url"), name=item.get("name"), remaining=queue.remaining, **totals.snapshot())

    while item is not None and not STOP_PATH.exists():
        snap = wait_for_listing(sb, item, previous_src)
        src = str(snap.get("listingSrc") or "")
        href = str(snap.get("url") or "")
        if snap.get("rateLimited"):
            log("rate-limited", url=item.get("url"), title=snap.get("title") or "")
            return "rate-limited"
        if listing_ok(src):
            previous_src = src
            log(
                "listing",
                url=item.get("url"),
                image_url=src,
                how=snap.get("listingHow") or "",
                idProduct=snap.get("idProduct") or "",
            )
            threading.Thread(
                target=save_listing,
                args=(token, item, src, totals),
                daemon=True,
            ).start()
        elif snap.get("cf"):
            mark_fail(item, totals, reason="captcha-timeout", title=snap.get("title") or "")
        else:
            mark_fail(item, totals, reason="timeout", href=href, title=snap.get("title") or "")

        pages_done += 1
        nxt = queue.pop()
        while nxt is None and not queue.done and not STOP_PATH.exists():
            time.sleep(0.1)
            nxt = queue.pop()
        if nxt is None:
            item = None
            break
        pace_wait(pages_done)
        try:
            goto_url(sb, str(nxt["url"]), first=first)
        except Exception as exc:
            mark_fail(nxt, totals, error=str(exc))
            item = queue.pop()
            continue
        item = nxt
        log(
            "visit",
            url=item.get("url"),
            name=item.get("name"),
            remaining=queue.remaining,
            **totals.snapshot(),
            rpm=totals.rate(),
        )

    for _ in range(40):
        if threading.active_count() <= 2:
            break
        time.sleep(0.1)
    log("done" if queue.done else "stop", **totals.snapshot())
    return "done" if queue.done else "stop"


def main() -> int:
    if STOP_PATH.exists():
        STOP_PATH.unlink()
    token = issue_token()
    state = load_state()
    after = str(state.get("after") or "")
    totals = Totals(
        stored=int(state.get("stored") or 0),
        skipped=int(state.get("skipped") or 0),
        failed=int(state.get("failed") or 0),
    )
    log("start", after=after, tabs=1, **totals.snapshot(), api=API_BASE)

    from seleniumbase import SB

    cooldown_s = RATE_LIMIT_PAUSE_S
    COOLDOWN_PATH.unlink(missing_ok=True)

    while not STOP_PATH.exists():
        stored_before = totals.snapshot()["stored"]
        result = "session-error"
        try:
            with SB(uc=True, test=True, guest=True, locale="en") as sb:
                result = crawl_session(sb, token, after, totals)
        except Exception as exc:
            log("session-error", error=str(exc), **totals.snapshot(), after=after)
        if result in {"done", "stop"}:
            return 0
        state = load_state()
        after = str(state.get("after") or after)
        snap = totals.snapshot()
        totals = Totals(
            stored=int(state.get("stored") or snap["stored"]),
            skipped=int(state.get("skipped") or snap["skipped"]),
            failed=int(state.get("failed") or snap["failed"]),
        )
        if result == "rate-limited":
            if totals.snapshot()["stored"] > stored_before:
                cooldown_s = RATE_LIMIT_PAUSE_S
            set_cooldown(cooldown_s)
            log("rate-limit-pause", seconds=round(cooldown_s), next_pause=round(min(RATE_LIMIT_MAX_S, cooldown_s * 2)))
            if not interruptible_sleep(cooldown_s):
                break
            cooldown_s = min(RATE_LIMIT_MAX_S, cooldown_s * 2)
            continue
        time.sleep(4)
    log("exit", **totals.snapshot(), after=after)
    return 0


if __name__ == "__main__":
    sys.exit(main())
