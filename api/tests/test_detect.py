from __future__ import annotations

from PIL import Image

from app.recognition.detect import detect_and_rectify


def test_detects_contrasting_rectangle() -> None:
    image = Image.new("RGB", (400, 400), color=(20, 20, 20))
    card = Image.new("RGB", (180, 250), color=(240, 240, 240))
    image.paste(card, (110, 70))
    result, detected = detect_and_rectify(image)
    assert detected is True
    assert min(result.size) >= 80


def test_busy_background_falls_back() -> None:
    image = Image.new("RGB", (120, 120), color=(80, 80, 80))
    result, detected = detect_and_rectify(image)
    assert detected is False
    assert result.size == image.size
