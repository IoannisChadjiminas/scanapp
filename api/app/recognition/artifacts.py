from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.config import Settings
from app.db import connect


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
    bundle_dir: Path

    @property
    def snapshot_name(self) -> str:
        return self.preprocess_config


def validate_embeddings(embeddings: np.ndarray, card_ids: np.ndarray) -> None:
    if embeddings.ndim != 2:
        raise ArtifactError("embeddings.npy must be 2-dimensional")
    if card_ids.shape[0] != embeddings.shape[0]:
        raise ArtifactError("embedding_card_ids.npy length does not match embeddings.npy")
    if embeddings.dtype != np.float32:
        raise ArtifactError("embeddings.npy must be float32")
    if not np.isfinite(embeddings).all():
        raise ArtifactError("embeddings contain non-finite values")
    unique = set(str(item) for item in card_ids.tolist())
    if len(unique) != int(card_ids.shape[0]):
        raise ArtifactError("embedding_card_ids.npy contains duplicate ids")
    norms = np.linalg.norm(embeddings, axis=1)
    if norms.size and float(np.max(np.abs(norms - 1.0))) > 1e-2:
        raise ArtifactError("embeddings are not L2-normalized")


def resolve_bundle_dir(vectors_dir: Path) -> Path:
    active = vectors_dir / "ACTIVE"
    if active.is_file():
        name = active.read_text().strip()
        bundle = vectors_dir / name
        if bundle.is_dir():
            return bundle
    return vectors_dir


def load_snapshot(settings: Settings) -> ArtifactSnapshot:
    vectors_dir = settings.vectors_dir
    bundle = resolve_bundle_dir(vectors_dir)
    manifest_path = bundle / "manifest.json"
    embeddings_path = bundle / "embeddings.npy"
    ids_path = bundle / "embedding_card_ids.npy"
    if not manifest_path.exists() or not embeddings_path.exists() or not ids_path.exists():
        raise ArtifactError(
            f"Vector snapshot missing for {settings.snapshot_name}. Run bootstrap."
        )
    if not settings.dinov2_path.exists():
        raise ArtifactError("DINOv2 ONNX model is missing. Run bootstrap.")

    manifest = json.loads(manifest_path.read_text())
    if str(manifest.get("preprocess_config") or "") != settings.preprocess_config:
        raise ArtifactError("Vector snapshot preprocess_config does not match settings")
    embeddings = np.load(embeddings_path, mmap_mode="r")
    card_ids = np.load(ids_path)
    validate_embeddings(np.asarray(embeddings), card_ids)
    expected_dim = int(manifest.get("embedding_dim") or 0)
    if expected_dim and embeddings.shape[1] != expected_dim:
        raise ArtifactError("embedding dimension does not match the snapshot manifest")

    expected_emb = manifest.get("embeddings_sha256")
    expected_ids = manifest.get("ids_sha256")
    if expected_emb and sha256_file(embeddings_path) != expected_emb:
        raise ArtifactError("embeddings.npy checksum mismatch")
    if expected_ids and sha256_file(ids_path) != expected_ids:
        raise ArtifactError("embedding_card_ids.npy checksum mismatch")

    model_checksum = manifest.get("dinov2_sha256")
    if model_checksum and sha256_file(settings.dinov2_path) != model_checksum:
        raise ArtifactError("DINOv2 ONNX checksum mismatch")

    catalog_path = settings.catalog_sqlite
    if catalog_path.is_file():
        conn = connect(catalog_path)
        present = {
            str(row["id"])
            for row in conn.execute("SELECT id FROM cards WHERE has_image = 1")
        }
        conn.close()
        missing = [str(card_id) for card_id in card_ids.tolist() if str(card_id) not in present]
        if missing:
            raise ArtifactError("Vector snapshot ids are missing from the catalogue")

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
        bundle_dir=bundle,
    )
