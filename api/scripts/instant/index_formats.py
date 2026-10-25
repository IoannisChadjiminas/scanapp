"""Phone-style card index formats (fp32, fp16, int8) and brute-force search.

The index is one row per catalogue card (384-dim DINOv2 vectors). Duplicate
rows for the same catalogue card (for example `base1-1` and `en:base1-1`) carry
the same `group` key, so search collapses them before ranking.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DIM = 384
FORMATS = ("fp32", "fp16", "int8")
INT8_MAX = 127


@dataclass(frozen=True)
class Hit:
    group: str
    row: int
    score: float


@dataclass(frozen=True)
class CardIndex:
    fmt: str
    ids: tuple[str, ...]
    groups: tuple[str, ...]
    group_codes: np.ndarray  # int32, one per row, index into `group_names`
    group_names: tuple[str, ...]
    matrix: np.ndarray  # float32 / float16 rows, or int8 rows
    row_scales: np.ndarray | None  # float32 per row, int8 only

    @property
    def count(self) -> int:
        return len(self.ids)

    def nbytes(self) -> int:
        size = self.matrix.nbytes
        if self.row_scales is not None:
            size += self.row_scales.nbytes
        return size


def normalize_rows(vectors: np.ndarray) -> np.ndarray:
    values = np.asarray(vectors, dtype=np.float32)
    if values.ndim != 2 or values.shape[1] != DIM:
        raise ValueError(f"expected (N, {DIM}) vectors, got {values.shape}")
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("zero-length vector in index")
    return values / norms


def quantize_int8(vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Symmetric per-row int8. Each row keeps its own scale (max-abs / 127)."""
    values = np.asarray(vectors, dtype=np.float32)
    peak = np.max(np.abs(values), axis=1)
    scales = np.where(peak > 0, peak / INT8_MAX, 1.0).astype(np.float32)
    quantized = np.clip(np.rint(values / scales[:, None]), -INT8_MAX, INT8_MAX).astype(np.int8)
    return quantized, scales


def build_index(
    fmt: str,
    vectors: np.ndarray,
    ids: list[str] | tuple[str, ...],
    groups: list[str] | tuple[str, ...],
) -> CardIndex:
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {fmt!r}")
    if len(ids) != len(vectors) or len(groups) != len(vectors):
        raise ValueError("ids, groups and vectors must have the same length")
    unit = normalize_rows(vectors)
    group_names = tuple(dict.fromkeys(groups))
    position = {name: code for code, name in enumerate(group_names)}
    codes = np.asarray([position[name] for name in groups], dtype=np.int32)
    if fmt == "fp32":
        matrix, scales = unit.copy(), None
    elif fmt == "fp16":
        matrix, scales = unit.astype(np.float16), None
    else:
        matrix, scales = quantize_int8(unit)
    return CardIndex(
        fmt=fmt,
        ids=tuple(ids),
        groups=tuple(groups),
        group_codes=codes,
        group_names=group_names,
        matrix=matrix,
        row_scales=scales,
    )


def quantize_query_int8(query: np.ndarray) -> tuple[np.ndarray, float]:
    unit = normalize_rows(np.asarray(query, dtype=np.float32).reshape(1, -1))
    quantized, scales = quantize_int8(unit)
    return quantized[0], float(scales[0])


def row_scores(index: CardIndex, query: np.ndarray) -> np.ndarray:
    """Cosine-like score for every row. `query` is a unit-length (384,) vector."""
    if index.fmt == "fp32":
        return index.matrix @ query.astype(np.float32)
    if index.fmt == "fp16":
        return index.matrix.astype(np.float32) @ query.astype(np.float32)
    query_int, query_scale = quantize_query_int8(query)
    accumulated = np.empty(index.count, dtype=np.float32)
    chunk = 8192
    query_wide = query_int.astype(np.int32)
    for start in range(0, index.count, chunk):
        block = index.matrix[start:start + chunk].astype(np.int32)
        accumulated[start:start + chunk] = block @ query_wide
    return accumulated * index.row_scales * np.float32(query_scale)


def _collapse(index: CardIndex, scores: np.ndarray, rows: np.ndarray, k: int) -> list[Hit]:
    hits: list[Hit] = []
    seen: set[int] = set()
    for row in rows.tolist():
        code = int(index.group_codes[row])
        if code in seen:
            continue
        seen.add(code)
        hits.append(Hit(group=index.group_names[code], row=row, score=float(scores[row])))
        if len(hits) == k:
            break
    return hits


def rank_groups(index: CardIndex, scores: np.ndarray, k: int = 5) -> list[Hit]:
    """Best row per catalogue group, highest score first, at most k groups."""
    if scores.shape[0] != index.count:
        raise ValueError("scores do not match the index")
    pool = min(index.count, max(64, 8 * k))
    if pool < index.count:
        top = np.argpartition(-scores, pool - 1)[:pool]
        top = top[np.argsort(-scores[top], kind="stable")]
        hits = _collapse(index, scores, top, k)
        if len(hits) == k:
            return hits
    # Fewer than k groups in the pool (heavy duplication) or a small index: full sort.
    return _collapse(index, scores, np.argsort(-scores, kind="stable"), k)


def search(index: CardIndex, query: np.ndarray, k: int = 5) -> list[Hit]:
    return rank_groups(index, row_scores(index, query), k)


def margin(hits: list[Hit]) -> float:
    """Top-1 minus the best score of a different catalogue group."""
    if len(hits) < 2:
        return float("inf") if hits else 0.0
    return hits[0].score - hits[1].score
