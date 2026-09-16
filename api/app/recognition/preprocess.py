from __future__ import annotations

import numpy as np
from PIL import Image


IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
MODEL_SIZE = 224


def prepare_full_card(image: Image.Image, mode: str, size: int = MODEL_SIZE) -> Image.Image:
    rgb = image.convert("RGB")
    if mode == "square":
        return rgb.resize((size, size), Image.Resampling.BICUBIC)
    if mode != "pad":
        raise ValueError(f"Unknown preprocess mode: {mode}")
    width, height = rgb.size
    scale = size / max(width, height)
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    resized = rgb.resize(new_size, Image.Resampling.BICUBIC)
    canvas = Image.new("RGB", (size, size), (0, 0, 0))
    offset = ((size - new_size[0]) // 2, (size - new_size[1]) // 2)
    canvas.paste(resized, offset)
    return canvas


def to_nchw(image: Image.Image) -> np.ndarray:
    array = np.asarray(image, dtype=np.float32) / 255.0
    array = (array - IMAGENET_MEAN) / IMAGENET_STD
    return np.transpose(array, (2, 0, 1))[None, ...]
