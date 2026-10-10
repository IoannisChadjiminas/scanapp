from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.db import connect, init_catalog
from app.routes.cards import search_cards


def _request(catalog):  # noqa: ANN001, ANN202
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(dbs=SimpleNamespace(catalog=catalog))))


def _catalog(tmp_path: Path):  # noqa: ANN202
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    for index in range(7):
        card_id = f"base-{index:03d}"
        conn.execute(
            """
            INSERT INTO cards (id, provider_id, name, set_id, set_name, collector_number, language)
            VALUES (?, ?, 'Pikachu', 'base', 'Base', ?, 'en')
            """,
            (card_id, card_id, str(index + 1)),
        )
        conn.execute(
            "INSERT INTO cards_fts (name, set_name, collector_number, id) VALUES ('Pikachu', 'Base', ?, ?)",
            (str(index + 1), card_id),
        )
    conn.execute(
        "INSERT INTO cards (id, provider_id, name, set_id, set_name, collector_number, language) "
        "VALUES ('jp-1', 'jp-1', 'ピカチュウ', 'jp', 'ジャパン', '1', 'ja')"
    )
    conn.commit()
    return conn


def _ids(response) -> list[str]:  # noqa: ANN001
    return [item.id for item in response.items]


def test_name_search_pages_without_repeats_or_gaps(tmp_path: Path) -> None:
    request = _request(_catalog(tmp_path))
    pages = [
        search_cards(request, q="pika", language="", limit=3, offset=offset)
        for offset in (0, 3, 6, 9)
    ]
    seen = [card for page in pages for card in _ids(page)]
    assert seen == [f"base-{index:03d}" for index in range(7)]
    assert [len(page.items) for page in pages] == [3, 3, 1, 0]
    assert {page.total for page in pages} == {7}


def test_cjk_and_empty_searches_page_too(tmp_path: Path) -> None:
    request = _request(_catalog(tmp_path))
    first = search_cards(request, q="", language="", limit=5, offset=0)
    rest = search_cards(request, q="", language="", limit=5, offset=5)
    assert len(set(_ids(first)) | set(_ids(rest))) == 8
    assert first.total == 8
    cjk = search_cards(request, q="ピカ", language="", limit=5, offset=1)
    assert cjk.items == [] and cjk.total == 1



def test_results_carry_the_stored_prices_a_scan_shows(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    catalog.execute(
        "INSERT INTO tcgdex_prices (card_id, cardmarket_json, tcgplayer_json, fetched_at)"
        " VALUES ('base-000', ?, NULL, '2026-10-01T00:00:00Z')",
        ('{"unit": "EUR", "low": 1.2, "trend": 3.45, "updated": "2026-10-01"}',),
    )
    catalog.commit()
    items = {item.id: item for item in search_cards(_request(catalog), q="pika", language="", limit=20, offset=0).items}
    priced = items["base-000"].cardmarket_prices
    assert [(price.label, price.amount, price.source) for price in priced] == [
        ("From", 1.2, "tcgdex"),
        ("Trend", 3.45, "tcgdex"),
    ]
    # A card nothing is stored for comes back without a price, not with an error.
    assert items["base-001"].cardmarket_prices == []
