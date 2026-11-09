import pytest

from app.recognition import rank
from app.recognition.rank import extract_collector_candidates


def numbers(lines):
    return [h.text for h in extract_collector_candidates(lines)]


@pytest.fixture
def guards_on(monkeypatch):
    settings = rank.get_settings().model_copy(update={"ocr_cjk_minus_guard": True, "ocr_dex_number_guard": True})
    monkeypatch.setattr(rank, "get_settings", lambda: settings)


@pytest.mark.parametrize("line", ["ダメージ-30", "抵抗力-30", "规力-30", "ダメ-シ-30", "抵抗力 −30"])
def test_japanese_resistance_values_are_not_collector_numbers(guards_on, line):
    assert numbers([line]) == []


def test_ascii_codes_fractions_and_bare_numbers_stay(guards_on):
    assert numbers(["025/048"]) == ["025/048"]
    assert numbers(["025"]) == ["025"]


def test_ascii_prefixed_codes_read_as_without_the_flag(guards_on, monkeypatch):
    with_flag = numbers(["SV-P 025"])
    off = rank.get_settings().model_copy(update={"ocr_cjk_minus_guard": False, "ocr_dex_number_guard": True})
    monkeypatch.setattr(rank, "get_settings", lambda: off)
    assert numbers(["SV-P 025"]) == with_flag


def test_neo1_072_footer_yields_no_collector(guards_on):
    assert numbers(["ルギア", "HP90", "规力-30", "No.249", "ダメージ-30"]) == []


@pytest.fixture
def flag_off(monkeypatch):
    settings = rank.get_settings().model_copy(update={"ocr_cjk_minus_guard": False})
    monkeypatch.setattr(rank, "get_settings", lambda: settings)


def test_flag_off_keeps_todays_reading(flag_off):
    assert "30" in numbers(["ダメージ-30"])


def test_flag_is_on_by_default():
    from app.config import Settings
    assert Settings().ocr_cjk_minus_guard is True
