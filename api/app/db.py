from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import Settings


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
            has_image INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_cards_name ON cards(name);
        CREATE INDEX IF NOT EXISTS idx_cards_set ON cards(set_id);
        CREATE INDEX IF NOT EXISTS idx_cards_number ON cards(collector_number);
        CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5(
            name, set_name, collector_number, id UNINDEXED
        );
        """
    )
    conn.commit()


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


class Databases:
    def __init__(self, settings: Settings) -> None:
        self.catalog = connect(settings.catalog_sqlite)
        self.results = connect(settings.results_sqlite)
        init_catalog(self.catalog)
        init_results(self.results)

    def close(self) -> None:
        self.catalog.close()
        self.results.close()
