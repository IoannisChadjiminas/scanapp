"""Search lists the newest expansions first."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import httpx

from app.config import Settings
from app.db import connect, init_catalog
from app.routes.cards import search_cards
from app.set_totals import refresh_set_releases

_SETS = {
    "base1": ("Base", "1999-01-09"),
    "sv03": ("Obsidian Flames", "2023-08-11"),
    "swsh9": ("Brilliant Stars", "2022-02-25"),
    "promo": ("Promos", None),
}


def _catalog(tmp_path: Path):
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    for set_id, (set_name, _) in _SETS.items():
        for number in ("10", "2"):
            card_id = f"en:{set_id}-{number}"
            conn.execute(
                "INSERT INTO cards (id, provider_id, name, set_id, set_name, collector_number, language)"
                " VALUES (?, ?, 'Charizard', ?, ?, ?, 'en')",
                (card_id, card_id, set_id, set_name, number),
            )
            conn.execute(
                "INSERT INTO cards_fts (name, set_name, collector_number, id) VALUES ('Charizard', ?, ?, ?)",
                (set_name, number, card_id),
            )
    conn.commit()
    return conn


def _fake_tcgdex(monkeypatch, asked: list[str]) -> None:
    def fake_get(self, url, **kwargs):
        set_id = url.rsplit("/", 1)[-1]
        asked.append(set_id)
        request = httpx.Request("GET", url)
        if set_id not in _SETS:
            return httpx.Response(404, request=request)
        name, date = _SETS[set_id]
        body = {"id": set_id, "name": name, **({"releaseDate": date} if date else {})}
        return httpx.Response(200, json=body, request=request)

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    monkeypatch.setattr("app.set_totals.sleep", lambda _: None)


def _request(catalog):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(dbs=SimpleNamespace(catalog=catalog))))


def test_dates_are_asked_once_per_set(tmp_path: Path, monkeypatch) -> None:
    conn = _catalog(tmp_path)
    asked: list[str] = []
    _fake_tcgdex(monkeypatch, asked)
    assert refresh_set_releases(conn, Settings()) == 3
    assert sorted(asked) == sorted(_SETS)
    # Known dates are not asked again; a set without one waits a week.
    asked.clear()
    assert refresh_set_releases(conn, Settings()) == 0
    assert asked == []


def test_search_lists_the_newest_expansion_first(tmp_path: Path, monkeypatch) -> None:
    conn = _catalog(tmp_path)
    _fake_tcgdex(monkeypatch, [])
    refresh_set_releases(conn, Settings())
    expected = [
        f"en:{set_id}-{number}" for set_id in ("sv03", "swsh9", "base1", "promo") for number in ("2", "10")
    ]
    request = _request(conn)
    assert [item.id for item in search_cards(request, q="chari", language="", limit=20, offset=0).items] == expected
    assert [item.id for item in search_cards(request, q="", language="", limit=20, offset=0).items] == expected


def test_search_works_before_any_date_is_known(tmp_path: Path) -> None:
    request = _request(_catalog(tmp_path))
    names = [item.set_name for item in search_cards(request, q="chari", language="", limit=20, offset=0).items]
    assert names[:2] == ["Base", "Base"]
