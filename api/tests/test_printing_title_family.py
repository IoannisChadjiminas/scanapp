"""PRINTING_TITLE_FAMILY: a recovered row named in English joins its same-art Japanese twin's printing review.

The dev-half proof-panel photo dev-ja-modern-009 (Umbreon V S6a-047, footer read "047/06") showed
ブラッキーV S8b-100 first with S6a-047 nowhere: S6a-047 is a vectorless twin named "Umbreon V",
so the same-name family never found it.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from app.db import connect, init_catalog
from app.recognition.printing import ReferencePrintingIndex, assess_printings


def _catalog(tmp_path, rows):
    root = tmp_path / "reference-images"
    root.mkdir()
    rng = np.random.default_rng(7)
    arts = {}
    conn = connect(tmp_path / "catalog.sqlite")
    init_catalog(conn)
    for cid, name, title, language, art in rows:
        if art not in arts:
            arts[art] = Image.fromarray(rng.integers(0, 255, (320, 224, 3), dtype=np.uint8))
        path = root / f"{cid.replace(':', '_')}.png"
        arts[art].save(path)
        conn.execute("INSERT INTO cards (id,provider_id,name,set_id,set_name,collector_number,language,image_path,has_image,view_title) "
                     "VALUES (?,?,?,?,?,?,?,?,1,?)", (cid, cid, name, cid.split(':')[1].split('-')[0], cid, cid.rsplit('-', 1)[1],
                                                       language, str(path), title))
    return conn


ROWS = [("ja:S8b-100", "ブラッキーV", "Umbreon V", "ja", "umbreon"),
        ("ja:S6a-047", "Umbreon V", "Umbreon V", "ja", "umbreon"),           # same art, English-named twin
        ("ja:S6a-095", "Umbreon V", "Umbreon V", "ja", "umbreon-alt"),       # same title, other art
        ("en:swsh7-94", "Umbreon V", "Umbreon V", "en", "umbreon")]          # same art, other language

TOP = {"card_id": "ja:S8b-100", "name": "ブラッキーV", "view_title": "Umbreon V", "language": "ja",
       "set_name": "S8b", "collector_number": "100", "visual_score": .907, "combined_score": .82}


def test_title_family_offers_the_same_art_twin(tmp_path):
    conn = _catalog(tmp_path, ROWS)
    try:
        members, _ = ReferencePrintingIndex(tmp_path, by_title=True).family(conn, TOP)
        assert {r["id"] for r in members} == {"ja:S8b-100", "ja:S6a-047"}
        decision = assess_printings([TOP], family=members, hits=[], reference_incomplete=False,
                                    min_visual=.78, min_gap=.04, retake=False, title_family=True)
        assert decision.ambiguous
        assert {r["card_id"] for r in decision.members} == {"ja:S8b-100", "ja:S6a-047"}
        # the card shown first does not change
        assert decision.members[0]["card_id"] == "ja:S8b-100"
    finally:
        conn.close()


def test_flag_off_keeps_the_same_name_family(tmp_path):
    conn = _catalog(tmp_path, ROWS)
    try:
        members, _ = ReferencePrintingIndex(tmp_path).family(conn, TOP)
        assert {r["id"] for r in members} == {"ja:S8b-100"}
        twin = {"card_id": "ja:S6a-047", "name": "Umbreon V", "view_title": "Umbreon V", "language": "ja",
                "set_name": "S6a", "collector_number": "047"}
        decision = assess_printings([TOP], family=[TOP, twin], hits=[], reference_incomplete=False,
                                    min_visual=.78, min_gap=.04, retake=False)
        assert not decision.ambiguous
    finally:
        conn.close()


def test_same_title_other_artwork_or_language_never_joins(tmp_path):
    conn = _catalog(tmp_path, ROWS)
    try:
        members, _ = ReferencePrintingIndex(tmp_path, by_title=True).family(conn, TOP)
        ids = {r["id"] for r in members}
        assert "ja:S6a-095" not in ids      # shares the title, not the artwork
        assert "en:swsh7-94" not in ids     # shares the artwork, not the language
    finally:
        conn.close()


def test_other_title_is_not_a_member(tmp_path):
    other = {"card_id": "ja:S8b-099", "name": "エーフィV", "view_title": "Espeon V", "language": "ja",
             "set_name": "S8b", "collector_number": "099"}
    decision = assess_printings([TOP], family=[TOP, other], hits=[], reference_incomplete=False,
                                min_visual=.78, min_gap=.04, retake=False, title_family=True)
    assert not decision.ambiguous
    untitled = {**TOP, "view_title": None}
    blank = {**other, "name": "Umbreon V", "view_title": None}
    assert not assess_printings([untitled], family=[untitled, blank], hits=[], reference_incomplete=False,
                                min_visual=.78, min_gap=.04, retake=False, title_family=True).ambiguous


def test_title_member_is_marked_so_it_never_orders_the_shown_card(tmp_path):
    # Charizard upload 379234db: a recovered row named "Charizard" (CLL-003) joined the family
    # and the verified-sibling ordering showed it first instead of M6a-137. Title members are
    # marked and the pipeline leaves them out of every ordering rule.
    conn = _catalog(tmp_path, ROWS)
    try:
        members, _ = ReferencePrintingIndex(tmp_path, by_title=True).family(conn, TOP)
        decision = assess_printings([TOP], family=members, hits=[], reference_incomplete=False,
                                    min_visual=.78, min_gap=.04, retake=False, title_family=True)
        marks = {m["card_id"]: bool(m.get("title_member")) for m in decision.members}
        assert marks == {"ja:S8b-100": False, "ja:S6a-047": True}
    finally:
        conn.close()


def test_title_row_without_an_image_does_not_make_the_group_incomplete(tmp_path):
    # Moltres PMCG3-009 went from matched to uncertain: imageless "Moltres" rows found by title
    # marked its family incomplete.
    conn = _catalog(tmp_path, ROWS)
    try:
        conn.execute("INSERT INTO cards (id,provider_id,name,set_id,set_name,collector_number,language,image_path,has_image,view_title) "
                     "VALUES ('ja:jr-x-u01','x','Umbreon V','jr','jr','u01','ja','',0,'Umbreon V')")
        _, incomplete = ReferencePrintingIndex(tmp_path, by_title=True).family(conn, TOP)
        assert not incomplete
        conn.execute("INSERT INTO cards (id,provider_id,name,set_id,set_name,collector_number,language,image_path,has_image,view_title) "
                     "VALUES ('ja:jr-y-u02','y','ブラッキーV','jr','jr','u02','ja','',0,'Umbreon V')")
        _, incomplete = ReferencePrintingIndex(tmp_path, by_title=True).family(conn, TOP)
        assert incomplete      # a same-name row without an image still counts, as before
    finally:
        conn.close()
