from __future__ import annotations

import numpy as np
from PIL import Image

from app.recognition.preprocess import prepare_full_card, to_nchw


class DinoEmbedder:
    def __init__(self, model_path: str, intra_threads: int, inter_threads: int) -> None:
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = intra_threads
        options.inter_op_num_threads = inter_threads
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            model_path,
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        first = self.session.get_inputs()[0]
        self.input_name = first.name
        # A fixed batch size of 1 in the exported graph rules out one batched call.
        self.batchable = not (isinstance(first.shape[0], int) and first.shape[0] == 1)

    def embed(self, image: Image.Image, mode: str) -> np.ndarray:
        prepared = prepare_full_card(image, mode)
        tensor = to_nchw(prepared)
        outputs = self.session.run(None, {self.input_name: tensor})
        vector = np.asarray(outputs[0], dtype=np.float32).reshape(-1)
        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return vector / norm


    def embed_many(self, images: list[Image.Image], mode: str) -> list[np.ndarray]:
        """One model call for several frames; the same vectors as `embed`, one by one."""
        if len(images) < 2 or not self.batchable:
            return [self.embed(image, mode) for image in images]
        batch = np.concatenate([to_nchw(prepare_full_card(image, mode)) for image in images])
        try:
            outputs = np.asarray(self.session.run(None, {self.input_name: batch})[0], dtype=np.float32)
        except Exception:
            self.batchable = False
            return [self.embed(image, mode) for image in images]
        if outputs.shape[0] != len(images):
            self.batchable = False
            return [self.embed(image, mode) for image in images]
        vectors = []
        for row in outputs.reshape(len(images), -1):
            norm = np.linalg.norm(row)
            vectors.append(row / norm if norm else row)
        return vectors


def top_k(
    embeddings: np.ndarray,
    query: np.ndarray,
    k: int = 20,
    keep: np.ndarray | None = None,
    segments: tuple[int, ...] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    if segments is not None:
        if not segments or any(type(n) is not int or n <= 0 for n in segments) or sum(segments) != len(embeddings):
            raise ValueError("Invalid immutable retrieval segments")
        if keep is not None and keep.shape[0] != len(embeddings):
            return np.array([], dtype=np.int64), np.array([], dtype=np.float32)
        indices, values, offset = [], [], 0
        for count in segments:
            idx, score = top_k(embeddings[offset:offset + count], query, k,
                               None if keep is None else keep[offset:offset + count])
            indices.extend((idx + offset).tolist())
            values.extend(score.tolist())
            offset += count
        # Preserve each immutable parent's tie order. An appended reference
        # can win on a higher score, but cannot reorder equally scored parents.
        order = np.argsort(-np.asarray(values, dtype=np.float32), kind="stable")[:k]
        return np.asarray(indices, dtype=np.int64)[order], np.asarray(values, dtype=np.float32)[order]
    scores = embeddings @ query.astype(np.float32)
    if keep is not None:
        if keep.shape[0] != scores.shape[0] or not np.any(keep):
            return np.array([], dtype=np.int64), np.array([], dtype=np.float32)
        scores = np.where(keep, scores, np.float32("-inf"))
    finite = np.isfinite(scores)
    available = int(finite.sum())
    if available <= 0:
        return np.array([], dtype=np.int64), np.array([], dtype=np.float32)
    k = min(k, available, scores.shape[0])
    idx = np.argpartition(-scores, k - 1)[:k]
    idx = idx[np.argsort(-scores[idx])]
    return idx, scores[idx]
