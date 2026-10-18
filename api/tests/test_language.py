from __future__ import annotations

from app.recognition.language import (detect_script_language, english_print_evidence, ranking_languages,
                                     resolve_search_languages)
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


def _auto(texts: list[str]):
    return resolve_search_languages("auto", texts)


# Confident Latin text on a Japanese print whose kana OCR fell below the floor.
JA_FOOTER_LATIN = ["Illus. PLANETA Mochizuki", "sv2a 185/165 SR",
                   "©2023 Pokémon/Nintendo/Creatures/GAME FREAK"]


def test_latin_letters_alone_do_not_rank_a_japanese_leader_as_english() -> None:
    decision = _auto(JA_FOOTER_LATIN)
    assert decision.detected == "en"
    assert ranking_languages(decision, JA_FOOTER_LATIN, "ja") == ()


def test_latin_guess_still_ranks_when_the_picture_leads_with_english() -> None:
    decision = _auto(JA_FOOTER_LATIN)
    assert ranking_languages(decision, JA_FOOTER_LATIN, "en") == ("en",)
    assert ranking_languages(decision, JA_FOOTER_LATIN, None) == ("en",)


def test_printed_english_words_rank_over_a_japanese_leader() -> None:
    texts = ["Illus. PLANETA Mochizuki", "Pokémon ex rule: When your Pokémon ex is Knocked Out,",
             "your opponent takes 2 Prize cards."]
    assert english_print_evidence(texts)
    assert ranking_languages(_auto(texts), texts, "ja") == ("en",)
    assert english_print_evidence(["weakness", "resistance"])
    assert not english_print_evidence(JA_FOOTER_LATIN)


def test_detected_japanese_and_user_language_rank_unchanged() -> None:
    texts = ["2進化", "リザードンex"]
    assert ranking_languages(_auto(texts), texts, "en") == ("ja",)
    assert ranking_languages(resolve_search_languages("en", texts), texts, "ja") == ("en",)
