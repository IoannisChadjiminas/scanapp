"""Claims proxy jobs from SQLite and asks the scraper service for one attempt."""

from __future__ import annotations

import logging
import threading
import time
import uuid

import httpx

from app.cardmarket import sample_key
from app.cardmarket_budget import (
    cooldown_remaining,
    note_scraper_health,
    reconcile_attempt,
    release_attempt,
    scraper_online,
    reserve_attempt,
)
from app.cardmarket_queue import (
    PROXY_WORKER_ID,
    QueueError,
    claim_proxy_job,
    complete_proxy_job,
    fail_proxy_job,
    release_job,
    chart_prices,
    header_prices,
    rows_to_prices,
    sample_is_fresh,
)
from app.config import Settings
from app.db import connect

def classify_503(response: httpx.Response) -> str:
    """Busy and restarts did not reach Cardmarket. A long Retry-After is a rate limit."""
    detail = ""
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        detail = str(body.get("detail") or "")
    if detail in {"Busy", "Starting", "Restarting"}:
        return "busy"
    if detail == "Rate limited":
        return "rate_limited"
    return "rate_limited" if _retry_after(response) >= 60 else "busy"


def _retry_after(response: httpx.Response) -> float:
    try:
        return float(response.headers.get("retry-after", "").strip() or 0)
    except ValueError:
        return 0.0


