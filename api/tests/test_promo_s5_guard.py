import pytest

from app.recognition import rank
from app.recognition.rank import extract_collector_candidates


def numbers(lines):
    return [h.text for h in extract_collector_candidates(lines)]


@pytest.fixture
def guard_on(monkeypatch):
    settings = rank.get_settings().model_copy(update={"ocr_promo_s5_guard": True})
    monkeypatch.setattr(rank, "get_settings", lambda: settings)


@pytest.mark.parametrize("misread,true", [("235/5V-P", "235/SV-P"), ("001/5-P", "001/S-P"),
                                          ("012/5M-P", "012/SM-P"), ("235 / 5V-P", "235/SV-P")])
def test_promo_suffix_read_with_5_reads_as_with_s(guard_on, misread, true):
    assert numbers([misread]) == numbers([true])


def test_b28fa245_footer_has_no_stray_5(guard_on):
    found = numbers(["235/5V-P", "110"])
    assert "5V" not in found and "235" in found


def test_real_fractions_stay(guard_on):
    assert numbers(["012/5"]) == ["012/5"]
    assert numbers(["025/048"]) == ["025/048"]


@pytest.fixture
def flag_off(monkeypatch):
    settings = rank.get_settings().model_copy(update={"ocr_promo_s5_guard": False})
    monkeypatch.setattr(rank, "get_settings", lambda: settings)


def test_flag_off_keeps_todays_reading(flag_off):
    assert "5V" in numbers(["235/5V-P"])


def test_flag_is_on_by_default():
    from app.config import Settings
    assert Settings().ocr_promo_s5_guard is True
