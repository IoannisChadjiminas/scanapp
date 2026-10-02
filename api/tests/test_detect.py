from __future__ import annotations

from PIL import Image
from PIL import ImageDraw

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


def test_prefers_nested_card_over_slab_and_square_background():
    image = Image.new('RGB', (600, 800), 'black')
    draw = ImageDraw.Draw(image)
    draw.rectangle((60, 20, 540, 780), fill='gray')
    draw.rounded_rectangle((115, 190, 485, 710), radius=12, fill='white')
    result, detected = detect_and_rectify(image)
    assert detected
    assert .67 < result.width/result.height < .77
    assert result.width < 400 and result.height < 570


def test_square_and_extreme_rectangle_are_not_card_frames():
    for box in ((60,60,340,340), (20,150,380,250)):
        image = Image.new('RGB',(400,400),'black')
        ImageDraw.Draw(image).rectangle(box, fill='white')
        result, detected = detect_and_rectify(image)
        assert not detected and result is image
