from __future__ import annotations

from app.recognition.rank import decide_status, rerank


def _card(card_id: str, name: str, number: str, score: float) -> dict:
    return {
        "card_id": card_id,
        "name": name,
        "set_name": "Base",
        "collector_number": number,
        "image_url": f"/api/v1/cards/{card_id}/image",
        "visual_score": score,
        "combined_score": score,
        "ocr_consistent": None,
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


def test_matched_disabled_stays_uncertain() -> None:
    suggestions = [_card("a", "Pikachu", "25", 0.95)]
    status = decide_status(
        suggestions,
        enable_matched=False,
        min_visual=0.7,
        min_gap=0.01,
        retake=False,
    )
    assert status == "uncertain"


def test_retake_when_image_unsuitable() -> None:
    status = decide_status(
        [_card("a", "Pikachu", "25", 0.95)],
        enable_matched=True,
        min_visual=0.7,
        min_gap=0.01,
        retake=True,
    )
    assert status == "retake"
