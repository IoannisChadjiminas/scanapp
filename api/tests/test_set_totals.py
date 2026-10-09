"""The printed total after the slash on a card (35/108)."""

import httpx

from app.config import Settings
from app.db import connect, init_catalog
from app.recognition.pipeline import _preview_candidates
from app.set_totals import official_total, refresh_set_totals, set_total


def _catalog(tmp_path):
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    conn.execute(
        "INSERT INTO cards (id, provider_id, name, set_id, set_name, collector_number, language)"
        " VALUES ('en:sv3pt5-200', 'sv3pt5-200', 'Blastoise ex', 'sv3pt5', '151', '200', 'en')"
    )
    conn.commit()
    return conn


def test_official_total_prefers_the_printed_count():
    assert official_total({"cardCount": {"official": 165, "total": 207}}) == 165
    assert official_total({"cardCount": {"total": 30}}) == 30
    assert official_total({"cardCount": {"official": 0, "total": 0}}) is None
    assert official_total({}) is None


def test_refresh_stores_each_sets_total_and_scans_return_it(tmp_path, monkeypatch):
    conn = _catalog(tmp_path)
    sets = [{"id": "sv3pt5", "cardCount": {"official": 165, "total": 207}}, {"id": "bad"}]

    def fake_get(self, url, **kwargs):
        assert url.endswith("/en/sets")
        return httpx.Response(200, json=sets, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    assert refresh_set_totals(conn, Settings()) == 1
    assert set_total(conn, "en", "sv3pt5") == 165
    assert set_total(conn, "en", "bad") is None
    [preview] = _preview_candidates(conn, ["en:sv3pt5-200"])
    assert preview["set_total"] == 165 and preview["collector_number"] == "200"


def test_unknown_set_gives_none(tmp_path):
    assert set_total(_catalog(tmp_path), "ja", "nope") is None
