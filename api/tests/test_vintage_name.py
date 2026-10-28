import io
import json
import sqlite3
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from app.config import Settings
from app.db import connect, init_catalog, init_results
from app.recognition.ocr import OcrHit, OcrResult
from app.recognition.pipeline import recognize_bytes
from app.recognition.vintage_name import vintage_name_choices

CARDS = [
    # id, name, set_id, collector_number
    ("ja:PMCG1-021", "リザードン", "PMCG1", "021"),
    ("ja:PMCG4-004", "わるいリザードン", "PMCG4", "004"),
    ("ja:CP6-011", "Charizard", "CP6", "011"),
    ("ja:S8a-P-001", "リザードン", "S8a-P", "001"),
    ("ja:M6a-137", "メガリザードンXex", "M6a", "137"),
]


def _catalog():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE cards (id, name, set_id, language, printed_collector_number)")
    conn.executemany("INSERT INTO cards VALUES (?, ?, ?, 'ja', NULL)", [(c[0], c[1], c[2]) for c in CARDS])
    return conn


def _choices(hits, numbers=(), languages=("ja",), exclude=frozenset()):
    return vintage_name_choices(_catalog(), hits=list(hits), numbers=list(numbers),
                                languages=languages, exclude=set(exclude))


def test_a_confident_name_offers_only_the_unnumbered_card_of_that_exact_name():
    # Not the anniversary reprint (numbered), not Dark Charizard (another name).
    assert _choices([OcrHit("リザードン", .9995, "name")]) == (["ja:PMCG1-021"], "choices")


@pytest.mark.parametrize("hits,numbers,languages,reason", [
    ([OcrHit("リザードン", .98, "name")], [], ("ja",), "no_confident_name"),
    ([OcrHit("リザードン", .9995, "holder")], [], ("ja",), "no_confident_name"),
    ([OcrHit("リザードン", .9995, "name")], [OcrHit("001/025", .99, "collector")], ("ja",), "printed_fraction"),
    ([OcrHit("リザードン", .9995, "name")], [], ("en",), "not_japanese"),
    ([OcrHit("ナッシー", .9995, "name")], [], ("ja",), "no_unnumbered_card"),
])
def test_no_choices_without_the_evidence(hits, numbers, languages, reason):
    assert _choices(hits, numbers, languages) == ([], reason)


def test_a_name_bare_number_read_is_not_a_printed_fraction():
    # "No.006" is the Pokedex number, not a collector fraction.
    assert _choices([OcrHit("リザードン", .9995, "name")], [OcrHit("006", .99, "collector")])[0] == ["ja:PMCG1-021"]


def test_cards_already_offered_are_not_repeated():
    assert _choices([OcrHit("リザードン", .9995, "name")], exclude={"ja:PMCG1-021"}) == ([], "already_offered")


def test_a_name_with_too_many_unnumbered_cards_offers_none():
    conn = _catalog()
    conn.executemany("INSERT INTO cards VALUES (?, 'ピカチュウ', ?, 'ja', NULL)",
                     [(f"ja:{s}-0{i}", s) for i, s in enumerate(("PMCG1", "PMCG2", "neo1", "neo2"))])
    assert vintage_name_choices(conn, hits=[OcrHit("ピカチュウ", .9995, "name")], numbers=[],
                                languages=("ja",)) == ([], "too_many_cards")


def _scan(tmp_path, on):
    catalog, results = connect(tmp_path/"catalog.sqlite"), connect(tmp_path/"results.sqlite")
    init_catalog(catalog)
    init_results(results)
    results.execute("INSERT INTO sessions VALUES ('test','test','test')")
    try:
        for cid, name, set_id, number in CARDS:
            catalog.execute("INSERT INTO cards(id,provider_id,name,set_id,set_name,collector_number,language) "
                            "VALUES(?,?,?,?,?,?,?)", (cid, cid, name, set_id, set_id, number, "ja"))
        catalog.commit()
        # The picture search finds the Mega Charizard and the anniversary print, not the 1996 card.
        ids = ["ja:M6a-137", "ja:S8a-P-001"]
        snapshot = SimpleNamespace(card_ids=np.array(ids), embeddings=np.array(
            [[.82, np.sqrt(1-.82**2)], [.80, np.sqrt(1-.80**2)]], dtype=np.float32))
        ocr = OcrResult(name_text="リザードン", hits=[OcrHit("リザードン", .9995, "name")])
        runtime = SimpleNamespace(require=lambda: (snapshot,
            SimpleNamespace(embed=lambda *args: np.array([1, 0], dtype=np.float32)),
            SimpleNamespace(read=lambda image: ocr)), card_languages=np.array(["ja"]*len(ids)),
            artwork_verifier=None, printing_index=None, metadata_index=None,
            versions=lambda: dict(model_revision="test", catalogue="test", ocr="test", ranking="test"),
            threshold_config=lambda: {})
        image = Image.fromarray(np.random.default_rng(8).integers(0, 255, (825, 600, 3), dtype=np.uint8))
        payload = io.BytesIO()
        image.save(payload, format="JPEG")
        response = recognize_bytes(payload.getvalue(), settings=Settings(
            _env_file=None, data_dir=tmp_path/("on" if on else "off"), store_captures=False,
            vintage_name_choices=on), runtime=runtime, catalog=catalog, results=results,
            session_id="test", skip_detect=True, language="ja")
        evidence = json.loads(results.execute("SELECT ocr_json FROM scans WHERE id=?",
                                              (response.id,)).fetchone()[0])
        return response, evidence
    finally:
        catalog.close()
        results.close()


def test_pipeline_offers_the_vintage_card_without_changing_the_answer(tmp_path):
    off, off_evidence = _scan(tmp_path/"off", False)
    on, evidence = _scan(tmp_path/"on", True)
    offered = lambda r: [p.card_id for p in (r.printing_review.plausible_printings if r.printing_review else [])]
    # Same answer and status: the scan still needs confirmation, on the same first card.
    assert on.status == off.status
    assert on.status in {"uncertain", "printing_ambiguous"}
    assert on.suggestions[0].card_id == off.suggestions[0].card_id
    assert "ja:PMCG1-021" not in offered(off)
    assert "vintage_name_choices" not in off_evidence
    # The 1996 card is now one of the choices, after the card shown first.
    assert offered(on)[0] == on.suggestions[0].card_id
    assert "ja:PMCG1-021" in offered(on)
    assert evidence["vintage_name_choices"] == {"reason": "choices", "card_ids": ["ja:PMCG1-021"]}
    # Saved with the scan, so the feedback endpoint accepts the collector choosing it.
    assert "ja:PMCG1-021" in [p["card_id"] for p in evidence["printing_review"]["plausible_printings"]]
