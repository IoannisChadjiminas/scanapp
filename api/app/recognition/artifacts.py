from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.config import Settings


class ArtifactError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class ArtifactSnapshot:
    preprocess_config: str
    use_ocr: bool
    catalogue_version: str
    model_revision: str
    model_name: str
    embedding_dim: int
    card_count: int
    indexed_count: int
    missing_images: int
    embeddings_sha256: str
    ids_sha256: str
    embeddings: np.ndarray
    card_ids: np.ndarray
    manifest: dict

    @property
    def snapshot_name(self) -> str:
        return self.preprocess_config


def load_snapshot(settings: Settings) -> ArtifactSnapshot:
    vectors_dir = settings.vectors_dir
    manifest_path = vectors_dir / "manifest.json"
    embeddings_path = vectors_dir / "embeddings.npy"
    ids_path = vectors_dir / "embedding_card_ids.npy"
    if not manifest_path.exists() or not embeddings_path.exists() or not ids_path.exists():
        raise ArtifactError(
            f"Vector snapshot missing for {settings.snapshot_name}. Run bootstrap."
        )
    if not settings.dinov2_path.exists():
        raise ArtifactError("DINOv2 ONNX model is missing. Run bootstrap.")

    manifest = json.loads(manifest_path.read_text())
    embeddings = np.load(embeddings_path, mmap_mode="r")
    card_ids = np.load(ids_path)
    if embeddings.ndim != 2:
        raise ArtifactError("embeddings.npy must be 2-dimensional")
    if card_ids.shape[0] != embeddings.shape[0]:
        raise ArtifactError("embedding_card_ids.npy length does not match embeddings.npy")
    if embeddings.dtype != np.float32:
        raise ArtifactError("embeddings.npy must be float32")

    expected_emb = manifest.get("embeddings_sha256")
    expected_ids = manifest.get("ids_sha256")
    if expected_emb and sha256_file(embeddings_path) != expected_emb:
        raise ArtifactError("embeddings.npy checksum mismatch")
    if expected_ids and sha256_file(ids_path) != expected_ids:
        raise ArtifactError("embedding_card_ids.npy checksum mismatch")

    model_checksum = manifest.get("dinov2_sha256")
    if model_checksum and sha256_file(settings.dinov2_path) != model_checksum:
        raise ArtifactError("DINOv2 ONNX checksum mismatch")

    return ArtifactSnapshot(
        preprocess_config=manifest["preprocess_config"],
        use_ocr=bool(manifest["use_ocr"]),
        catalogue_version=str(manifest["catalogue_version"]),
        model_revision=str(manifest["model_revision"]),
        model_name=str(manifest.get("model_name", settings.model_name)),
        embedding_dim=int(manifest["embedding_dim"]),
        card_count=int(manifest.get("card_count", 0)),
        indexed_count=int(manifest.get("indexed_count", embeddings.shape[0])),
        missing_images=int(manifest.get("missing_images", 0)),
        embeddings_sha256=str(expected_emb or ""),
        ids_sha256=str(expected_ids or ""),
        embeddings=embeddings,
        card_ids=card_ids,
        manifest=manifest,
    )
