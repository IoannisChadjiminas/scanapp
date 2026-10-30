"""Once-a-day price refresh for products someone holds.

The job posts to the existing scraper. It does not open a browser itself.
"""

from __future__ import annotations

import logging
import math
import random
import threading
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
    release_attempt,
    reserve_attempt,
    scraper_block_reason,
    usage_today,
)
from app.cardmarket_queue import header_prices, rows_to_prices
from app.config import Settings, get_settings
from app.db import connect
from app.price_sources import market_trend, parse_tiers, trend_for_url
from app.portfolio_db import has_synced_at, portfolio_keys, statement
from app.paid_sample_lease import acquire as acquire_paid_lease, release as release_paid_lease
from app.subscription_client import SubscriptionClient, SubscriptionUnavailable

log = logging.getLogger("cardmarket.daily")
daily_lane_url: ContextVar[str] = ContextVar("daily_lane_url", default="")

DAILY_PARSER = "daily-offers-v1"


def should_schedule(settings: Settings) -> bool:
    """The night job starts only when both switches are on."""
    return bool(settings.daily_prices_enabled and settings.scraper_enabled)


def accepted_daily_browsers(requested: int, lanes: int = 1) -> int:
    """Held Chromes the night may use. One lane always stays free for people.

    With one scraper lane the night uses it. With more, it may take all but one,
    each with its own exit IP.
    """
    if lanes < 2:
        return 1
    return max(1, min(int(requested), lanes - 1))


class WorkQueue:
    """The night's URLs, shared by every worker so no product is read twice."""

    def __init__(self, items: list[str]) -> None:
        self._items = list(items)
        self._lock = threading.Lock()
        self.total = len(self._items)

    def take(self) -> str | None:
        with self._lock:
            return self._items.pop(0) if self._items else None

    def put_back(self, item: str) -> None:
        with self._lock:
            self._items.insert(0, item)

    def left(self) -> int:
        with self._lock:
            return len(self._items)


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


def replace_portfolio(conn, session_id: str, products: list[tuple[str, str]], *, lock_owner: bool = False) -> int:
    """Replace one session's holdings. Each item is a sample key and when it was opened."""
    kept: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw, opened in products:
        key = sample_key(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        kept.append((key, opened))
    stamped = has_synced_at(conn)
    synced = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        if lock_owner:
            # Service requests use independent connections. Lock even an empty
            # owner so two first-time replacements cannot merge their snapshots.
            import sqlite3

            if isinstance(conn, sqlite3.Connection):
                conn.execute("BEGIN IMMEDIATE")
            else:
                conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (session_id,),
                )
        conn.execute(
            statement(conn, "DELETE FROM portfolio_products WHERE session_id = ?"),
            (session_id,),
        )
        # A psycopg connection has no executemany, so insert in plain
        # multi-row statements that every connection type can run.
        for start in range(0, len(kept), 300):
            chunk = kept[start:start + 300]
            if stamped:
                conn.execute(
                    statement(
                        conn,
                        "INSERT INTO portfolio_products "
                        "(session_id, sample_key, opened_at, synced_at) VALUES "
                        + ", ".join("(?, ?, ?, ?)" for _ in chunk),
                    ),
                    [value for key, opened in chunk for value in (session_id, key, opened, synced)],
                )
                continue
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
    candidates: list[str] | None = None,
    refresh: dict | None = None,
) -> list[str]:
    """Holdings whose last listing read is older than their value tier.

    Order: cards about to pass the listing age limit, cards whose trend moved,
    dearer cards, then the rest. Each group is shuffled.
    """
    settings = settings or get_settings()
    rng = rng or random.Random()
    day = date.fromisoformat(today)
    max_age = max(1, int((refresh or {}).get('maximumListingAgeDays', settings.cardmarket_listing_max_age_days)))
    groups: list[list[str]] = [[], [], [], []]
    keys = candidates if candidates is not None else portfolio_keys(portfolio or conn, settings.daily_install_max_age_days)
    for key in keys:
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
        elif trend_moved(trend, _listing_trend(record), (refresh or {}).get('trendMovePercent', settings.daily_move_pct)):
            groups[1].append(key)
        elif age >= _policy_tier_days(settings, trend, refresh):
            groups[2 if trend is None or trend >= 20 else 3].append(key)
    pending: list[str] = []
    for group in groups:
        rng.shuffle(group)
        pending.extend(group)
    return pending


def _policy_tier_days(settings: Settings, trend: float | None, refresh: dict | None) -> int:
    if refresh is None:
        return tier_days(settings, trend)
    if trend is None or trend <= 0:
        seconds = refresh['unknownPriceMinimumAgeSeconds']
    else:
        seconds = next(tier['minimumAgeSeconds'] for tier in refresh['tiers']
                       if tier['lessThanEur'] is None or trend < tier['lessThanEur'])
    return max(1, math.ceil(seconds / 86400))


