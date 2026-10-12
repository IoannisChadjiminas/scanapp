import sqlite3
import time

from app.cardmarket_daily import WorkQueue, accepted_daily_browsers, replace_portfolio
from app.portfolio_db import has_synced_at, portfolio_keys

URL = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Charizard-V1-BS4"
OTHER = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Charmeleon-V1-BS24"
PLAIN = """CREATE TABLE portfolio_products (
    session_id text NOT NULL, sample_key text NOT NULL, opened_at text NOT NULL,
    PRIMARY KEY (session_id, sample_key))"""
STAMPED = PLAIN.replace("opened_at text NOT NULL,", "opened_at text NOT NULL, synced_at text NOT NULL,")


def db(schema):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(schema)
    return conn


def test_one_lane_means_one_browser():
    assert accepted_daily_browsers(3, 1) == 1
    assert accepted_daily_browsers(3) == 1


def test_a_lane_stays_free_for_people():
    assert accepted_daily_browsers(5, 3) == 2
    assert accepted_daily_browsers(1, 4) == 1
    assert accepted_daily_browsers(2, 4) == 2


def test_queue_hands_each_product_out_once():
    queue = WorkQueue(["a", "b", "c"])
    assert queue.total == 3
    assert [queue.take(), queue.take()] == ["a", "b"]
    queue.put_back("b")
    assert queue.left() == 2
    assert [queue.take(), queue.take(), queue.take()] == ["b", "c", None]


def test_without_the_column_every_holding_is_kept():
    conn = db(PLAIN)
    assert not has_synced_at(conn)
    replace_portfolio(conn, "s1", [(URL, "2026-10-01T10:00:00Z")])
    assert portfolio_keys(conn, 30) == [URL]


def test_sync_time_is_stamped_and_old_installs_are_skipped():
    conn = db(STAMPED)
    assert has_synced_at(conn)
    replace_portfolio(conn, "fresh", [(URL, "2026-10-01T10:00:00Z")])
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 40 * 86400))
    conn.execute(
        "INSERT INTO portfolio_products VALUES ('stale', ?, '2026-09-01T10:00:00Z', ?)",
        (OTHER, old),
    )
    assert portfolio_keys(conn, 30) == [URL]
    assert set(portfolio_keys(conn, 0)) == {URL, OTHER}
