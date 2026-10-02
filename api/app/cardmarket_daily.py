"""Once-a-day price refresh for products someone holds.

The job posts to the existing scraper. It does not open a browser itself.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass

import httpx

from app.cardmarket import sample_key, snapshot_record, write_snapshot
from app.cardmarket_budget import QueueError, reconcile_attempt, reserve_attempt, scraper_block_reason
from app.cardmarket_queue import header_prices, rows_to_prices
from app.config import Settings, get_settings
from app.db import connect
from app.portfolio_db import portfolio_keys, statement

log = logging.getLogger("cardmarket.daily")

DAILY_PARSER = "daily-offers-v1"


def should_schedule(settings: Settings) -> bool:
    """The night job starts only when both switches are on."""
    return bool(settings.daily_prices_enabled and settings.scraper_enabled)


def accepted_daily_browsers(requested: int) -> int:
    """One held Chrome. A higher count is refused until each session has a window."""
    return 1


class DailyRateLimit(Exception):
    def __init__(self, retry_after: float) -> None:
        self.retry_after = max(0.0, float(retry_after))


@dataclass
class DailyPace:
    gap_min: float
    gap_max: float
    gap_step: float
    session_pages: int
    rotate_before: float
    lifetime: float
    now: callable
    gap: float
    session_id: str
    pages: int
    started: float
    challenge_streak: int

    @classmethod
    def from_settings(cls, settings: Settings, now=time.monotonic) -> DailyPace:
        pace = cls(
            gap_min=settings.daily_gap_min_s,
            gap_max=settings.daily_gap_max_s,
            gap_step=settings.daily_gap_step_s,
            session_pages=settings.daily_session_pages,
            rotate_before=settings.daily_session_rotate_before_s,
            lifetime=settings.scraper_browser_lifetime_s,
            now=now,
            gap=settings.daily_gap_min_s,
            session_id="",
            pages=0,
            started=0.0,
            challenge_streak=0,
        )
        pace.rotate()
        return pace

    def rotate(self) -> None:
        self.session_id = f"daily-{uuid.uuid4().hex[:16]}"
        self.pages = 0
        self.started = self.now()

    def due(self) -> bool:
        if self.pages >= self.session_pages:
            return True
        return self.now() - self.started >= self.lifetime - self.rotate_before

    def note(self, outcome: str) -> None:
        if outcome in {"offers", "empty"}:
            self.challenge_streak = 0
            self.gap = max(self.gap_min, self.gap - self.gap_step)
            self.pages += 1
        elif outcome == "challenge_unsolved":
            self.challenge_streak += 1
            self.gap = min(self.gap_max, self.gap + self.gap_step)
            self.pages += 1
            self.rotate()
            return
        elif outcome == "rate_limited":
            self.gap = self.gap_max
            self.rotate()
            return
        else:
            self.pages += 1
        if self.due():
            self.rotate()


def extra_sleep(gap: float, page_gap: float) -> float:
    return max(0.0, gap - page_gap)


def replace_portfolio(conn, session_id: str, products: list[tuple[str, str]]) -> int:
    """Replace one session's holdings. Each item is a sample key and when it was opened."""
    kept: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw, opened in products:
        key = sample_key(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append((key, opened))
    conn.execute(
        statement(conn, "DELETE FROM portfolio_products WHERE session_id = ?"),
        (session_id,),
    )
    if kept:
        conn.executemany(
            statement(
                conn,
                """
                INSERT INTO portfolio_products (session_id, sample_key, opened_at)
                VALUES (?, ?, ?)
                """,
            ),
            [(session_id, key, opened) for key, opened in kept],
        )
    conn.commit()
    return len(kept)


def due_urls(conn, today: str, portfolio=None) -> list[str]:
    """Distinct holdings, newest open first, skipping a snapshot already written today."""
    pending: list[str] = []
    for key in portfolio_keys(portfolio or conn):
        record = snapshot_record(conn, key)
        stamps = (
            str((record or {}).get("observed_at") or ""),
            str((record or {}).get("fetched_at") or ""),
        )
        if any(stamp.startswith(today) for stamp in stamps):
            continue
        pending.append(key)
    return pending


def _prices(result: dict) -> list[dict]:
    header = result.get("header") if isinstance(result.get("header"), dict) else None
    return rows_to_prices(list(result.get("rows") or [])) + header_prices(header)


def store_result(conn, url: str, result: dict) -> bool:
    outcome = str(result.get("outcome") or "")
    prices = _prices(result)
    if outcome == "offers" and prices:
        write_snapshot(
            conn,
            url,
            prices,
            parser_version=DAILY_PARSER,
            sampled_offer_count=len(prices),
        )
        return True
    if outcome == "empty":
        write_snapshot(
            conn,
            url,
            prices,
            parser_version=DAILY_PARSER,
            sampled_offer_count=len(prices),
            allow_empty=not prices,
            empty_source=DAILY_PARSER,
        )
        return True
    return False


def scrape_product(settings: Settings, url: str, session_id: str) -> dict:
    response = httpx.post(
        f"{settings.scraper_url.rstrip('/')}/scrape",
        json={"url": url, "session_id": session_id},
        headers={"Authorization": f"Bearer {settings.scraper_api_key}"},
        timeout=settings.scraper_attempt_seconds + 30,
    )
    if response.status_code == 503:
        raw = response.headers.get("retry-after", "").strip()
        try:
            delay = float(raw)
        except ValueError:
            delay = 0
        raise DailyRateLimit(delay)
    response.raise_for_status()
    body = response.json()
    return body if isinstance(body, dict) else {}


def run_pass(
    conn,
    settings: Settings,
    *,
    scrape,
    sleep,
    today: str,
    portfolio=None,
    now=time.monotonic,
) -> str:
    """Walk today's remaining holdings. Returns done, capped, paused, or blocked."""
    if settings.photo_scrape_active:
        log.info("daily paused reason=photo-scrape")
        return "paused"
    if accepted_daily_browsers(settings.daily_browsers) != settings.daily_browsers:
        log.info("daily browsers requested=%s using=1", settings.daily_browsers)
    pace = DailyPace.from_settings(settings, now)
    for url in due_urls(conn, today, portfolio):
        if settings.photo_scrape_active:
            return "paused"
        reason = scraper_block_reason(conn)
        if reason in {"daily-pages", "daily-mb"}:
            log.info("daily stop reason=%s", reason)
            return "capped"
        if reason:
            log.info("daily stop reason=%s", reason)
            return "blocked"
        try:
            reservation = reserve_attempt(conn, sample=url, session_id=pace.session_id, ip="daily")
        except QueueError as exc:
            log.info("daily stop reason=budget detail=%s", exc.detail)
            return "capped"
        started = time.monotonic()
        resumed = False
        while True:
            try:
                result = _load(conn, url, pace, reservation, scrape, started)
                if str(result.get("outcome") or "") == "challenge_unsolved":
                    try:
                        reservation = reserve_attempt(
                            conn, sample=url, session_id=pace.session_id, ip="daily"
                        )
                    except QueueError:
                        return "capped"
                    result = _load(conn, url, pace, reservation, scrape, time.monotonic())
                break
            except DailyRateLimit as exc:
                reconcile_attempt(
                    conn,
                    reservation,
                    outcome="rate_limited",
                    actual_bytes=None,
                    elapsed_ms=int((time.monotonic() - started) * 1000),
                )
                pace.note("rate_limited")
                sleep(exc.retry_after)
                if resumed:
                    return "blocked"
                resumed = True
                try:
                    reservation = reserve_attempt(
                        conn, sample=url, session_id=pace.session_id, ip="daily"
                    )
                except QueueError:
                    return "capped"
                started = time.monotonic()
        sleep(extra_sleep(pace.gap, settings.scraper_page_gap_s))
    return "done"


def _load(conn, url: str, pace: DailyPace, reservation: str, scrape, started: float) -> dict:
    result = scrape(url, pace.session_id)
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
    if store_result(conn, str(result.get("url") or url), result):
        log.info("daily stored outcome=%s url=%s", outcome, url)
    else:
        log.info("daily skipped outcome=%s url=%s", outcome or "timeout", url)
    pace.note(outcome)
    return result


def run_once(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if not should_schedule(settings):
        return "disabled"
    conn = connect(settings.catalog_sqlite)
    portfolio = _portfolio_conn(settings)
    try:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        return run_pass(
            conn,
            settings,
            scrape=lambda url, session_id: scrape_product(settings, url, session_id),
            sleep=time.sleep,
            today=today,
            portfolio=portfolio,
        )
    finally:
        if portfolio is not None:
            portfolio.close()
        conn.close()


def _portfolio_conn(settings: Settings):
    url = settings.portfolio_database_url.get_secret_value().strip()
    if not url:
        return None
    from app.portfolio_db import connect_portfolio

    return connect_portfolio(url)
