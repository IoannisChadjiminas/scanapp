from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "HEIF", "HEIC"}


class ImageError(ValueError):
    pass


@dataclass
class DecodedImage:
    image: Image.Image
    format_name: str
    converted: bool


def decode_image(data: bytes, max_pixels: int) -> DecodedImage:
    if not data:
        raise ImageError("Empty upload")
    try:
        with Image.open(io.BytesIO(data)) as raw:
            fmt = (raw.format or "").upper()
            if fmt not in ALLOWED_FORMATS:
                raise ImageError(f"Unsupported image format: {fmt or 'unknown'}")
            oriented = ImageOps.exif_transpose(raw) or raw
            image = oriented.convert("RGB")
            converted = fmt in {"HEIF", "HEIC"} or fmt != "JPEG"
    except ImageError:
        raise
    except Exception as exc:  # noqa: BLE001 - pillow raises many subclasses
        raise ImageError("Unreadable image") from exc

    width, height = image.size
    if width * height > max_pixels:
        scale = (max_pixels / (width * height)) ** 0.5
        image = image.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            Image.Resampling.BICUBIC,
        )
    if min(image.size) < 32:
        raise ImageError("Image is too small")
    return DecodedImage(image=image, format_name=fmt, converted=converted)


def to_jpeg_bytes(image: Image.Image, quality: int = 88) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def apply_crop(
    image: Image.Image,
    crop_x: float | None,
    crop_y: float | None,
    crop_w: float | None,
    crop_h: float | None,
    rotation: int = 0,
) -> Image.Image:
    result = image
    if rotation:
        result = result.rotate(-rotation, expand=True)
    if None in (crop_x, crop_y, crop_w, crop_h):
        return result
    width, height = result.size
    left = int(max(0.0, min(1.0, crop_x or 0)) * width)
    top = int(max(0.0, min(1.0, crop_y or 0)) * height)
    right = int(max(0.0, min(1.0, (crop_x or 0) + (crop_w or 1))) * width)
    bottom = int(max(0.0, min(1.0, (crop_y or 0) + (crop_h or 1))) * height)
    if right - left < 16 or bottom - top < 16:
        return result
    return result.crop((left, top, right, bottom))


def blur_variance(image: Image.Image) -> float:
    gray = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())
