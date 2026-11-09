"""SET_TOTAL_ALIASES: Japanese half-set ids find their TCGdex total; known-wrong totals are corrected."""

from app.config import get_settings
from app.db import connect, init_catalog
from app.set_totals import JA_TOTAL_ALIASES, set_total


def _conn(tmp_path):
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    conn.executemany(
        "INSERT INTO set_totals (language, set_id, official_total, fetched_at) VALUES (?, ?, ?, 'x')",
        [("ja", "XY1b", 60), ("ja", "XY8b", 59), ("ja", "SM7a", 50), ("en", "XY1b", 999)],
    )
    conn.commit()
    return conn


def _flag(monkeypatch, on):
    monkeypatch.setenv("SET_TOTAL_ALIASES", "true" if on else "false")
    get_settings.cache_clear()


def test_flag_off_keeps_todays_answers(tmp_path, monkeypatch):
    _flag(monkeypatch, False)
    conn = _conn(tmp_path)
    assert set_total(conn, "ja", "XY1-By") is None
    assert set_total(conn, "ja", "SM7a") == 50
    get_settings.cache_clear()


def test_flag_on_finds_the_half_set_total_and_corrects_sm7a(tmp_path, monkeypatch):
    _flag(monkeypatch, True)
    conn = _conn(tmp_path)
    assert set_total(conn, "ja", "XY1-By") == 60
    assert set_total(conn, "ja", "XY8-Bb") == 59
    assert set_total(conn, "ja", "SM7a") == 60
    assert set_total(conn, "ja", "XY1b") == 60
    # Only Japanese ids are aliased, and an unknown set stays unknown.
    assert set_total(conn, "en", "XY1-By") is None
    assert set_total(conn, "ja", "XY9-Bz") is None
    get_settings.cache_clear()


def test_every_alias_names_a_half_of_the_same_set():
    for half, tcgdex in JA_TOTAL_ALIASES.items():
        assert half.split("-")[0] == tcgdex.rstrip("ab") or half[:2] == "L1" and tcgdex[:2] == "L1"
