#!/usr/bin/env python3
"""Claim Cardmarket helper jobs with SeleniumBase CDP Mode.

Same queue as the Chrome extension: claim → open product URL → extract
prices (and listing image) → complete. Turnstile uses the OS mouse click.
Error 1015 releases the job and goes quiet so the extension can take over.
Touch /tmp/scanapp-helper-cdp.stop to halt.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp_listing import listing_image_helpers  # noqa: E402

API_BASE = os.environ.get("SCANAPP_API_BASE", "http://127.0.0.1:8000/api/v1")
TOKEN_PATH = Path(os.environ.get("SCANAPP_CDP_JOB_TOKEN_FILE", "/tmp/scanapp-cdp-job.token"))
LOG_PATH = Path("/tmp/scanapp-helper-cdp.log")
STOP_PATH = Path("/tmp/scanapp-helper-cdp.stop")
COOLDOWN_PATH = Path("/tmp/scanapp-helper-cdp.cooldown")
HELPER_ID = "cdp"
PARSER_VERSION = "offers-v1"
IDLE_POLL_S = 1.0
NAV_GAP_S = 3.0
CHROME_IDLE_S = 45.0
PAGE_DEADLINE_S = 20.0
POLL_S = 0.05
CF_MAX_S = 40.0
RATE_LIMIT_PAUSE_S = float(os.environ.get("SCANAPP_CDP_RATE_LIMIT_S", "900"))
RATE_LIMIT_MAX_S = float(os.environ.get("SCANAPP_CDP_RATE_LIMIT_MAX_S", "3600"))

COLLECT_JS = (
    "(() => {\n"
    + listing_image_helpers()
    + r"""
  const title = document.title || "";
  const href = location.href || "";
  const bodyText = String(document.body && document.body.innerText || "");
  const blob = (title + " " + href + " " + bodyText.slice(0, 800)).toLowerCase();
  const rateLimited = /error 1015|you are being rate limited|banned you temporarily|access denied/.test(blob);
  const picked = pickListingImage(document, location.href) || {};
  const listingSrc = String(picked.listingSrc || "");
  const listingOk = Boolean(picked.hasListingImage);
  const listingHow = picked.listingHow || "";
  const idProduct = picked.idProduct || "";
  if (rateLimited) {
    return {outcome: "rate_limited", title, url: href, cf: false, rateLimited: true, prices: [], empty: false, listingSrc, listingOk, listingHow, idProduct};
  }
  const cfNode = Boolean(document.querySelector("#challenge-form, .cf-turnstile, iframe[src*='challenges.cloudflare.com'], iframe[src*='turnstile']"));
  const cf = cfNode || /just a moment|einen moment|verify you are human|checking your browser|attention required/.test(blob);
  if (cf) {
    return {outcome: "challenge", title, url: href, cf: true, rateLimited: false, prices: [], empty: false, listingSrc, listingOk, listingHow, idProduct};
  }
  const parseAmount = (text) => {
    const source = String(text || "").replace(/\s/g, "");
    const european = source.match(/(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})/);
    const us = source.match(/(\d{1,3}(?:,\d{3})+\.\d{2}|\d+\.\d{2})/);
    let raw = null;
    if (european && us) {
      raw = source.lastIndexOf(",") > source.lastIndexOf(".") ? european[1] : us[1];
    } else if (european) {
      raw = european[1];
    } else if (us) {
      raw = us[1];
    }
    if (!raw) return null;
    if (raw.includes(".") && raw.includes(",")) {
      raw = raw.lastIndexOf(",") > raw.lastIndexOf(".")
        ? raw.replace(/\./g, "").replace(",", ".")
        : raw.replace(/,/g, "");
    } else if (/,\d{2}$/.test(raw)) {
      raw = raw.replace(",", ".");
    } else {
      raw = raw.replace(/,/g, "");
    }
    const amount = Number.parseFloat(raw);
    if (!Number.isFinite(amount) || amount <= 0) return null;
    return Math.round(amount * 100) / 100;
  };
  const CONDITION_RE = /^(NM|M|EX|GD|LP|PL|PO|SS|MT|Near Mint|Excellent)$/i;
  const prices = [];
  const seen = new Set();
  const rows = document.querySelectorAll(".article-row, tr.article");
  for (const row of rows) {
    let label = "";
    const nodes = row.querySelectorAll(".article-condition, [class*='condition'], .badge");
    for (const node of nodes) {
      const text = (node.textContent || "").trim().replace(/\s+/g, " ");
      if (text && CONDITION_RE.test(text.split(/\s/)[0] || text)) {
        label = text.split(/\s/)[0];
        break;
      }
    }
    if (!label) {
      label = (row.querySelector(".article-condition")?.textContent || "").trim();
    }
    const offer = row.querySelector(".col-offer, .price-container, [class*='col-offer']");
    if (!offer || offer.closest(".mobile-offer-container")) continue;
    const amount = parseAmount(offer.textContent || "");
    if (!label || amount == null) continue;
    const key = `${label}-${amount}`;
    if (seen.has(key)) continue;
    seen.add(key);
    prices.push({label, amount, currency: "EUR"});
    if (prices.length >= 3) break;
  }
  if (!prices.length) {
    const specs = [
      {re: /(?:^|\n)\s*From\s+([\d.,]+)\s*€/i, label: "From"},
      {re: /Price Trend\s+([\d.,]+)\s*€/i, label: "Trend"},
      {re: /7-days? average price\s+([\d.,]+)\s*€/i, label: "7-day"},
    ];
    for (const spec of specs) {
      const match = bodyText.match(spec.re);
      if (!match) continue;
      const amount = parseAmount(`${match[1]} €`);
      if (amount == null) continue;
      prices.push({label: spec.label, amount, currency: "EUR"});
    }
  }
  const emptyNode = Boolean(document.querySelector("[data-test-empty-articles], .noArticles, .no-articles"));
  const emptyText = /there are currently no articles|no articles available|there are no articles/.test(bodyText.toLowerCase());
  const empty = emptyNode || emptyText;
  let outcome = "unrecognized";
  if (prices.length) outcome = "offers";
  else if (empty) outcome = "empty";
  return {outcome, title, url: href, cf: false, rateLimited: false, prices, empty, listingSrc, listingOk, listingHow, idProduct, articleRowCount: rows.length};
})()
"""
)


def log(event: str, **fields: object) -> None:
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event, **fields}
    line = json.dumps(row, ensure_ascii=False)
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


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


def issue_token() -> str:
    if TOKEN_PATH.exists():
        token = TOKEN_PATH.read_text(encoding="utf-8").strip()
        if token.startswith(f"{HELPER_ID}."):
            return token
    last_error = ""
    for attempt in range(1, 8):
        proc = subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "api",
                "python",
                "-m",
                "app.helper_credential",
                "--helper-id",
                HELPER_ID,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            token = ""
            for line in proc.stdout.splitlines():
                if line.startswith("token="):
                    token = line.split("=", 1)[1].strip()
            if token:
                TOKEN_PATH.write_text(token + "\n", encoding="utf-8")
                TOKEN_PATH.chmod(0o600)
                return token
            raise RuntimeError("helper_credential did not print a token")
        last_error = (proc.stderr or proc.stdout or "").strip()
        log("token-retry", attempt=attempt, error=last_error[-400:])
        time.sleep(min(8, 1.5 * attempt))
    raise RuntimeError(f"helper_credential failed: {last_error}")


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
            if exc.code == 401 and attempt == 1:
                TOKEN_PATH.unlink(missing_ok=True)
            raise RuntimeError(f"{method} {path} -> {exc.code} {detail}") from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            last_error = exc
            log("api-retry", method=method, path=path, attempt=attempt, error=str(exc))
            time.sleep(min(8, 1.5 * attempt))
    raise RuntimeError(f"{method} {path} failed after {attempts} attempts: {last_error}") from last_error


def heartbeat(token: str, job_id: str | None = None) -> dict:
    return api(
        token,
        "POST",
        "/cardmarket/helper/status",
        {"ready": True, "paused": False, "attention": None, "current_job_id": job_id},
    )


def js(sb, expression: str):
    driver = getattr(sb, "cdp", None)
    if driver is not None and hasattr(driver, "evaluate"):
        return driver.evaluate(expression)
    execute = getattr(sb, "execute_script", None)
    if callable(execute):
        return execute(f"return {expression}")
    raise RuntimeError("no JS evaluate on this SeleniumBase driver")


def collect(sb) -> dict:
    payload = js(sb, COLLECT_JS) or {}
    if not isinstance(payload, dict):
        return {"outcome": "challenge", "cf": True, "rateLimited": False, "prices": [], "url": ""}
    return payload


def cdp_api(sb):
    return getattr(sb, "cdp", None)


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
        snap = collect(sb)
        if snap.get("rateLimited"):
            log("captcha-click", how=how, result="rate-limited")
            return snap
        if snap.get("outcome") in {"offers", "empty"} or not snap.get("cf"):
            log("captcha-click", how=how, result="ok")
            return snap
        log("captcha-click", how=how, result="still-cf")
    return collect(sb)


def goto_url(sb, url: str, first: bool) -> None:
    if first:
        sb.activate_cdp_mode(url)
        return
    if callable(getattr(sb, "goto", None)):
        sb.goto(url)
        return
    cdp_api(sb).goto(url)


def claim_job(token: str) -> dict | None:
    payload = api(token, "POST", "/cardmarket/helper/claim", {})
    if not payload.get("id") or payload.get("status") == "idle":
        return None
    return payload


def release_job(token: str, job: dict, reason: str) -> None:
    api(
        token,
        "POST",
        "/cardmarket/helper/release",
        {"job_id": job["id"], "claim_token": job["claim_token"], "reason": reason},
    )


def fail_job(token: str, job: dict, reason: str, terminal: bool = False) -> None:
    api(
        token,
        "POST",
        "/cardmarket/helper/fail",
        {
            "job_id": job["id"],
            "claim_token": job["claim_token"],
            "reason": reason,
            "terminal": terminal,
        },
    )


def complete_job(token: str, job: dict, snap: dict) -> dict:
    prices = list(snap.get("prices") or [])
    empty = bool(snap.get("empty")) and not prices
    result = api(
        token,
        "POST",
        "/cardmarket/helper/complete",
        {
            "job_id": job["id"],
            "claim_token": job["claim_token"],
            "submission_id": str(uuid.uuid4()),
            "url": str(snap.get("url") or job.get("url") or ""),
            "prices": prices,
            "empty": empty,
            "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "parser_version": PARSER_VERSION,
            "sampled_offer_count": len(prices),
        },
    )
    src = str(snap.get("listingSrc") or "")
    if snap.get("listingOk") and src:
        try:
            api(
                token,
                "POST",
                "/cardmarket/helper/unmatched-image",
                {"url": str(job.get("url") or ""), "name": str(job.get("card_id") or ""), "image_url": src},
            )
        except Exception as exc:
            log("listing-image-skip", url=job.get("url"), error=str(exc))
    return result


def wait_for_product(sb, token: str, job: dict) -> dict:
    url = str(job.get("url") or "")
    wanted = url.rstrip("/")
    started = time.monotonic()
    tried_cf = False
    last_renew = started
    while not STOP_PATH.exists():
        now = time.monotonic()
        if now - last_renew > 90:
            try:
                api(
                    token,
                    "POST",
                    "/cardmarket/helper/renew",
                    {"job_id": job["id"], "claim_token": job["claim_token"]},
                )
            except Exception as exc:
                log("renew-skip", error=str(exc))
            last_renew = now
        snap = collect(sb)
        if snap.get("rateLimited"):
            return snap
        if snap.get("cf") and snap.get("outcome") == "challenge":
            if not tried_cf:
                log("captcha-wait", url=url)
                snap = example_solve_captcha(sb)
                tried_cf = True
                started = time.monotonic()
                if snap.get("rateLimited") or snap.get("outcome") in {"offers", "empty"}:
                    return snap
            if time.monotonic() - started > CF_MAX_S:
                return collect(sb)
            time.sleep(0.4)
            continue
        href = str(snap.get("url") or "").rstrip("/")
        if wanted and href and wanted not in href and href not in wanted:
            if now - started > PAGE_DEADLINE_S:
                return snap
            time.sleep(POLL_S)
            continue
        if snap.get("outcome") in {"offers", "empty"}:
            return snap
        if now - started > PAGE_DEADLINE_S:
            return snap
        time.sleep(POLL_S)
    return collect(sb)


def handle_job(sb, token: str, job: dict, first: bool) -> str:
    url = str(job.get("url") or "")
    log("visit", url=url, job_id=job.get("id"), card_id=job.get("card_id") or "")
    heartbeat(token, str(job.get("id") or ""))
    try:
        goto_url(sb, url, first=first)
    except Exception as exc:
        log("nav-error", url=url, error=str(exc))
        fail_job(token, job, "timeout")
        return "fail"
    snap = wait_for_product(sb, token, job)
    if snap.get("rateLimited"):
        log("rate-limited", url=url, title=snap.get("title") or "")
        try:
            release_job(token, job, "rate_limited")
        except Exception as exc:
            log("release-error", error=str(exc))
        return "rate-limited"
    outcome = str(snap.get("outcome") or "")
    if outcome in {"offers", "empty"}:
        try:
            result = complete_job(token, job, snap)
            log(
                "complete",
                url=url,
                job_id=job.get("id"),
                prices=len(snap.get("prices") or []),
                empty=bool(snap.get("empty")),
                listing=bool(snap.get("listingOk")),
                status=result.get("status"),
            )
            return "ok"
        except Exception as exc:
            log("complete-error", url=url, error=str(exc))
            fail_job(token, job, "parser")
            return "fail"
    if outcome == "challenge" or snap.get("cf"):
        log("captcha-timeout", url=url, title=snap.get("title") or "")
        try:
            release_job(token, job, "challenge")
        except Exception as exc:
            log("release-error", error=str(exc))
        return "fail"
    href = str(snap.get("url") or "")
    if href and url.rstrip("/") not in href.rstrip("/") and href.rstrip("/") not in url.rstrip("/"):
        fail_job(token, job, "wrong_product", terminal=True)
        log("wrong-product", url=url, href=href)
        return "fail"
    fail_job(token, job, "parser")
    log("parser-timeout", url=url, href=href, title=snap.get("title") or "")
    return "fail"


def chrome_session(token: str, first_job: dict) -> str:
    from seleniumbase import SB

    job = first_job
    first = True
    last_nav = 0.0
    idle_since = None
    with SB(uc=True, test=True, guest=True, locale="en") as sb:
        while job is not None and not STOP_PATH.exists():
            if cooldown_remaining() > 0:
                return "rate-limited"
            gap = NAV_GAP_S - (time.monotonic() - last_nav) if last_nav else 0.0
            if gap > 0:
                time.sleep(gap)
            result = handle_job(sb, token, job, first=first)
            first = False
            last_nav = time.monotonic()
            if result == "rate-limited":
                return "rate-limited"
            idle_since = time.monotonic()
            job = None
            while not STOP_PATH.exists():
                leftover = cooldown_remaining()
                if leftover > 0:
                    return "rate-limited"
                heartbeat(token)
                nxt = claim_job(token)
                if nxt is not None:
                    job = nxt
                    idle_since = None
                    break
                if time.monotonic() - idle_since >= CHROME_IDLE_S:
                    return "idle"
                if not interruptible_sleep(IDLE_POLL_S):
                    return "stop"
    return "idle"


def main() -> int:
    if STOP_PATH.exists():
        STOP_PATH.unlink()
    token = issue_token()
    log("start", api=API_BASE, helper_id=HELPER_ID)
    cooldown_s = RATE_LIMIT_PAUSE_S
    while not STOP_PATH.exists():
        leftover = cooldown_remaining()
        if leftover > 0:
            log("rate-limit-pause", seconds=round(leftover))
            if not interruptible_sleep(leftover):
                break
            continue
        try:
            heartbeat(token)
        except Exception as exc:
            log("heartbeat-error", error=str(exc))
            if "401" in str(exc):
                token = issue_token()
            if not interruptible_sleep(3):
                break
            continue
        try:
            job = claim_job(token)
        except Exception as exc:
            log("claim-error", error=str(exc))
            if not interruptible_sleep(3):
                break
            continue
        if job is None:
            if not interruptible_sleep(IDLE_POLL_S):
                break
            continue
        try:
            result = chrome_session(token, job)
        except Exception as exc:
            log("session-error", error=str(exc), job_id=job.get("id"))
            result = "fail"
        if result == "stop":
            break
        if result == "rate-limited":
            set_cooldown(cooldown_s)
            log("rate-limit-pause", seconds=round(cooldown_s), next_pause=round(min(RATE_LIMIT_MAX_S, cooldown_s * 2)))
            if not interruptible_sleep(cooldown_s):
                break
            cooldown_s = min(RATE_LIMIT_MAX_S, cooldown_s * 2)
            continue
        cooldown_s = RATE_LIMIT_PAUSE_S
    log("exit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
