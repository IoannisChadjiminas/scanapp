from datetime import datetime, timezone

from app import cardmarket_daily as daily
from app.cardmarket import sample_key, write_snapshot
from app.cardmarket_budget import reserve_attempt, usage_today
from app.cardmarket_queue import claim_proxy_job, enqueue_job, schedule_scan_parallel_read
from app.cardmarket_scraper import ScraperWorker
from app.config import Settings, get_settings
from app.db import connect, init_catalog
from app.paid_refresh_requests import attach, register

URL = 'https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Pikachu?language=1&minCondition=2'
OFFERS = [{'label': 'NM · English', 'amount': 20.0, 'currency': 'EUR'}]


class Product:
    def __init__(self):
        self.calls = 0
    def authorize_price(self, *_):
        self.calls += 1
        return False
    def price_budget(self):
        return (50, 50)


def _worker(monkeypatch, tmp_path, product):
    settings = get_settings()
    monkeypatch.setattr(settings, 'product_api_paid_gate_ready', True)
    monkeypatch.setattr('app.cardmarket_scraper.SubscriptionClient', lambda _s: product)
    conn = connect(tmp_path / 'catalog.sqlite')
    init_catalog(conn)
    worker = ScraperWorker(settings)
    worker._scrape = lambda url: (_ for _ in ()).throw(AssertionError('must not scrape'))
    return conn, worker


def test_fresh_cache_under_the_gate_spends_nothing_and_skips_the_product_api(tmp_path, monkeypatch):
    product = Product()
    conn, worker = _worker(monkeypatch, tmp_path, product)
    write_snapshot(conn, URL, OFFERS)
    enqueue_job(conn, URL, tier='proxy')
    worker._handle(conn, claim_proxy_job(conn))
    assert product.calls == 0 and usage_today(conn) == (0, 0)
    assert conn.execute('SELECT status FROM cardmarket_jobs').fetchone()[0] == 'done'


def test_job_without_a_permit_fails_instead_of_spinning(tmp_path, monkeypatch):
    product = Product()
    conn, worker = _worker(monkeypatch, tmp_path, product)
    enqueue_job(conn, URL, tier='proxy', source='scan-parallel')
    worker._handle(conn, claim_proxy_job(conn))
    row = conn.execute('SELECT status, failure_reason FROM cardmarket_jobs').fetchone()
    assert (row['status'], row['failure_reason']) == ('failed', 'permit-missing')
    assert usage_today(conn) == (0, 0)


def test_lapsed_subscription_retries_are_bounded(tmp_path, monkeypatch):
    product = Product()
    conn, worker = _worker(monkeypatch, tmp_path, product)
    job_id = enqueue_job(conn, URL, tier='proxy')
    register(conn, 'req-1', '7', sample_key(URL))
    attach(conn, 'req-1', job_id)
    for _ in range(5):
        conn.execute("UPDATE cardmarket_jobs SET next_attempt_at='2020-01-01T00:00:00Z' WHERE status='pending'")
        conn.commit()
        job = claim_proxy_job(conn)
        if job is None:
            break
        worker._handle(conn, job)
    assert conn.execute('SELECT status FROM cardmarket_jobs').fetchone()[0] == 'failed'
    assert usage_today(conn) == (0, 0)


def test_scan_owned_reads_are_not_queued_under_the_gate(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, 'scan_price_server_read', 'parallel')
    monkeypatch.setattr(settings, 'scan_price_server_read_daily_pages', 10)
    monkeypatch.setattr(settings, 'product_api_paid_gate_ready', True)
    conn = connect(tmp_path / 'catalog.sqlite')
    init_catalog(conn)
    assert schedule_scan_parallel_read(conn, status='matched', url=URL) is None
    assert conn.execute('SELECT COUNT(*) FROM cardmarket_jobs').fetchone()[0] == 0


class Eligible:
    def eligible(self, _sample):
        return True


def test_daily_skips_a_product_being_read_elsewhere_and_continues(tmp_path, monkeypatch):
    other = URL.replace('Pikachu', 'Raichu')
    settings = Settings(_env_file=None, data_dir=tmp_path, scraper_daily_pages=5, scraper_daily_mb=5,
                        scraper_gap_min_s=0, daily_gap_min_s=0, daily_gap_max_s=0, daily_gap_jitter=0)
    conn = connect(settings.catalog_sqlite)
    init_catalog(conn)
    monkeypatch.setattr(daily, 'scraper_block_reason', lambda _: None)
    monkeypatch.setattr(daily, 'current_pool', lambda: None)
    reserve_attempt(conn, sample=URL, session_id='phone', ip='', budget_settings=settings)
    calls = []
    sleeps = []
    status = daily.run_pass(conn, settings, scrape=lambda url, _s: (calls.append(url), {'outcome': 'empty', 'url': url, 'bytes': 1})[1],
                            sleep=sleeps.append, today=datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                            queue=daily.WorkQueue([URL, other]), subscription_client=Eligible(), interactive_reserve=0)
    assert status == 'done' and calls == [other]



def test_daily_does_not_pace_products_that_were_never_read(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, data_dir=tmp_path, scraper_daily_pages=5, scraper_daily_mb=5,
                        daily_gap_min_s=30, daily_gap_max_s=30, daily_gap_jitter=0)
    conn = connect(settings.catalog_sqlite)
    init_catalog(conn)
    monkeypatch.setattr(daily, 'scraper_block_reason', lambda _: None)
    monkeypatch.setattr(daily, 'current_pool', lambda: None)
    class Lapsed:
        def eligible(self, _sample): return False
    sleeps = []
    daily.run_pass(conn, settings, scrape=lambda *_: (_ for _ in ()).throw(AssertionError()),
                   sleep=sleeps.append, today=datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                   queue=daily.WorkQueue([URL]), subscription_client=Lapsed(), interactive_reserve=0)
    assert sleeps == [] and usage_today(conn) == (0, 0)
