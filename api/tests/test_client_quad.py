"""The phone's corners fill in when the server finds no card, and never override it."""
import numpy as np
from PIL import Image, ImageDraw

from app.recognition.detect import client_quad_rect, quads_agree, server_frame_rect
from app.recognition.pipeline import _detect_with_client_quad

W, H = 600, 800


def photo(card=(150, 180, 450, 620), noise=False):
    """Dark desk with a light card; `noise` hides the card's edges from Canny."""
    image = Image.new('RGB', (W, H), (30, 30, 30))
    ImageDraw.Draw(image).rectangle(card, fill=(230, 230, 220))
    if noise:
        rng = np.random.default_rng(1)
        array = np.asarray(image).astype(np.int16) + rng.integers(-60, 60, (H, W, 3))
        image = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))
    return image


def quad(card=(150, 180, 450, 620)):
    x1, y1, x2, y2 = card
    return [(x1 / W, y1 / H), (x2 / W, y1 / H), (x2 / W, y2 / H), (x1 / W, y2 / H)]


def test_matching_server_and_phone_quads_agree_and_the_server_frame_is_used():
    frame, detected, note = _detect_with_client_quad(photo(), quad())
    assert detected and note == 'client_quad_agrees'
    assert abs(frame.width / frame.height - 300 / 440) < .03


def test_a_phone_quad_far_from_the_server_one_is_logged_and_ignored():
    shifted = quad((60, 100, 360, 540))
    frame, detected, note = _detect_with_client_quad(photo(), shifted)
    assert detected and note == 'client_quad_disagrees'
    # The server's rectangle (the real card), not the phone's, was warped.
    assert np.asarray(frame).mean() > 200


def test_phone_quad_alone_is_used_when_the_server_finds_no_card():
    image = Image.new('RGB', (W, H), (120, 120, 120))  # nothing to detect
    assert server_frame_rect(image) is None
    frame, detected, note = _detect_with_client_quad(image, quad())
    assert detected and note == 'client_quad_only'
    assert abs(frame.width / frame.height - 300 / 440) < .03


def test_implausible_phone_quads_are_rejected_and_today_s_result_stands():
    image = Image.new('RGB', (W, H), (120, 120, 120))
    wide = [(0.1, 0.4), (0.9, 0.4), (0.9, 0.6), (0.1, 0.6)]  # not card-shaped
    frame, detected, note = _detect_with_client_quad(image, wide)
    assert (detected, note) == (False, 'client_quad_rejected') and frame is image
    assert client_quad_rect(image, wide) is None


def test_agreement_is_four_percent_of_the_smaller_card_side():
    a = np.array([[0, 0], [300, 0], [300, 440], [0, 440]], dtype=np.float32)
    assert quads_agree(a, a + 5) and not quads_agree(a, a + 20)
