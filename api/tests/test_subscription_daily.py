from datetime import datetime, timezone

from app import cardmarket_daily as daily
from app.cardmarket import sample_key
from app.cardmarket_budget import usage_today
from app.cardmarket_budget import QueueError, reserve_attempt
import pytest
from app.config import Settings
from app.db import connect, init_catalog

URL = 'https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Pikachu?language=1&minCondition=2'
REFRESH = {
    'tiers': [{'lessThanEur': 2, 'minimumAgeSeconds': 518400},
              {'lessThanEur': None, 'minimumAgeSeconds': 86400}],
    'unknownPriceMinimumAgeSeconds': 86400, 'maximumListingAgeDays': 7,
    'trendMovePercent': 10, 'dailyPageBudget': 5, 'dailyMegabyteBudget': 5,
    'interactiveReservePercent': 0,
    'dailyScheduleUtc': '02:30',
}


class Product:
    def __init__(self, eligible=True):
        self.allowed = eligible
        self.checks = 0
    def eligible(self, sample):
        assert sample == URL
        self.checks += 1
        return self.allowed
    def candidates(self, *, after=None, limit=100):
        return ([URL], None, REFRESH)


def test_subscriber_candidates_are_deduplicated_and_policy_driven():
    candidates, policy = daily._subscriber_candidates(Product())
    assert candidates == [URL]
    assert sample_key(candidates[0]) == candidates[0]
    assert daily._policy_tier_days(Settings(_env_file=None), 1, policy) == 6
    assert daily._policy_tier_days(Settings(_env_file=None), 10, policy) == 1


def test_next_daily_run_follows_backend_utc_schedule(monkeypatch):
    monkeypatch.setattr(daily, 'SubscriptionClient', lambda _: Product())
    assert daily.next_configured_run(Settings(_env_file=None), datetime(2026, 10, 29, 1, 30, tzinfo=timezone.utc)) == 3600
    assert daily.next_configured_run(Settings(_env_file=None), datetime(2026, 10, 29, 3, 30, tzinfo=timezone.utc)) == 23 * 3600


def test_daily_checks_current_eligibility_and_deduplicates_under_lease(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, data_dir=tmp_path, scraper_daily_pages=5,
                        scraper_daily_mb=5, scraper_gap_min_s=0, daily_gap_min_s=0,
                        daily_gap_max_s=0, daily_gap_jitter=0)
    conn = connect(settings.catalog_sqlite)
    init_catalog(conn)
    monkeypatch.setattr(daily, 'scraper_block_reason', lambda _: None)
    monkeypatch.setattr(daily, 'current_pool', lambda: None)
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    calls = []
    def scrape(url, _session):
        calls.append(url)
        return {'outcome': 'empty', 'url': url, 'bytes': 10}
    blocked = Product(False)
    assert daily.run_pass(conn, settings, scrape=scrape, sleep=lambda _: None, today=today,
                          queue=daily.WorkQueue([URL]), subscription_client=blocked, interactive_reserve=0) == 'done'
    assert calls == [] and usage_today(conn) == (0, 0)
    allowed = Product(True)
    assert daily.run_pass(conn, settings, scrape=scrape, sleep=lambda _: None, today=today,
                          queue=daily.WorkQueue([URL, URL]), subscription_client=allowed, interactive_reserve=0) == 'done'
    assert calls == [URL]
    assert allowed.checks >= 3
    assert conn.execute('SELECT COUNT(*) FROM paid_sample_lease').fetchone()[0] == 0
    conn.close()


def test_backend_budget_cannot_be_exceeded_by_legacy_local_limits(tmp_path):
    conn = connect(tmp_path / 'catalog.sqlite')
    init_catalog(conn)
    policy = Settings(_env_file=None, scraper_daily_pages=0, scraper_daily_mb=100)
    with pytest.raises(QueueError):
        reserve_attempt(conn, sample=URL, session_id='test', ip='', budget_settings=policy)
    assert usage_today(conn) == (0, 0)
    conn.close()
