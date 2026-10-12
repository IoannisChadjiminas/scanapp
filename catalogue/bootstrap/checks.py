"""Automatic reference-image checks. Thresholds match the scanner settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# api/app/config.py Settings defaults. Do not tune these here.
MIN_SIDE = 180
BLUR_LIMIT = 40.0
BLUR_EDGE = 1000

_BACK = ("back", "cardback", "card-back")


@dataclass(frozen=True)
class ImageFacts:
    width: int
    height: int
    blur: float | None
    dhash: int | None
    back_only: bool


def judge(
    facts: ImageFacts | None,
    *,
    language: str,
    name: str,
    collector: str | None,
    observed_name: str | None,
    observed_collector: str | None,
    lines: list[str],
    duplicate_of: str | None,
) -> tuple[str, str]:
    """Return pass, fail, or review, plus a reason. Fail beats review."""
    failures: list[str] = []
    reviews: list[str] = []
    if facts is None:
        reviews.append("no_image")
    else:
        if facts.back_only:
            failures.append("back_only")
        if min(facts.width, facts.height) < MIN_SIDE:
            failures.append("too_small")
        elif facts.blur is None:
            reviews.append("blur_not_measured")
        elif facts.blur < BLUR_LIMIT:
            failures.append("too_blurry")
        if duplicate_of:
            failures.append(f"duplicate_of:{duplicate_of}")
    identity = _identity(name, collector, observed_name, observed_collector)
    if identity == "missing":
        reviews.append("identity_not_read")
    elif identity == "mismatch":
        failures.append("identity_mismatch")
    script = _script(lines)
    if script and language and script != language:
        failures.append(f"wrong_script:{script}")
    if failures:
        return "fail", ",".join(failures)
    if reviews:
        return "review", ",".join(reviews)
    return "pass", "resolution_blur_identity_script"


def collector_matches(expected: str | None, observed: str | None) -> bool | None:
    if not expected or not observed:
        return None
    exp = expected.strip().casefold()
    obs = observed.strip().casefold().replace(" ", "")
    if obs == exp or obs.startswith(exp + "/"):
        return True
    head = obs.split("/", 1)[0]
    return head == exp


def load_facts(path: Path, label: str = "") -> ImageFacts:
    from PIL import Image

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        return ImageFacts(
            width=width,
            height=height,
            blur=_blur(rgb),
            dhash=_dhash(rgb),
            back_only=_looks_back(label or path.name),
        )


def _identity(
    name: str,
    collector: str | None,
    observed_name: str | None,
    observed_collector: str | None,
) -> str:
    if not observed_name and not observed_collector:
        return "missing"
    if observed_name and observed_name.casefold() != name.casefold():
        return "mismatch"
    matched = collector_matches(collector, observed_collector)
    if matched is False:
        return "mismatch"
    if observed_name and matched is True:
        return "match"
    return "missing"


def _script(lines: list[str]) -> str | None:
    text = [line for line in lines if line]
    if not text:
        return None
    try:
        from app.recognition.language import detect_card_language
    except ImportError:
        return _script_fallback(text)
    detected = detect_card_language(text)
    if detected in {"zh-cn", "zh-tw"}:
        return "zh"
    return detected


def _script_fallback(lines: list[str]) -> str | None:
    hira = kata = latin = 0
    for char in "\n".join(lines):
        code = ord(char)
        if 0x3040 <= code <= 0x309F:
            hira += 1
        elif 0x30A0 <= code <= 0x30FF:
            kata += 1
        elif char.isascii() and char.isalpha():
            latin += 1
    if hira + kata >= 2:
        return "ja"
    if latin >= 8:
        return "en"
    return None


def _looks_back(label: str) -> bool:
    tokens = label.casefold().replace("_", "-").replace(".", "-").split("-")
    return any(token in _BACK or token == "back" for token in tokens)


def _blur(image) -> float | None:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    gray = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
    long_side = max(gray.shape[:2])
    if long_side > BLUR_EDGE:
        scale = BLUR_EDGE / long_side
        gray = cv2.resize(
            gray,
            (max(1, round(gray.shape[1] * scale)), max(1, round(gray.shape[0] * scale))),
            interpolation=cv2.INTER_AREA,
        )
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _dhash(image, size: int = 8) -> int:
    gray = image.convert("L").resize((size + 1, size))
    pixels = list(gray.get_flattened_data() if hasattr(gray, "get_flattened_data") else gray.getdata())
    bits = 0
    for row in range(size):
        for col in range(size):
            left = pixels[row * (size + 1) + col]
            right = pixels[row * (size + 1) + col + 1]
            bits = (bits << 1) | int(left > right)
    return bits


def hamming(left: int, right: int) -> int:
    return (left ^ right).bit_count()
