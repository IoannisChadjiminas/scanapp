from __future__ import annotations

import numpy as np
import onnxruntime as ort
from PIL import Image

from app.recognition.preprocess import prepare_full_card, to_nchw


class DinoEmbedder:
    def __init__(self, model_path: str, intra_threads: int, inter_threads: int) -> None:
        options = ort.SessionOptions()
        options.intra_op_num_threads = intra_threads
        options.inter_op_num_threads = inter_threads
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            model_path,
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name

    def embed(self, image: Image.Image, mode: str) -> np.ndarray:
        prepared = prepare_full_card(image, mode)
        tensor = to_nchw(prepared)
        outputs = self.session.run(None, {self.input_name: tensor})
        vector = np.asarray(outputs[0], dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return vector / norm


def top_k(embeddings: np.ndarray, query: np.ndarray, k: int = 20) -> tuple[np.ndarray, np.ndarray]:
    scores = embeddings @ query.astype(np.float32)
    k = min(k, scores.shape[0])
    if k == 0:
        return np.array([], dtype=np.int64), np.array([], dtype=np.float32)
    idx = np.argpartition(-scores, k - 1)[:k]
    idx = idx[np.argsort(-scores[idx])]
    return idx, scores[idx]