class PaidReadSkipped(Exception):
    pass


def _protected_daily_load(conn, settings: Settings, client: SubscriptionClient, today: str,
                          url: str, pace: DailyPace, reservation: str, scrape, started: float) -> dict:
    if not client.eligible(url):
        raise PaidReadSkipped()
    token = None
    try:
        token = acquire_paid_lease(conn, url, 'daily', int(settings.scraper_attempt_seconds) + 90)
        if token is None or not client.eligible(url):
            raise PaidReadSkipped()
        record = snapshot_record(conn, url)
        if str((record or {}).get('fetched_at') or '').startswith(today):
            raise PaidReadSkipped()
        return _load(conn, url, pace, reservation, scrape, started)
    finally:
        if token is not None:
            release_paid_lease(conn, url, token)


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


def next_configured_run(settings: Settings, now: datetime) -> float:
    """Read the current published UTC schedule from the product API."""
    _, _, refresh = SubscriptionClient(settings).candidates(limit=1)
    schedule = refresh.get('dailyScheduleUtc')
    if (not isinstance(schedule, str) or len(schedule) != 5 or schedule[2] != ':' or
            not schedule[:2].isascii() or not schedule[:2].isdigit() or
            not schedule[3:].isascii() or not schedule[3:].isdigit() or
            int(schedule[:2]) > 23 or int(schedule[3:]) > 59):
        raise SubscriptionUnavailable('invalid daily schedule')
    return max(1.0, seconds_until(schedule, now))


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
    queue: WorkQueue | None = None,
    subscription_client: SubscriptionClient | None = None,
    interactive_reserve: int | None = None,
) -> str:
    """Walk tonight's due holdings. Returns done, capped, paused, or blocked.

    Several workers can share one [queue]; each has its own pace and exit IP.
    """
    if settings.photo_scrape_active:
        log.info("daily paused reason=photo-scrape")
        return "paused"
    pace = DailyPace.from_settings(settings, now)
    if queue is None:
        queue = WorkQueue(due_urls(conn, today, portfolio, settings))
        log.info("daily start due=%s", queue.total)
    clock = clock or (lambda: datetime.now(timezone.utc))
    began = now()
    done = 0
    misses = 0
    while (url := queue.take()) is not None:
        if done and done % 50 == 0 and settings.daily_deadline_utc:
            elapsed = now() - began
            pace.gap = deadline_gap(
                pace.gap,
                pace.gap_min,
                queue.left() + 1,
                seconds_until(settings.daily_deadline_utc, clock()),
                elapsed / done,
            )
            log.info("daily pace gap=%.1f left=%s", pace.gap, queue.left() + 1)
        if settings.photo_scrape_active:
            return "paused"
        reason = scraper_block_reason(conn)
        if reason in {"daily-pages", "daily-mb"}:
            log.info("daily stop reason=%s", reason)
            return "capped"
        pages, _used = usage_today(conn)
        reserve_pages = settings.interactive_reserve_pages() if interactive_reserve is None else interactive_reserve
        if settings.scraper_daily_pages - pages <= reserve_pages:
            log.info("daily stop reason=interactive-reserve")
            return "capped"
        if reason:
            log.info("daily stop reason=%s", reason)
            return "blocked"
        pool = current_pool()
        lane = pool.lease("daily", conn, timeout=1) if pool is not None else None
        if pool is not None and lane is None:
            # Every lane is busy or resting. Keep the product for the next try.
            queue.put_back(url)
            misses += 1
            if misses >= 60:
                log.info("daily stop reason=no-free-lane")
                return "blocked"
            sleep(1)
            continue
        misses = 0
        token = daily_lane_url.set(lane.settings.scraper_url) if lane is not None else None
        try:
            try:
                reservation = reserve_attempt(conn, sample=url, session_id=pace.session_id, ip="daily", budget_settings=settings)
            except QueueError as exc:
                log.info("daily stop reason=budget detail=%s", exc.detail)
                return "capped"
            started = time.monotonic()
            resumed = False
            while True:
                try:
                    load = lambda res, start: (_protected_daily_load(conn, settings, subscription_client, today, url, pace, res, scrape, start)
                        if subscription_client is not None else _load(conn, url, pace, res, scrape, start))
                    result = load(reservation, started)
                    if str(result.get("outcome") or "") == "challenge_unsolved":
                        try:
                            reservation = reserve_attempt(
                                conn, sample=url, session_id=pace.session_id, ip="daily", budget_settings=settings
                            )
                        except QueueError:
                            return "capped"
                        result = load(reservation, time.monotonic())
                    break
                except PaidReadSkipped:
                    release_attempt(conn, reservation, 'subscription-or-cache')
                    break
                except SubscriptionUnavailable:
                    release_attempt(conn, reservation, 'subscription-unavailable')
                    return 'blocked'
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
                            conn, sample=url, session_id=pace.session_id, ip="daily", budget_settings=settings
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
    log.info("daily worker done read=%s", done)
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


