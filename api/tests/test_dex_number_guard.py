import pytest

from app.recognition import rank
from app.recognition.rank import extract_collector_candidates


def numbers(lines):
    return [h.text for h in extract_collector_candidates(lines)]


@pytest.fixture
def guard_on(monkeypatch):
    settings = rank.get_settings().model_copy(update={"ocr_dex_number_guard": True})
    monkeypatch.setattr(rank, "get_settings", lambda: settings)


@pytest.mark.parametrize("line", ["No.025", "No 025", "NO.025", "N0.025", "No,025", "全国図鑑No.025"])
def test_pokedex_numbers_are_not_collector_numbers(guard_on, line):
    assert numbers([line]) == []


def test_fractions_and_bare_numbers_stay(guard_on):
    assert numbers(["025/048"]) == ["025/048"]
    assert numbers(["025"]) == ["025"]


def test_neo1_072_footer_keeps_only_the_other_number(guard_on):
    # neo1-072-1: the footer read "No.249" (Lugia's Pokedex number) and a stray "30"
    assert "249" not in numbers(["No.249", "30"])


@pytest.fixture
def flag_off(monkeypatch):
    settings = rank.get_settings().model_copy(update={"ocr_dex_number_guard": False})
    monkeypatch.setattr(rank, "get_settings", lambda: settings)


def test_flag_off_keeps_todays_reading(flag_off):
    assert numbers(["No.025"]) == ["025"]


def test_flag_is_on_by_default():
    from app.config import Settings
    assert Settings().ocr_dex_number_guard is True
