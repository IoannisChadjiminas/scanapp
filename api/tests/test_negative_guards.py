"""One negative test per ranking fix: each must leave the case it is not about alone."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

from app.recognition import rank
from app.recognition.family_verify import decisive_family, scan_language_members
from app.recognition.name_evidence import verification_name
from app.recognition.ocr import OcrHit
from app.recognition.rank import extract_collector_candidates
from app.recognition.species_names import species_verdict

spec = importlib.util.spec_from_file_location(
    "build_species_names", Path(__file__).resolve().parents[1] / "scripts/ja_set_recovery/build_species_names.py")
build_species_names = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_species_names)


def numbers(lines):
    return [h.text for h in extract_collector_candidates(lines)]


@pytest.fixture
def all_guards(monkeypatch):
    settings = rank.get_settings().model_copy(update={
        "ocr_dex_number_guard": True, "ocr_cjk_minus_guard": True, "ocr_promo_s5_guard": True,
        "rank_species_names": True})
    monkeypatch.setattr(rank, "get_settings", lambda: settings)


# 1. RANK_FAMILY_VERIFY
def test_family_close_to_its_runner_up_decides_nothing():
    families = [[{"card_id": "a"}], [{"card_id": "b"}]]
    assert decisive_family(families, {"a": 20, "b": 15}) is None   # 20 < 1.5 x 15


def test_family_in_the_scan_language_is_kept_whole():
    family = [{"card_id": "en:x", "language": "en"}, {"card_id": "en:y", "language": "en"}]
    assert scan_language_members(family, ("en",), "en") == family


# 2. VERIFY_UNMATCHED_NAME
def test_a_confident_read_naming_a_candidate_title_is_kept():
    rows = [{"card_id": "ja:x", "name": "Charizard", "view_title": "Charizard", "language": "ja"}]
    assert verification_name("Charizard", .99, rows, languages=("ja",), numbers=[])[2] is False


# 3. RANK_SPECIES_NAMES: the table never maps ambiguously, the verdict never invents a match
def test_one_japanese_name_for_two_english_species_is_rejected():
    rows = [("SV1", "ミュウツー", "Mewtwo"), ("SV2", "ミュウツー", "Mewtwo"),
            ("SV3", "ミュウツー", "Mew"), ("SV4", "ミュウツー", "Mew")]
    species, rejected = build_species_names.build(rows)
    assert "mewtwo" not in species and "mew" not in species and {"mewtwo", "mew"} <= set(rejected)


def test_one_english_species_with_two_japanese_names_is_rejected():
    rows = [("SV1", "ニドラン♀", "Nidoran"), ("SV2", "ニドラン♀", "Nidoran"),
            ("SV3", "ニドラン♂", "Nidoran"), ("SV4", "ニドラン♂", "Nidoran")]
    species, rejected = build_species_names.build(rows)
    assert "nidoran" not in species and "nidoran" in rejected


def test_species_verdict_is_false_for_another_species_and_none_without_a_read_species():
    row = {"name": "Illumise", "language": "ja"}
    assert species_verdict("フワライド", row) is False
    assert species_verdict("ポケモンのどうぐ", row) is None


# 4. OCR_DEX_NUMBER_GUARD
@pytest.mark.parametrize("line", ["CASINO 025", "NOV 025", "025"])
def test_no_inside_a_word_is_not_a_pokedex_prefix(all_guards, monkeypatch, line):
    with_guard = numbers([line])
    off = rank.get_settings().model_copy(update={"ocr_dex_number_guard": False})
    monkeypatch.setattr(rank, "get_settings", lambda: off)
    assert numbers([line]) == with_guard


# 5. OCR_CJK_MINUS_GUARD
def test_a_promo_code_hyphen_after_ascii_reads_as_without_the_guard(all_guards, monkeypatch):
    with_guard = numbers(["SV-P 025"])
    off = rank.get_settings().model_copy(update={"ocr_cjk_minus_guard": False})
    monkeypatch.setattr(rank, "get_settings", lambda: off)
    assert numbers(["SV-P 025"]) == with_guard


def test_a_bare_minus_number_after_ascii_text_is_still_dropped(all_guards):
    assert "30" not in numbers(["weakness -30"])


# 6. OCR_PROMO_S5_GUARD
def test_a_real_denominator_of_5_without_promo_suffix_stays(all_guards):
    assert numbers(["003/5"]) == ["003/5"]