def _combine(statuses: list[str]) -> str:
    for status in ("capped", "blocked", "paused"):
        if status in statuses:
            return status
    return "done"


def _subscriber_candidates(client: SubscriptionClient) -> tuple[list[str], dict]:
    items: list[str] = []
    seen: set[str] = set()
    cursors: set[str] = set()
    cursor = None
    refresh = None
    for _ in range(400):
        page, next_cursor, policy = client.candidates(after=cursor, limit=250)
        if refresh is not None and policy != refresh:
            raise SubscriptionUnavailable('price policy changed during pagination')
        refresh = policy
        for item in page:
            if sample_key(item) != item:
                raise SubscriptionUnavailable('invalid listing candidate')
            if item not in seen:
                seen.add(item)
                items.append(item)
        if next_cursor is None:
            break
        if next_cursor in cursors:
            raise SubscriptionUnavailable('repeated listing cursor')
        cursors.add(next_cursor)
        cursor = next_cursor
    else:
        raise SubscriptionUnavailable('too many listing candidates')
    if refresh is None:
        raise SubscriptionUnavailable('missing price policy')
    try:
        tiers = refresh['tiers']
        if (not isinstance(tiers, list) or not tiers or tiers[-1]['lessThanEur'] is not None or
                any(not isinstance(t['minimumAgeSeconds'], int) or t['minimumAgeSeconds'] < 1 for t in tiers) or
                any(not isinstance(refresh[k], int) or refresh[k] < 0 for k in
                    ('dailyPageBudget', 'dailyMegabyteBudget', 'interactiveReservePercent',
                     'maximumListingAgeDays', 'unknownPriceMinimumAgeSeconds')) or
                refresh['interactiveReservePercent'] > 100 or
                not isinstance(refresh['trendMovePercent'], (int, float))):
            raise ValueError('invalid policy')
    except (KeyError, TypeError, ValueError) as exc:
        raise SubscriptionUnavailable('invalid price policy') from exc
    return items, refresh


def run_once(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if not should_schedule(settings):
        return "disabled"
    conn = connect(settings.catalog_sqlite)
    portfolio = None if settings.product_api_paid_gate_ready else _portfolio_conn(settings)
    try:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        scrape = lambda url, session_id: scrape_product(settings, url, session_id)  # noqa: E731
        client = None
        reserve_pages = None
        queue = None
        if settings.product_api_paid_gate_ready:
            try:
                client = SubscriptionClient(settings)
                candidates, refresh = _subscriber_candidates(client)
                settings = settings.model_copy(update={'scraper_daily_pages': refresh['dailyPageBudget'],
                                                       'scraper_daily_mb': refresh['dailyMegabyteBudget']})
                reserve_pages = math.ceil(refresh['dailyPageBudget'] * refresh['interactiveReservePercent'] / 100)
                queue = WorkQueue(due_urls(conn, today, settings=settings, candidates=candidates, refresh=refresh))
            except SubscriptionUnavailable:
                log.info('daily stopped reason=subscription-unavailable')
                return 'blocked'
        workers = accepted_daily_browsers(settings.daily_browsers, len(settings.lane_urls))
        if workers != settings.daily_browsers:
            log.info("daily browsers requested=%s using=%s", settings.daily_browsers, workers)
        if workers == 1:
            return run_pass(
                conn, settings, scrape=scrape, sleep=time.sleep, today=today, portfolio=portfolio,
                queue=queue, subscription_client=client, interactive_reserve=reserve_pages,
            )
        queue = queue or WorkQueue(due_urls(conn, today, portfolio, settings))
        log.info("daily start due=%s workers=%s", queue.total, workers)
        statuses: list[str] = []

        def work() -> None:
            own = connect(settings.catalog_sqlite)
            try:
                statuses.append(
                    run_pass(
                        own, settings, scrape=scrape, sleep=time.sleep, today=today, queue=queue,
                        subscription_client=client, interactive_reserve=reserve_pages,
                    )
                )
            except Exception as exc:  # one worker failing must not stop the others
                log.info("daily worker failed error=%s", type(exc).__name__)
                statuses.append("blocked")
            finally:
                own.close()

        threads = [threading.Thread(target=work, name=f"daily-{n}") for n in range(workers)]
        for index, thread in enumerate(threads):
            thread.start()
            if index + 1 < len(threads):
                time.sleep(random.uniform(5, 20))  # do not open every window at once
        for thread in threads:
            thread.join()
        log.info("daily done due=%s left=%s", queue.total, queue.left())
        return _combine(statuses)
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
