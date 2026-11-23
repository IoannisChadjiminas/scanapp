from app.db import connect, init_catalog
from app.routes.cards import search_sets
from app.set_eras import ERAS, RELEASE_DATES, refresh_set_eras, set_era
from test_card_search import _request


def test_code_date_and_table_rules():
    # A code names its era, before any date.
    assert set_era("en", "sv10", "2025-05-30") == ("scarlet_violet", "code")
    assert set_era("en", "mfb", "2023-09-29") == ("scarlet_violet", "date")
    assert set_era("ja", "S12a", "2022-12-02") == ("sword_shield", "code")
    assert set_era("ja", "SV-P", "2022-11-29") == ("scarlet_violet", "code")
    # Deck boxes whose M code is not Mega Evolution.
    assert set_era("ja", "MDB", None) == ("black_white", "table")
    assert set_era("ja", "MMBP", None) == ("xy", "table")
    # Sold before the era's first booster.
    assert set_era("ja", "SP", "2019-11-01") == ("sword_shield", "table")
    assert set_era("ja", "HXY", "2013-11-08") == ("xy", "table")
    # A researched date places a deck TCGdex has no date for.
    assert set_era("ja", "SEK", None) == ("sword_shield", "date")
    assert set_era("ja", "jr-guren-town-gym-deck", None) == ("original", "date")
    assert set_era("ja", "jr-dpt-gift-box-pikachu", None) == ("platinum", "date")
    # Nothing known.
    assert set_era("en", "PPS1", None) == ("other", "none")
    assert all(era in ERAS for era, _ in (set_era("ja", key[1], None) for key in RELEASE_DATES))


def test_refresh_stores_eras_and_keeps_manual_rows(tmp_path):
    conn = connect(tmp_path / "eras.sqlite")
    init_catalog(conn)
    for card_id, lang, set_id in [("a", "en", "sv10"), ("b", "ja", "SEK"), ("c", "ja", "MDB"), ("d", "en", "PPS1"), ("e", "ja", "SV9")]:
        conn.execute(
            """INSERT INTO cards(id, provider_id, name, set_id, set_name, collector_number, language, rarity, category, variants_json)
            VALUES (?, ?, 'Pikachu', ?, ?, '1', ?, 'Rare', 'Pokemon', '{}')""",
            (card_id, card_id, set_id, set_id, lang),
        )
    conn.execute(
        "INSERT INTO set_releases (language, set_id, release_date, fetched_at, era, era_source) VALUES ('ja', 'SV9', '2025-01-24', 'x', 'other', 'manual')"
    )
    conn.commit()
    assert refresh_set_eras(conn) == 4
    rows = {
        (row[0], row[1]): (row[2], row[3], row[4])
        for row in conn.execute("SELECT language, set_id, release_date, era, era_source FROM set_releases")
    }
    assert rows[("en", "sv10")] == (None, "scarlet_violet", "code")
    # The researched date is stored with the era.
    assert rows[("ja", "SEK")] == ("2020-12-04", "sword_shield", "date")
    assert rows[("ja", "MDB")] == ("2012-09-14", "black_white", "table")
    assert rows[("en", "PPS1")] == (None, "other", "none")
    # Set by hand: kept.
    assert rows[("ja", "SV9")] == ("2025-01-24", "other", "manual")
    # A second pass changes nothing.
    assert refresh_set_eras(conn) == 0
    # The set list sends the stored era.
    sets = {item["set_id"]: item for item in search_sets(_request(conn))}
    assert sets["SEK"]["era"] == "sword_shield"
    assert sets["SEK"]["release_date"] == "2020-12-04"
    conn.close()


def test_a_tcgdex_date_never_wipes_the_era(tmp_path):
    conn = connect(tmp_path / "keep.sqlite")
    init_catalog(conn)
    conn.execute(
        "INSERT INTO set_releases (language, set_id, release_date, fetched_at, era, era_source) VALUES ('en', 'sv10', NULL, 'x', 'scarlet_violet', 'code')"
    )
    conn.execute(
        """INSERT INTO set_releases (language, set_id, release_date, fetched_at) VALUES ('en', 'sv10', '2025-05-30', 'y')
        ON CONFLICT (language, set_id) DO UPDATE SET
          release_date = COALESCE(excluded.release_date, set_releases.release_date),
          fetched_at = excluded.fetched_at"""
    )
    row = conn.execute("SELECT release_date, era, era_source FROM set_releases").fetchone()
    assert tuple(row) == ("2025-05-30", "scarlet_violet", "code")
    conn.close()
