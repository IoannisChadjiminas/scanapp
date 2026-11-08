import pytest

from app.recognition import rank
from app.recognition.ocr import OcrHit
from app.recognition.rank import artwork_evidence_compatible, rerank
from app.recognition.species_names import read_species, row_species, species_verdict

# neo1-072-1 on the all-eras catalogue: ルギア read at 0.99 and a stray "30" on the collector line
# that matches a new row with an English-only name (number 030). With the flag off that row leads
# by a small margin (0.002 in the trace); the scores below reproduce a lead of the same kind.
LUGIA_READ = "ルギア"
NUMBERS = [OcrHit("30", .3, "collector")]
HO_OH = {"card_id": "ja:jr-play-promos-030", "name": "Ho-Oh ex", "language": "ja", "set_id": "jr-play-promos",
         "collector_number": "030", "visual_score": .76}
LUGIA = {"card_id": "ja:neo1-072", "name": "ルギア", "language": "ja", "set_id": "neo1",
         "collector_number": "072", "visual_score": .75}


@pytest.fixture
def species_on(monkeypatch):
    settings = rank.get_settings().model_copy(update={"rank_species_names": True})
    monkeypatch.setattr(rank, "get_settings", lambda: settings)


def test_english_and_transliterated_rows_resolve_to_official_species():
    assert row_species({"name": "Ho-Oh ex", "language": "ja"}) == {"ホウオウ"}
    assert row_species({"name": "Charizard-GX", "language": "ja"}) == {"リザードン"}
    assert row_species({"name": "M Mawile-EX", "language": "ja"}) == {"クチート"}
    assert row_species({"name": "Dark Charizard", "language": "ja"}) == {"リザードン"}
    assert row_species({"name": "Mewtwo", "language": "ja"}) == {"ミュウツー"}  # not ミュウ
    # an older-era machine transliteration falls back to the English title
    assert row_species({"name": "マチャンプ", "view_title": "Machamp", "language": "ja"}) == {"カイリキー"}


def test_rows_that_are_compared_today_stay_untouched():
    assert row_species({"name": "わるいリザードン", "view_title": "Dark Charizard", "language": "ja"}) == set()
    assert row_species({"name": "Ho-Oh ex", "language": "en"}) == set()
    assert row_species({"name": "Fire Energy", "language": "ja"}) == set()
    assert row_species({"name": "Professor Oak's Research", "language": "ja"}) == set()


def test_reads_resolve_to_the_longest_species():
    assert read_species("わるいリザードン") == {"リザードン"}
    assert read_species("ミュウツーex") == {"ミュウツー"}
    assert read_species("モンスターカードに重ねて使います。") == set()


def test_verdict_needs_both_sides():
    assert species_verdict(LUGIA_READ, HO_OH) is False
    assert species_verdict(LUGIA_READ, {"name": "Lugia", "language": "ja"}) is True
    assert species_verdict("カイリキー", {"name": "マチャンプ", "view_title": "Machamp", "language": "ja"}) is True
    assert species_verdict("モンスターカードに重ねて使います。", HO_OH) is None  # read names no species
    assert species_verdict(LUGIA_READ, {"name": "Fire Energy", "language": "ja"}) is None
    assert species_verdict(LUGIA_READ, LUGIA) is None  # Japanese-named rows keep today's rule


def test_flag_off_keeps_the_new_row_first():
    ranked = rerank([HO_OH, LUGIA], LUGIA_READ, NUMBERS, False, detected_languages=("ja",),
                    name_confidence=.99, require_confident_ocr=True)
    assert ranked[0]["card_id"] == HO_OH["card_id"]


def test_species_names_put_lugia_first_and_rule_out_ho_oh(species_on):
    ranked = rerank([HO_OH, LUGIA], LUGIA_READ, NUMBERS, False, detected_languages=("ja",),
                    name_confidence=.99, require_confident_ocr=True)
    assert ranked[0]["card_id"] == LUGIA["card_id"]
    ho_oh = next(r for r in ranked if r["card_id"] == HO_OH["card_id"])
    assert ho_oh["strong_name_conflict"] and ho_oh["ocr_consistent"] is False
    assert not artwork_evidence_compatible(HO_OH, ocr_name=LUGIA_READ, name_confidence=.99,
                                           numbers=[], languages=("ja",))
    assert artwork_evidence_compatible({**HO_OH, "name": "Lugia"}, ocr_name=LUGIA_READ, name_confidence=.99,
                                       numbers=[], languages=("ja",))


def test_flag_is_off_by_default():
    from app.config import Settings
    assert Settings().rank_species_names is False
