from __future__ import annotations

from app.recognition.ocr import pick_collector_text, pick_name_line
from app.recognition.rank import decide_status, name_match, number_match, rerank


def _card(card_id: str, name: str, number: str, score: float, language: str = "en") -> dict:
    return {
        "card_id": card_id,
        "name": name,
        "set_name": "Base",
        "collector_number": number,
        "image_url": f"/api/v1/cards/{card_id}/image",
        "visual_score": score,
        "combined_score": score,
        "ocr_consistent": None,
        "language": language,
    }


def test_ocr_boosts_matching_number() -> None:
    visual = [
        _card("a", "Pikachu", "25", 0.80),
        _card("b", "Raichu", "26", 0.79),
    ]
    ranked = rerank(visual, "Pikachu", ["25"], ocr_failed=False)
    assert ranked[0]["card_id"] == "a"
    assert ranked[0]["ocr_consistent"] is True
    assert ranked[0]["combined_score"] > ranked[0]["visual_score"]


def test_conflicting_number_penalizes_candidate() -> None:
    visual = [_card("a", "Pikachu", "25", 0.91)]
    ranked = rerank(visual, None, ["99"], ocr_failed=False)
    assert ranked[0]["ocr_consistent"] is False
    assert ranked[0]["combined_score"] < ranked[0]["visual_score"]


def test_missing_ocr_does_not_block_visual_order() -> None:
    visual = [
        _card("a", "Pikachu", "25", 0.88),
        _card("b", "Pikachu", "26", 0.70),
    ]
    ranked = rerank(visual, None, [], ocr_failed=True)
    assert [item["card_id"] for item in ranked] == ["a", "b"]
    assert ranked[0]["ocr_consistent"] is None


def test_matched_when_visual_and_gap_pass() -> None:
    suggestions = [
        _card("a", "Pikachu", "25", 0.92),
        _card("b", "Raichu", "26", 0.70),
    ]
    suggestions[0]["ocr_consistent"] = False
    status = decide_status(
        suggestions,
        enable_matched=False,
        min_visual=0.78,
        min_gap=0.04,
        retake=False,
    )
    assert status == "matched"


def test_no_match_when_visual_is_low() -> None:
    suggestions = [
        _card("a", "Pikachu", "25", 0.62),
        _card("b", "Raichu", "26", 0.40),
    ]
    status = decide_status(
        suggestions,
        enable_matched=True,
        min_visual=0.78,
        min_gap=0.04,
        retake=False,
    )
    assert status == "no_match"


def test_no_match_when_gap_is_small() -> None:
    suggestions = [
        _card("a", "Switch", "95", 0.88),
        _card("b", "Scoop Up", "78", 0.87),
    ]
    status = decide_status(
        suggestions,
        enable_matched=True,
        min_visual=0.78,
        min_gap=0.04,
        retake=False,
    )
    assert status == "no_match"


def test_short_ocr_digit_does_not_match_collector() -> None:
    visual = [
        _card("gengar", "Gengar & Mimikyu GX", "103/095", 0.918, "ja"),
        _card("crobat", "Crobat V", "182", 0.722, "en"),
    ]
    ranked = rerank(visual, "たね", ["2", "240", "102/0955"], ocr_failed=False, detected_languages=("ja",))
    assert ranked[0]["card_id"] == "gengar"


def test_ocr_cannot_outrank_clear_visual_leader() -> None:
    visual = [
        _card("gengar", "Gengar & Mimikyu GX", "103/095", 0.918, "ja"),
        _card("crobat", "Crobat V", "182", 0.722, "en"),
    ]
    ranked = rerank(visual, "Crobat V", ["182"], ocr_failed=False, detected_languages=("ja",))
    assert ranked[0]["card_id"] == "gengar"


def test_japanese_print_wins_when_art_matches_english() -> None:
    visual = [
        _card("en-zard", "Charizard", "4", 0.91, "en"),
        _card("ja-zard", "リザードン", "006", 0.89, "ja"),
    ]
    ranked = rerank(visual, "リザードン", [], ocr_failed=False, detected_languages=("ja",))
    assert ranked[0]["card_id"] == "ja-zard"


def test_matched_uses_visual_gap_not_ocr_scores() -> None:
    suggestions = [
        _card("gengar", "Gengar & Mimikyu GX", "103/095", 0.918, "ja"),
        _card("crobat", "Crobat V", "182", 0.722, "en"),
    ]
    suggestions[0]["combined_score"] = 0.798
    suggestions[1]["combined_score"] = 0.802
    status = decide_status(
        suggestions,
        enable_matched=True,
        min_visual=0.78,
        min_gap=0.04,
        retake=False,
    )
    assert status == "matched"


def test_retake_when_image_unsuitable() -> None:
    status = decide_status(
        [_card("a", "Pikachu", "25", 0.95)],
        enable_matched=True,
        min_visual=0.7,
        min_gap=0.01,
        retake=True,
    )
    assert status == "retake"


def test_number_match_ignores_short_damage_digits() -> None:
    assert number_match(["2", "240", "102/0955"], "182") is False
    assert number_match(["2"], "2") is True
    assert number_match(["103/095"], "103/095") is True
    assert number_match(["103"], "103/095") is True


def test_ocr_fraction_distinguishes_reprints() -> None:
    assert number_match(["008/034", "008034"], "008/034") is True
    assert number_match(["008/034", "008034"], "008/015") is False
    assert number_match(["008"], "008/015") is True
    assert number_match(["008"], "008/034") is True


def test_reprint_with_matching_fraction_is_matched() -> None:
    visual = [
        _card("mcd", "Pikachu", "008/015", 0.9997),
        _card("clc", "Pikachu", "008/034", 0.9989),
        _card("base", "Pikachu", "58", 0.84),
    ]
    ranked = rerank(visual, "Pikachu", ["008/034"], ocr_failed=False, detected_languages=("en",))
    assert ranked[0]["card_id"] == "clc"
    assert ranked[0]["ocr_consistent"] is True
    assert ranked[1]["card_id"] == "mcd"
    assert ranked[1]["ocr_consistent"] is False
    status = decide_status(
        ranked,
        enable_matched=True,
        min_visual=0.78,
        min_gap=0.04,
        retake=False,
    )
    assert status == "matched"


def test_pick_collector_prefers_fraction_line() -> None:
    assert pick_collector_text(["008/034", "33 Pokemoen/Mrtendo"]) == "008/034"
    assert pick_collector_text(["Illus. Mitsuhiro Arita"]) == "Illus. Mitsuhiro Arita"


def test_pick_name_skips_japanese_stage_label() -> None:
    assert pick_name_line(["たね", "ゲンガー&ミミッキュGX"]) == "ゲンガー&ミミッキュGX"
    assert pick_name_line(["Basic Pokémon", "Pikachu"]) == "Pikachu"


def test_japanese_ocr_name_does_not_match_english_card() -> None:
    assert not name_match("ゲンガー&ミミッキュGX", "Gengar & Mimikyu GX")
