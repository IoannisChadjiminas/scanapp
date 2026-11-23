from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.db import connect, init_catalog
from app.routes.cards import search_cards, search_sets
from app.schemas import Candidate, PlausiblePrinting
from app.set_titles import JA_SET_TITLES, card_set_view_title, ja_sets_titled, set_view_title


def _request(catalog):  # noqa: ANN001, ANN202
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(dbs=SimpleNamespace(catalog=catalog))))


def _catalog(tmp_path: Path):  # noqa: ANN202
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    rows = [
        ("ja:SV10-001", "クヌギダマ", "SV10", "ロケット団の栄光", "1", "ja"),
        ("ja:SV10-002", "ピカチュウ", "SV10", "ロケット団の栄光", "2", "ja"),
        ("ja:SV9-001", "ピカチュウ", "SV9", "バトルパートナーズ", "1", "ja"),
        ("sv10-1", "Team Rocket's Mewtwo ex", "sv10", "Destined Rivals", "1", "en"),
    ]
    for card_id, name, set_id, set_name, number, language in rows:
        conn.execute(
            "INSERT INTO cards (id, provider_id, name, set_id, set_name, collector_number, language) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (card_id, card_id, name, set_id, set_name, number, language),
        )
        conn.execute(
            "INSERT INTO cards_fts (name, set_name, collector_number, id) VALUES (?, ?, ?, ?)",
            (name, set_name, number, card_id),
        )
    conn.commit()
    return conn


def test_titles_cover_only_japanese_expansions() -> None:
    assert set_view_title("ja", "SV10") == "The Glory of Team Rocket"
    assert set_view_title("en", "SV10") is None
    assert set_view_title("ja", "S10D") is None
    assert card_set_view_title("ja:SV10-001") == "The Glory of Team Rocket"
    assert card_set_view_title("ja:M-P-001") == "M-P Promos"
    assert card_set_view_title("ja:S8a-P-001") == "25th Anniversary Edition"
    assert card_set_view_title("sv10-1") is None
    # Every title is English.
    assert all(title.isascii() or "é" in title for title in JA_SET_TITLES.values())


def test_set_list_and_cards_carry_the_english_title(tmp_path: Path) -> None:
    request = _request(_catalog(tmp_path))
    sets = {item["set_id"]: item for item in search_sets(request, language="ja")}
    assert sets["SV10"]["set_view_title"] == "The Glory of Team Rocket"
    # The catalogue's own name stays: matching reads it.
    assert sets["SV10"]["set_name"] == "ロケット団の栄光"
    card = search_cards(request, q="", language="ja", limit=5, offset=0).items[0]
    assert card.set_view_title in {"The Glory of Team Rocket", "Battle Partners"}
    english = search_cards(request, q="mewtwo", language="", limit=5, offset=0).items
    assert [c.set_view_title for c in english] == [None]


def test_scan_candidates_carry_the_english_title() -> None:
    candidate = Candidate(card_id="ja:SV10-001", name="クヌギダマ", set_name="ロケット団の栄光",
                          collector_number="001", image_url="", visual_score=1, combined_score=1, language="ja")
    assert candidate.set_view_title == "The Glory of Team Rocket"
    printing = PlausiblePrinting(card_id="ja:SV9-001", name="ピカチュウ", set_name="バトルパートナーズ",
                                 collector_number="001", language="ja", image_url="")
    assert printing.set_view_title == "Battle Partners"


def test_searching_an_english_title_finds_the_japanese_expansion(tmp_path: Path) -> None:
    request = _request(_catalog(tmp_path))
    ids = {c.id for c in search_cards(request, q="glory rocket", language="", limit=10, offset=0).items}
    assert ids == {"ja:SV10-001", "ja:SV10-002"}
    # Another word still narrows within it.
    assert ja_sets_titled(["glory", "pika"])[0] == ["SV10"]
    # English cards found by their own names are not lost.
    ids = {c.id for c in search_cards(request, q="team rocket", language="", limit=10, offset=0).items}
    assert "sv10-1" in ids and "ja:SV10-001" in ids
