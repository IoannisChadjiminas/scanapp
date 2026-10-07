import sqlite3

from app.cardmarket_daily import replace_portfolio

URL = "https://www.cardmarket.com/en/Pokemon/Products/Singles/Base-Set/Charizard"


class PostgresLikeConnection:
    """A psycopg connection: no executemany on the connection, only on its cursor."""

    def __init__(self):
        self.inner = sqlite3.connect(":memory:")
        self.inner.execute(
            "CREATE TABLE portfolio_products (session_id text, sample_key text, opened_at text)")

    def execute(self, sql, params=()):
        return self.inner.execute(sql.replace("%s", "?"), params)

    def cursor(self):
        outer = self

        class Cursor:
            def executemany(self, sql, rows):
                outer.inner.executemany(sql.replace("%s", "?"), rows)

            def close(self):
                pass

        return Cursor()

    def commit(self):
        self.inner.commit()


def test_replace_portfolio_works_on_a_connection_without_executemany():
    conn = PostgresLikeConnection()
    assert not hasattr(conn, "executemany")
    assert replace_portfolio(conn, "s1", [(URL, "2026-10-07T18:00:00")]) == 1
    assert replace_portfolio(conn, "s1", [(URL, "2026-10-07T18:05:00")]) == 1
    rows = conn.inner.execute("SELECT session_id, opened_at FROM portfolio_products").fetchall()
    assert rows == [("s1", "2026-10-07T18:05:00")]


def test_replace_portfolio_still_works_on_sqlite():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE portfolio_products (session_id text, sample_key text, opened_at text)")
    assert replace_portfolio(conn, "s1", [(URL, "2026-10-07T18:00:00"), (URL, "x")]) == 1
