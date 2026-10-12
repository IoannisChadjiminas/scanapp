"""Once-a-day price refresh for products someone holds.

The job posts to the existing scraper. It does not open a browser itself.
"""

from __future__ import annotations

import logging
import random
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import httpx

from app.cardmarket import sample_key, snapshot_record, write_snapshot
from app.cardmarket_budget import (
    QueueError,
    current_pool,
    reconcile_attempt,
    reserve_attempt,
    scraper_block_reason,
    usage_today,
)
from app.cardmarket_queue import header_prices, rows_to_prices
from app.config import Settings, get_settings
from app.db import connect
from app.price_sources import market_trend, parse_tiers, trend_for_url
from app.portfolio_db import portfolio_keys, statement

log = logging.getLogger("cardmarket.daily")
daily_lane_url: ContextVar[str] = ContextVar("daily_lane_url", default="")

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
    try:
        conn.execute(
            statement(conn, "DELETE FROM portfolio_products WHERE session_id = ?"),
            (session_id,),
        )
        # A psycopg connection has no executemany, so insert in plain
        # multi-row statements that every connection type can run.
        for start in range(0, len(kept), 300):
            chunk = kept[start:start + 300]
            conn.execute(
                statement(
                    conn,
                    "INSERT INTO portfolio_products (session_id, sample_key, opened_at) VALUES "
                    + ", ".join("(?, ?, ?)" for _ in chunk),
                ),
                [value for key, opened in chunk for value in (session_id, key, opened)],
            )
    except Exception:
        # Do not leave the shared connection holding a half-done replace.
        conn.rollback()
        raise
    conn.commit()
    return len(kept)


def _read_date(record: dict | None) -> date | None:
    stamp = str((record or {}).get("observed_at") or "")[:10]
    try:
        return date.fromisoformat(stamp) if stamp else None
    except ValueError:
        return None


def tier_days(settings: Settings, trend: float | None) -> int:
    """Days between nightly reads for a card worth `trend` EUR. Unknown: every night."""
    if trend is None or trend <= 0:
        return 1
    for bound, days in parse_tiers(settings.daily_tiers):
        if bound is None or trend < bound:
            return max(1, days)
    return 1


def _listing_trend(record: dict | None) -> float | None:
    """The trend Cardmarket's own page showed on the last listing read."""
    for quote in (record or {}).get("prices") or []:
        if quote.get("label") == "Trend":
            amount = quote.get("amount")
            if isinstance(amount, (int, float)) and amount > 0:
                return float(amount)
    return None


def trend_moved(file_trend: float | None, read_trend: float | None, pct: float) -> bool:
    if not file_trend or not read_trend or pct <= 0:
        return False
    return abs(file_trend - read_trend) / read_trend * 100 > pct


def due_urls(
    conn,
    today: str,
    portfolio=None,
    settings: Settings | None = None,
    rng: random.Random | None = None,
) -> list[str]:
    """Holdings whose last listing read is older than their value tier.

    Order: cards about to pass the listing age limit, cards whose trend moved,
    dearer cards, then the rest. Each group is shuffled.
    """
    settings = settings or get_settings()
    rng = rng or random.Random()
    day = date.fromisoformat(today)
    max_age = max(1, int(settings.cardmarket_listing_max_age_days))
    groups: list[list[str]] = [[], [], [], []]
    for key in portfolio_keys(portfolio or conn):
        record = snapshot_record(conn, key)
        if str((record or {}).get("fetched_at") or "").startswith(today):
            continue
        read_on = _read_date(record) if (record or {}).get("prices") else None
        trend = trend_for_url(conn, key)
        if read_on is None:
            groups[2 if trend is None or trend >= 2 else 3].append(key)
            continue
        age = (day - read_on).days
        if age <= 0:
            continue
        if age >= max_age - 1:
            groups[0].append(key)
        elif trend_moved(trend, _listing_trend(record), settings.daily_move_pct):
            groups[1].append(key)
        elif age >= tier_days(settings, trend):
            groups[2 if trend is None or trend >= 20 else 3].append(key)
    pending: list[str] = []
    for group in groups:
        rng.shuffle(group)
        pending.extend(group)
    return pending


def jittered(gap: float, jitter: float, rng: random.Random | None = None) -> float:
    spread = max(0.0, min(float(jitter), 0.9))
    return max(0.0, gap * (1 + (rng or random).uniform(-spread, spread)))


def seconds_until(deadline: str, now: datetime) -> float:
    """Seconds from `now` (UTC) to the next HH:MM, or 0 when it is malformed."""
    try:
        hour, minute = (int(part) for part in deadline.split(":", 1))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except ValueError:
        return 0.0
    if target < now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def deadline_gap(gap: float, gap_min: float, remaining: int, seconds_left: float, load_s: float) -> float:
    """Shorten the gap toward its minimum when the rest of the night will not fit."""
    if remaining <= 0 or seconds_left <= 0:
        return gap_min
    fits = seconds_left / remaining - load_s
    return min(gap, max(gap_min, fits))


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
    base = daily_lane_url.get() or settings.scraper_url
    response = httpx.post(
        f"{base.rstrip('/')}/scrape",
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
    clock=None,
) -> str:
    """Walk tonight's due holdings. Returns done, capped, paused, or blocked."""
    if settings.photo_scrape_active:
        log.info("daily paused reason=photo-scrape")
        return "paused"
    if accepted_daily_browsers(settings.daily_browsers) != settings.daily_browsers:
        log.info("daily browsers requested=%s using=1", settings.daily_browsers)
    pace = DailyPace.from_settings(settings, now)
    due = due_urls(conn, today, portfolio, settings)
    clock = clock or (lambda: datetime.now(timezone.utc))
    began = now()
    done = 0
    log.info("daily start due=%s", len(due))
    for index, url in enumerate(due):
        if done and done % 50 == 0 and settings.daily_deadline_utc:
            elapsed = now() - began
            pace.gap = deadline_gap(
                pace.gap,
                pace.gap_min,
                len(due) - index,
                seconds_until(settings.daily_deadline_utc, clock()),
                elapsed / done,
            )
            log.info("daily pace gap=%.1f left=%s", pace.gap, len(due) - index)
        if settings.photo_scrape_active:
            return "paused"
        reason = scraper_block_reason(conn)
        if reason in {"daily-pages", "daily-mb"}:
            log.info("daily stop reason=%s", reason)
            return "capped"
        pages, _used = usage_today(conn)
        if settings.scraper_daily_pages - pages <= settings.interactive_reserve_pages():
            log.info("daily stop reason=interactive-reserve")
            return "capped"
        if reason:
            log.info("daily stop reason=%s", reason)
            return "blocked"
        pool = current_pool()
        lane = pool.lease("daily", conn, timeout=1) if pool is not None else None
        if pool is not None and lane is None:
            sleep(1)
            continue
        token = daily_lane_url.set(lane.settings.scraper_url) if lane is not None else None
        try:
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
        finally:
            if token is not None:
                daily_lane_url.reset(token)
            if lane is not None and pool is not None:
                pool.release_lease(lane)
        done += 1
        sleep(extra_sleep(jittered(pace.gap, settings.daily_gap_jitter), settings.scraper_page_gap_s))
    log.info("daily done due=%s read=%s", len(due), done)
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
