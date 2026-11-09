"""OCR_TRAINERS_BANNER: the Sun & Moon "TRAINER'S" banner is a layout badge, never a name.

Second development set, dev2-ja-modern-074: Judge SR SM7a-066 read its name as "TRAINER'S" at
0.99 and ranked Gym Trainer S4a-192 first.
"""
import pytest

from app.recognition import ocr


@pytest.fixture
def flag(monkeypatch):
    def set_flag(on):
        settings = ocr.__dict__.get('get_settings')
        from app import config
        s = config.get_settings().model_copy(update={"ocr_trainers_banner": on})
        monkeypatch.setattr(config, "get_settings", lambda: s)
    return set_flag


def test_trainers_banner_is_a_badge_with_the_flag(flag):
    flag(True)
    assert ocr._is_layout_badge("TRAINER'S")
    assert ocr._pick_name_line(["TRAINER'S", "ジャッジマン"]) == "ジャッジマン"


def test_flag_off_keeps_todays_reading(flag):
    flag(False)
    assert not ocr._is_layout_badge("TRAINER'S")


def test_real_names_are_never_dropped(flag):
    flag(True)
    for name in ("Trainer's Mail", "Pokémon Trainer", "Gym Trainer", "Ace Trainer", "Trainers' Mail"):
        assert not ocr._is_layout_badge(name), name
    assert ocr._pick_name_line(["Trainer's Mail"]) == "Trainer's Mail"