class LanePool:
    """One dispatcher thread per scraper URL. The queue claim is what keeps a job on one lane."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.lanes = []
        for index, url in enumerate(settings.lane_urls):
            lane = ScraperWorker(settings.model_copy(update={"scraper_url": url}), name=chr(ord("a") + index))
            lane.pool = self
            self.lanes.append(lane)
        self._lock = threading.Lock()

    def start(self) -> None:
        from app.cardmarket_budget import bind_pool

        bind_pool(self)
        for lane in self.lanes:
            lane.start()

    def stop(self) -> None:
        from app.cardmarket_budget import bind_pool

        for lane in self.lanes:
            lane.stop()
        bind_pool(None)

    def defer_cold(self, lane: ScraperWorker) -> bool:
        if lane.cleared or len(self.lanes) < 2:
            return False
        return any(
            other is not lane and other.cleared and not other.busy and not other.leased_by
            for other in self.lanes
        )

    def account_wide_block(self) -> bool:
        recent = [lane for lane in self.lanes if time.time() - lane.last_rate_limit_at < 600]
        return len(recent) >= 2

    def block_reason(self, conn) -> str | None:
        settings = self.settings
        if not settings.scraper_enabled:
            return "disabled"
        if not settings.lane_urls:
            return "no-url"
        if not settings.scraper_api_key:
            return "no-key"
        from app.cardmarket_budget import usage_today

        pages, used = usage_today(conn)
        if pages >= settings.scraper_daily_pages:
            return "daily-pages"
        if used >= settings.scraper_daily_mb * 1024 * 1024:
            return "daily-mb"
        now = time.time()
        ready = [
            lane
            for lane in self.lanes
            if lane._health_state == "online"
            and now >= lane.breaker_until
            and now >= lane.lane_cooldown_until
        ]
        if ready:
            return None
        if any(now < lane.lane_cooldown_until for lane in self.lanes):
            return "cooldown"
        return "no-lane"

    def lease(self, owner: str, conn, timeout: float = 1):
        from app.cardmarket_queue import interactive_pending

        deadline = time.time() + timeout
        while True:
            if interactive_pending(conn):
                if time.time() >= deadline:
                    return None
                time.sleep(0.2)
                continue
            with self._lock:
                free = [
                    lane
                    for lane in self.lanes
                    if not lane.leased_by and not lane.busy and time.time() >= lane.breaker_until
                    and time.time() >= lane.lane_cooldown_until
                ]
                if len(self.lanes) >= 2 and len(free) < 2:
                    free = []
                if free:
                    free[0].leased_by = owner
                    return free[0]
            if time.time() >= deadline:
                return None
            time.sleep(0.2)

    def release_lease(self, lane: ScraperWorker) -> None:
        with self._lock:
            if lane.leased_by:
                lane.leased_by = None


log = logging.getLogger("cardmarket.scraper")


class StickySession:
    """One proxy id while the scraper reuses the window. A block or a new window mints another."""

    def __init__(self) -> None:
        self.session_id = str(uuid.uuid4())
        self._fresh = True

    def note(self, *, reused: bool, outcome: str) -> None:
        if outcome in {"challenge_unsolved", "rate_limited"}:
            self._mint()
            return
        if not reused and not self._fresh:
            self._mint()
            return
        self._fresh = False

    def _mint(self) -> None:
        self.session_id = str(uuid.uuid4())
        self._fresh = True


class ScraperWorker:
    def __init__(self, settings: Settings, name: str = "a") -> None:
        self.settings = settings
        self.name = name
        self._sticky = StickySession()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._health_state: str | None = None
        self.failures = 0
        self.breaker_until = 0.0
        self.lane_cooldown_until = 0.0
        self.cleared = False
        self.busy = False
        self.pool = None
        self.leased_by: str | None = None
        self.last_rate_limit_at = 0.0

    def start(self) -> None:
        log.info("paid worker starting")
        self._thread = threading.Thread(
            target=self._loop, name="cardmarket-proxy", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        conn = connect(self.settings.catalog_sqlite)
        try:
            while not self._stop.is_set():
                self._ping()
                now = time.time()
                if now < self.breaker_until or now < self.lane_cooldown_until:
                    self._stop.wait(1)
                    continue
                if self.leased_by:
                    self._stop.wait(1)
                    continue
                if self.pool is not None and self.pool.defer_cold(self):
                    self._stop.wait(2)
                    continue
                remaining = cooldown_remaining()
                if remaining > 0:
                    self._stop.wait(min(remaining, 5))
                    continue
                try:
                    job = claim_proxy_job(conn, PROXY_WORKER_ID)
                except Exception:
                    log.exception("proxy claim failed")
                    self._stop.wait(2)
                    continue
                if job is None:
                    self._stop.wait(1)
                    continue
                try:
                    self.busy = True
                    self._handle(conn, job)
                except Exception:
                    log.exception("proxy job failed")
                    self._release(conn, job, "worker")
                finally:
                    self.busy = False
        finally:
            conn.close()

    def _ping(self) -> None:
        url = self.settings.scraper_url.rstrip("/")
        before = scraper_online()
        if not url:
            note_scraper_health(False)
            self._log_health("no-url")
            self._log_online(before)
            return
        try:
            response = httpx.get(f"{url}/health", timeout=5)
            body = response.json() if response.status_code == 200 else {}
            reported = float(body.get("cooldown_until") or 0)
            # A zero from /health must not erase a cooldown this process already recorded.
            cooldown = reported if reported > time.time() else None
            if cooldown is not None:
                cooldown = max(cooldown, cooldown_remaining() + time.time())
            note_scraper_health(response.status_code == 200 and body.get("ok") is True, cooldown)
            self._log_health(
                "online" if response.status_code == 200 and body.get("ok") is True
                else f"http-{response.status_code}-invalid-health"
            )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            note_scraper_health(False)
            self._log_health(type(exc).__name__)
        self._log_online(before)

    def _log_health(self, state: str) -> None:
        if state != self._health_state:
            log.info("scraper health state=%s", state)
            self._health_state = state

    def _log_online(self, before: bool) -> None:
        online = scraper_online()
        if online != before:
            log.info("scraper %s", "online" if online else "offline")

    def _handle(self, conn, job: dict) -> None:
        target = sample_key(job.get("url"), job.get("filters")) or str(job.get("url") or "")
        if sample_is_fresh(conn, target):
            log.info("paid skipped reason=fresh-cache job=%s url=%s", job["id"], target)
            self._mark_done(conn, job)
            return
        remaining = cooldown_remaining()
        if remaining > 0:
            self._release(conn, job, "cooldown", delay_seconds=remaining)
            return
        try:
            reservation = reserve_attempt(
                conn, sample=target, session_id="proxy", ip=""
            )
        except QueueError as exc:
            log.info("paid failed reason=budget detail=%s url=%s", exc.detail, target)
            fail_proxy_job(conn, job["id"], job["claim_token"], "budget", terminal=True)
            return
        started = time.monotonic()
        log.info("paid request url=%s", target)
        try:
            result = self._scrape(target)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 503 and classify_503(exc.response) == "busy":
                log.info("paid released reason=busy url=%s", target)
                release_attempt(conn, reservation, "busy")
                self._release(conn, job, "busy", delay_seconds=5)
                return
            log.info(
                "paid failed reason=http status=%s url=%s",
                exc.response.status_code,
                target,
            )
            reconcile_attempt(
                conn,
                reservation,
                outcome="http",
                actual_bytes=None,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            if exc.response.status_code == 503:
                self._sticky.note(reused=False, outcome="rate_limited")
                self._note_lane_cooldown(exc.response)
                delay = self._note_cooldown(exc.response)
                self._release(conn, job, "busy", delay_seconds=delay or 5)
                return
            self.failures += 1
            self._trip_breaker()
            self._fail(conn, job, "http")
            return
        except httpx.HTTPError as exc:
            log.info(
                "paid failed reason=unreachable error=%s url=%s",
                type(exc).__name__,
                target,
            )
            reconcile_attempt(
                conn,
                reservation,
                outcome="unreachable",
                actual_bytes=None,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            self._fail(conn, job, "unreachable")
            self.failures += 1
            self._trip_breaker()
            return
        raw_bytes = result.get("bytes")
        measured = int(raw_bytes) if isinstance(raw_bytes, (int, float)) else None
        reconcile_attempt(
            conn,
            reservation,
            outcome=str(result.get("outcome") or "timeout"),
            actual_bytes=measured,
            elapsed_ms=int(result.get("elapsed_ms") or (time.monotonic() - started) * 1000),
        )
        outcome = str(result.get("outcome") or "")
        if outcome == "offers":
            self.failures = 0
            self.cleared = True
        elif outcome in {"timeout", "challenge_unsolved"}:
            self.failures += 1
            self._trip_breaker()
            if outcome == "challenge_unsolved":
                self.cleared = False
        log.info("paid result outcome=%s url=%s", outcome or "timeout", target)
        if outcome == "offers":
            prices = (
                rows_to_prices(list(result.get("rows") or []))
                + header_prices(
                    result.get("header") if isinstance(result.get("header"), dict) else None
                )
                + chart_prices(
                    result.get("chart") if isinstance(result.get("chart"), list) else None
                )
            )
            if not prices:
                self._fail(conn, job, "parser")
                return
            complete_proxy_job(
                conn,
                job["id"],
                job["claim_token"],
                url=str(result.get("url") or target),
                prices=prices,
                submission_id=str(uuid.uuid4()),
                sampled_offer_count=len(prices),
            )
            return
        if outcome == "empty":
            general = header_prices(
                result.get("header") if isinstance(result.get("header"), dict) else None
            )
            complete_proxy_job(
                conn,
                job["id"],
                job["claim_token"],
                url=str(result.get("url") or target),
                prices=general,
                empty=not general,
                submission_id=str(uuid.uuid4()),
                sampled_offer_count=0,
            )
            return
        log.info("paid failed reason=%s url=%s", outcome or "timeout", target)
        self._fail(conn, job, outcome or "timeout")

    def _scrape(self, url: str) -> dict:
        response = httpx.post(
            f"{self.settings.scraper_url.rstrip('/')}/scrape",
            json={"url": url, "session_id": self._sticky.session_id},
            headers={"Authorization": f"Bearer {self.settings.scraper_api_key}"},
            timeout=self.settings.scraper_attempt_seconds + 30,
        )
        if response.status_code == 503:
            raise httpx.HTTPStatusError(
                "scraper unavailable", request=response.request, response=response
            )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            return {}
        self._sticky.note(
            reused=body.get("reused") is True,
            outcome=str(body.get("outcome") or ""),
        )
        return body

    def _fail(self, conn, job: dict, reason: str) -> None:
        terminal = int(job.get("attempts") or 0) >= 1 or reason in {
            "wrong_product",
            "budget",
        }
        fail_proxy_job(
            conn, job["id"], job["claim_token"], reason[:80], terminal=terminal
        )

    def _note_lane_cooldown(self, response: httpx.Response) -> None:
        seconds = _retry_after(response)
        if seconds <= 0:
            return
        self.lane_cooldown_until = time.time() + seconds
        self.last_rate_limit_at = time.time()

    def _trip_breaker(self) -> None:
        limit = max(1, int(self.settings.scraper_breaker_failures))
        if self.failures < limit:
            return
        step = self.failures - limit
        wait = min(
            float(self.settings.scraper_breaker_max_s),
            float(self.settings.scraper_breaker_base_s) * (2**step),
        )
        self.breaker_until = time.time() + wait
        self.failures = 0
        log.info("lane breaker name=%s wait_s=%.0f", self.name, wait)

    def _note_cooldown(self, response: httpx.Response) -> float:
        seconds = _retry_after(response)
        if seconds > 0 and (self.pool is None or self.pool.account_wide_block()):
            note_scraper_health(True, time.time() + seconds)
        return seconds

    def _release(self, conn, job: dict, reason: str, delay_seconds: float = 0) -> None:
        try:
            release_job(
                conn,
                PROXY_WORKER_ID,
                job["id"],
                job["claim_token"],
                reason=reason,
                delay_seconds=delay_seconds,
            )
        except QueueError:
            return

    def _mark_done(self, conn, job: dict) -> None:
        from app.cardmarket_queue import _notify_job_url, _require_claim, datetime_now, immediate_transaction

        with immediate_transaction(conn):
            _require_claim(conn, job["id"], PROXY_WORKER_ID, job["claim_token"])
            conn.execute(
                """
                UPDATE cardmarket_jobs
                SET status = 'done', updated_at = ?, claim_expires_at = NULL
                WHERE id = ?
                """,
                (datetime_now(), job["id"]),
            )
        _notify_job_url(job.get("url"), job.get("filters"))
