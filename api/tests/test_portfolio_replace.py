import sqlite3

import pytest

from app.cardmarket_daily import replace_portfolio

URL = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Charizard-V1-BS4"
OTHER = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Charmeleon-V1-BS24"
SCHEMA = """CREATE TABLE portfolio_products (
    session_id text NOT NULL, sample_key text NOT NULL, opened_at text NOT NULL,
    PRIMARY KEY (session_id, sample_key))"""


class PostgresLike:
    """Like psycopg: %s placeholders and no executemany on the connection."""

    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute(SCHEMA)
        self.db.commit()

    def execute(self, sql, params=()):
        return self.db.execute(sql.replace("%s", "?"), params)

    def commit(self):
        self.db.commit()

    def rollback(self):
        self.db.rollback()


def rows(db):
    return db.execute(
        "SELECT session_id, opened_at FROM portfolio_products ORDER BY session_id, opened_at").fetchall()


def test_replace_works_on_a_connection_without_executemany():
    conn = PostgresLike()
    assert not hasattr(conn, "executemany")
    assert replace_portfolio(conn, "s1", [(URL, "2026-10-01T10:00:00Z"), (OTHER, "2026-10-02T10:00:00Z")]) == 2
    assert replace_portfolio(conn, "s2", [(URL, "2026-10-03T10:00:00Z")]) == 1
    assert replace_portfolio(conn, "s1", [(URL, "2026-10-04T10:00:00Z"), (URL, "2026-10-05T10:00:00Z")]) == 1
    assert rows(conn.db) == [("s1", "2026-10-04T10:00:00Z"), ("s2", "2026-10-03T10:00:00Z")]
    assert replace_portfolio(conn, "s1", []) == 0
    assert rows(conn.db) == [("s2", "2026-10-03T10:00:00Z")]


def test_replace_still_works_on_sqlite():
    db = sqlite3.connect(":memory:")
    db.execute(SCHEMA)
    assert replace_portfolio(db, "s1", [(URL, "2026-10-01T10:00:00Z")]) == 1
    assert rows(db) == [("s1", "2026-10-01T10:00:00Z")]


def test_failed_insert_keeps_the_previous_holdings():
    conn = PostgresLike()
    replace_portfolio(conn, "s1", [(URL, "2026-10-01T10:00:00Z")])
    run = conn.execute

    def failing(sql, params=()):
        if sql.lstrip().startswith("INSERT"):
            raise RuntimeError("insert failed")
        return run(sql, params)

    conn.execute = failing
    with pytest.raises(RuntimeError):
        replace_portfolio(conn, "s1", [(OTHER, "2026-10-02T10:00:00Z")])
    assert rows(conn.db) == [("s1", "2026-10-01T10:00:00Z")]


def test_many_holdings_are_inserted_in_chunks():
    conn = PostgresLike()
    products = [(f"{URL}-{n}", "2026-10-01T10:00:00Z") for n in range(500)]
    assert replace_portfolio(conn, "s1", products) == 500
    assert len(rows(conn.db)) == 500
