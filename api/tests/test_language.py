from __future__ import annotations

from app.recognition.language import detect_script_language, resolve_search_languages
from app.recognition.rank import name_match, normalize_text


def test_detects_japanese_from_kana() -> None:
    assert detect_script_language(["たね", "ゲンガー&ミミッキュGX"]) == "ja"


def test_detects_english_from_latin() -> None:
    assert detect_script_language(["Basic Pokémon", "Pikachu", "weakness"]) == "en"


def test_detects_simplified_chinese() -> None:
    assert detect_script_language(["基本能量", "这个宝可梦"]) == "zh-cn"


def test_detects_traditional_chinese() -> None:
    assert detect_script_language(["基本能量", "這個寶可夢"]) == "zh-tw"


def test_auto_detects_japanese_but_searches_all_prints() -> None:
    decision = resolve_search_languages("auto", ["ルギアV", "たわ"])
    assert decision.detected == "ja"
    assert decision.search == ()


def test_user_language_overrides_ocr() -> None:
    decision = resolve_search_languages("en", ["たね", "ゲンガー"])
    assert decision.search == ("en",)
    assert decision.detected == "ja"


def test_chinese_group_covers_both_scripts() -> None:
    decision = resolve_search_languages("zh", ["皮卡丘"])
    assert set(decision.search) == {"zh-cn", "zh-tw"}


def test_normalize_keeps_japanese_letters() -> None:
    assert "ゲンガー" in normalize_text("ゲンガー&ミミッキュGX")


def test_japanese_name_matches_catalogue_name() -> None:
    assert name_match("ゲンガー&ミミッキュGX", "ゲンガー&ミミッキュGX") is True
    assert name_match("ゲンガー", "ゲンガー&ミミッキュGX") is True
