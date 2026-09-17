from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import Settings
from app.schemas import Coverage, LanguageCoverage


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_catalog(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cards (
            id TEXT PRIMARY KEY,
            provider_id TEXT NOT NULL,
            name TEXT NOT NULL,
            set_id TEXT NOT NULL,
            set_name TEXT NOT NULL,
            collector_number TEXT NOT NULL,
            language TEXT NOT NULL DEFAULT 'en',
            category TEXT,
            rarity TEXT,
            illustrator TEXT,
            variants_json TEXT NOT NULL DEFAULT '{}',
            image_path TEXT,
            has_image INTEGER NOT NULL DEFAULT 0,
            cardmarket_id INTEGER,
            cardmarket_url TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name);
        CREATE INDEX IF NOT EXISTS idx_cards_set ON cards(set_id);
        CREATE INDEX IF NOT EXISTS idx_cards_number ON cards(collector_number);
        CREATE INDEX IF NOT EXISTS idx_cards_language ON cards(language);
        CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5(
            name, set_name, collector_number, id UNINDEXED
        );
        """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(cards)")}
    if "cardmarket_id" not in columns:
        conn.execute("ALTER TABLE cards ADD COLUMN cardmarket_id INTEGER")
    if "cardmarket_url" not in columns:
        conn.execute("ALTER TABLE cards ADD COLUMN cardmarket_url TEXT")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cardmarket_snapshots (
            url TEXT PRIMARY KEY,
            prices_json TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cardmarket_jobs (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            card_id TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cardmarket_jobs_status
            ON cardmarket_jobs(status, created_at);
        CREATE TABLE IF NOT EXISTS cardmarket_helper (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_seen TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS cardmarket_helper_tokens (
            helper_id TEXT PRIMARY KEY,
            token_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            revoked_at TEXT
        );
        CREATE TABLE IF NOT EXISTS cardmarket_helpers (
            helper_id TEXT PRIMARY KEY,
            last_seen TEXT NOT NULL,
            ready INTEGER NOT NULL DEFAULT 0,
            paused INTEGER NOT NULL DEFAULT 0,
            attention TEXT,
            last_success_at TEXT,
            last_failure_at TEXT,
            last_failure_reason TEXT,
            current_job_id TEXT
        );
        """
    )
    _add_columns(
        conn,
        "cardmarket_jobs",
        {
            "attempts": "INTEGER NOT NULL DEFAULT 0",
            "helper_id": "TEXT",
            "claim_token": "TEXT",
            "claim_expires_at": "TEXT",
            "next_attempt_at": "TEXT",
            "failure_reason": "TEXT",
            "filters_json": "TEXT NOT NULL DEFAULT '{}'",
            "product_identity": "TEXT",
            "submission_id": "TEXT",
            "observed_at": "TEXT",
        },
    )
    _add_columns(
        conn,
        "cardmarket_snapshots",
        {
            "observed_at": "TEXT",
            "parser_version": "TEXT",
            "sampled_offer_count": "INTEGER",
            "submission_id": "TEXT",
        },
    )
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_cardmarket_jobs_claim
            ON cardmarket_jobs(claim_token);
        CREATE INDEX IF NOT EXISTS idx_cardmarket_jobs_helper
            ON cardmarket_jobs(helper_id, status);
        CREATE INDEX IF NOT EXISTS idx_cardmarket_jobs_retry
            ON cardmarket_jobs(status, next_attempt_at, created_at);
        """
    )
    conn.commit()


def _add_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def init_results(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            last_seen TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS scans (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            preprocessing TEXT NOT NULL,
            model_revision TEXT,
            catalogue_version TEXT,
            ocr_version TEXT,
            ranking_version TEXT,
            threshold_config_json TEXT,
            ocr_json TEXT,
            visual_ranking_json TEXT,
            combined_ranking_json TEXT,
            timings_json TEXT,
            confirmed_card_id TEXT,
            rejected INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        );
        CREATE INDEX IF NOT EXISTS idx_scans_session ON scans(session_id, created_at);
        """
    )
    conn.commit()


def coverage(conn: sqlite3.Connection) -> tuple[int, int, int]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS cards,
            SUM(CASE WHEN has_image = 1 THEN 1 ELSE 0 END) AS indexed,
            SUM(CASE WHEN has_image = 0 THEN 1 ELSE 0 END) AS missing_images
        FROM cards
        """
    ).fetchone()
    cards = int(row["cards"] or 0)
    indexed = int(row["indexed"] or 0)
    missing = int(row["missing_images"] or 0)
    return cards, indexed, missing


def coverage_by_language(conn: sqlite3.Connection) -> list[dict[str, int | str]]:
    rows = conn.execute(
        """
        SELECT
            language,
            COUNT(*) AS cards,
            SUM(CASE WHEN has_image = 1 THEN 1 ELSE 0 END) AS indexed
        FROM cards
        GROUP BY language
        ORDER BY language
        """
    ).fetchall()
    return [
        {
            "language": str(row["language"] or "en"),
            "cards": int(row["cards"] or 0),
            "indexed": int(row["indexed"] or 0),
        }
        for row in rows
    ]


def coverage_payload(conn: sqlite3.Connection) -> Coverage:
    cards, indexed, missing = coverage(conn)
    return Coverage(
        cards=cards,
        indexed=indexed,
        missing_images=missing,
        languages=[LanguageCoverage.model_validate(item) for item in coverage_by_language(conn)],
    )


class Databases:
    def __init__(self, settings: Settings) -> None:
        self.catalog = connect(settings.catalog_sqlite)
        self.results = connect(settings.results_sqlite)
        init_catalog(self.catalog)
        init_results(self.results)
        from app.cardmarket import sync_cardmarket_links

        sync_cardmarket_links(settings.data_dir, self.catalog)

    def close(self) -> None:
        self.catalog.close()
        self.results.close()
