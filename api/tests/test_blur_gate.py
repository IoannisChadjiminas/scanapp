import numpy as np
from PIL import Image

from app.recognition.images import blur_variance


def _textured(size, seed=1):
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 255, (size[1] // 4, size[0] // 4, 3), dtype=np.uint8)
    return Image.fromarray(base).resize(size, Image.BICUBIC)


def test_score_is_comparable_across_upload_sizes():
    large_image = _textured((2000, 2800))
    large = blur_variance(large_image, 1000)
    smaller = blur_variance(large_image.resize((1400, 1960), Image.LANCZOS), 1000)
    assert abs(large - smaller) / max(large, smaller) < 0.35
    native = (blur_variance(large_image, 0), blur_variance(large_image.resize((1400, 1960), Image.LANCZOS), 0))
    assert max(native) > 2 * min(native)


def test_edge_zero_measures_as_supplied():
    image = _textured((800, 1100))
    assert blur_variance(image, 0) == blur_variance(image, 5000)


def test_smaller_images_are_not_enlarged():
    image = _textured((600, 800))
    assert blur_variance(image, 1000) == blur_variance(image, 0)


def test_blurred_photo_scores_below_sharp_one():
    import cv2
    sharp = _textured((1400, 1960))
    soft = Image.fromarray(cv2.GaussianBlur(np.asarray(sharp), (0, 0), 6))
    assert blur_variance(soft, 1000) < 0.2 * blur_variance(sharp, 1000)
