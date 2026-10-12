"""User portfolios live in PlanetScale database pokesingle-product.

The catalogue database stays read-only. This connection is the writable one.
Prices stay in the local snapshot table.
"""

from __future__ import annotations

import sqlite3
import time
from urllib.parse import urlsplit

_SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolio_products (
    session_id text NOT NULL,
    sample_key text NOT NULL,
    opened_at timestamptz NOT NULL,
    PRIMARY KEY (session_id, sample_key)
);
CREATE INDEX IF NOT EXISTS portfolio_products_opened_idx
    ON portfolio_products (opened_at);
"""


def connect_portfolio(url: str):
    """Open the portfolio database. The URL is never logged."""
    parts = urlsplit(url.strip())
    host = parts.hostname or ""
    if parts.scheme not in {"postgres", "postgresql"} or not host.endswith(".psdb.cloud"):
        raise ValueError("Portfolio database must be a PlanetScale Postgres URL")
    import certifi
    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(
        url.strip(),
        port=6432,
        sslmode="verify-full",
        sslrootcert=certifi.where(),
        connect_timeout=15,
        autocommit=False,
        prepare_threshold=None,
        application_name="scanapp-portfolio",
        row_factory=dict_row,
    )
    try:
        if not conn.pgconn.ssl_in_use:
            raise ValueError("Portfolio database TLS is required")
        for ddl in _SCHEMA.split(";"):
            if ddl.strip():
                conn.execute(ddl)
        writable = conn.execute(
            "SELECT has_table_privilege(current_user, 'portfolio_products', 'INSERT') AS ok"
        ).fetchone()
        if not writable or not writable["ok"]:
            raise ValueError("Portfolio database role cannot insert")
        conn.commit()
    except Exception:
        conn.close()
        raise
    return conn


def statement(conn, sql: str) -> str:
    if isinstance(conn, sqlite3.Connection):
        return sql
    return sql.replace("?", "%s")


def has_synced_at(conn) -> bool:
    """True once docs/sql/portfolio-synced-at.sql has been applied.

    Until then the night job keeps every holding, as before.
    """
    try:
        conn.execute(statement(conn, "SELECT synced_at FROM portfolio_products LIMIT 0"))
        return True
    except Exception:
        conn.rollback()
        return False


def portfolio_keys(conn, max_age_days: int = 0) -> list[str]:
    """Distinct product URLs, most recently opened first.

    With [max_age_days], holdings from an install that has not synced in that
    many days are left out. Needs the synced_at column.
    """
    where, params = "", ()
    if max_age_days > 0 and has_synced_at(conn):
        cutoff = time.gmtime(time.time() - max_age_days * 86400)
        where = "WHERE synced_at >= ?"
        params = (time.strftime("%Y-%m-%dT%H:%M:%SZ", cutoff),)
    rows = conn.execute(
        statement(
            conn,
            f"""
            SELECT sample_key, MAX(opened_at) AS opened
            FROM portfolio_products
            {where}
            GROUP BY sample_key
            ORDER BY opened DESC, sample_key
            """,
        ),
        params,
    ).fetchall()
    return [str(row["sample_key"]) for row in rows]
