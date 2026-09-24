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
    header_prices,
    rows_to_prices,
    sample_is_fresh,
)
from app.config import Settings
from app.db import connect

log = logging.getLogger("cardmarket.scraper")


class ScraperWorker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._health_state: str | None = None

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
                    self._handle(conn, job)
                except Exception:
                    log.exception("proxy job failed")
                    self._release(conn, job, "worker")
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
                delay = self._note_cooldown(exc.response)
                self._release(conn, job, "busy", delay_seconds=delay or 5)
                return
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
        log.info("paid result outcome=%s url=%s", outcome or "timeout", target)
        if outcome == "offers":
            prices = rows_to_prices(list(result.get("rows") or [])) + header_prices(
                result.get("header") if isinstance(result.get("header"), dict) else None
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
            complete_proxy_job(
                conn,
                job["id"],
                job["claim_token"],
                url=str(result.get("url") or target),
                prices=[],
                empty=True,
                submission_id=str(uuid.uuid4()),
                sampled_offer_count=0,
            )
            return
        log.info("paid failed reason=%s url=%s", outcome or "timeout", target)
        self._fail(conn, job, outcome or "timeout")

    def _scrape(self, url: str) -> dict:
        response = httpx.post(
            f"{self.settings.scraper_url.rstrip('/')}/scrape",
            json={"url": url, "session_id": str(uuid.uuid4())},
            headers={"Authorization": f"Bearer {self.settings.scraper_api_key}"},
            timeout=self.settings.scraper_attempt_seconds + 30,
        )
        if response.status_code == 503:
            raise httpx.HTTPStatusError(
                "scraper unavailable", request=response.request, response=response
            )
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else {}

    def _fail(self, conn, job: dict, reason: str) -> None:
        terminal = int(job.get("attempts") or 0) >= 1 or reason in {
            "wrong_product",
            "budget",
        }
        fail_proxy_job(
            conn, job["id"], job["claim_token"], reason[:80], terminal=terminal
        )

    def _note_cooldown(self, response: httpx.Response) -> float:
        raw = response.headers.get("retry-after", "").strip()
        try:
            seconds = float(raw)
        except ValueError:
            return 0
        if seconds > 0:
            note_scraper_health(True, time.time() + seconds)
        return seconds if seconds > 0 else 0

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
