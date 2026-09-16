from __future__ import annotations

from PIL import Image

from app.recognition.ocr import CardOcr
from app.recognition.rank import rerank


def test_ocr_read_failure_returns_failed_result(monkeypatch) -> None:  # noqa: ANN001
    from PIL import Image

    from app.recognition.ocr import CardOcr as Real

    def boom(self, image):  # noqa: ANN001, ARG001
        raise RuntimeError("nope")

    monkeypatch.setattr(Real, "_run", boom)
    ocr = Real.__new__(Real)
    result = Real.read(ocr, Image.new("RGB", (64, 64)))
    assert result.failed is True
    ranked = rerank(
        [
            {
                "card_id": "a",
                "name": "Pikachu",
                "collector_number": "25",
                "visual_score": 0.8,
                "combined_score": 0.8,
            }
        ],
        result.name_text,
        [],
        result.failed,
    )
    assert ranked[0]["card_id"] == "a"
