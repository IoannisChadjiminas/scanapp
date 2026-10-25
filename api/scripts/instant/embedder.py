"""Server-model embeddings for Phase 0 queries (same preprocessing as the API).

Uses `app.recognition.preprocess` so the pad/square resize and ImageNet
normalisation are the server's own code, not a copy.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

API_DIR = Path(__file__).resolve().parents[2]
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.recognition.preprocess import prepare_full_card, to_nchw  # noqa: E402

# Phone-like jitter: (scale, dx, dy) of a centre crop, as fractions of the frame.
# Frame 0 is the photo as delivered; the rest mimic a card held a little differently.
FRAME_SPECS: tuple[tuple[float, float, float], ...] = (
    (1.00, 0.00, 0.00),
    (0.97, 0.00, 0.00),
    (0.97, 0.02, 0.00),
    (1.03, 0.00, 0.00),
    (1.00, -0.02, 0.02),
    (1.00, 0.02, -0.02),
)


def crop_frame(image: Image.Image, scale: float, dx: float, dy: float) -> Image.Image:
    width, height = image.size
    crop_w, crop_h = width * scale, height * scale
    centre_x = width / 2 + dx * width
    centre_y = height / 2 + dy * height
    left = min(max(centre_x - crop_w / 2, 0.0), width - crop_w)
    top = min(max(centre_y - crop_h / 2, 0.0), height - crop_h)
    box = (round(left), round(top), round(left + crop_w), round(top + crop_h))
    return image.crop(box)


def frames_for(image: Image.Image, specs: tuple[tuple[float, float, float], ...] = FRAME_SPECS) -> list[Image.Image]:
    return [image.convert("RGB") if spec == (1.0, 0.0, 0.0) else crop_frame(image.convert("RGB"), *spec) for spec in specs]


class OnnxEmbedder:
    """DINOv2-small on CPU through onnxruntime, one image per call."""

    def __init__(self, model_path: Path) -> None:
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            str(model_path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name

    def embed_tensor(self, tensor: np.ndarray) -> np.ndarray:
        output = np.asarray(self.session.run(None, {self.input_name: tensor})[0], dtype=np.float32).reshape(-1)
        return output / np.linalg.norm(output)

    def embed_image(self, image: Image.Image, mode: str = "pad") -> np.ndarray:
        return self.embed_tensor(to_nchw(prepare_full_card(image, mode)))


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
