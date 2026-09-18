from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

import numpy as np
from PIL import Image

from app.db import connect
from app.recognition.artifacts import sha256_file, validate_embeddings
from app.recognition.embed import DinoEmbedder
from bootstrap.pins import DINOV2_DIM, DINOV2_FILENAME


def read_model_revision(data_dir: Path) -> str:
    for candidate in (
        data_dir / "vectors" / "pad" / "ACTIVE",
        data_dir / "vectors" / "pad" / "manifest.json",
    ):
        if candidate.name == "ACTIVE" and candidate.is_file():
            bundle = data_dir / "vectors" / "pad" / candidate.read_text().strip()
            manifest = bundle / "manifest.json"
            if manifest.is_file():
                return str(json.loads(manifest.read_text())["model_revision"])
        if candidate.name == "manifest.json" and candidate.is_file():
            return str(json.loads(candidate.read_text())["model_revision"])
    raise SystemExit("No existing pad snapshot. Run a full bootstrap first.")


def reference_fingerprint(rows: list) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(str(row["id"]).encode())
        path = Path(str(row["image_path"]))
        digest.update(sha256_file(path).encode() if path.is_file() else b"missing")
    return digest.hexdigest()


def _write_active(root: Path, name: str) -> None:
    tmp = root / f".ACTIVE.{os.getpid()}"
    tmp.write_text(name)
    tmp.replace(root / "ACTIVE")


def build_embeddings(
    data_dir: Path,
    preprocess_config: str,
    model_revision: str,
    *,
    force: bool = False,
) -> None:
    catalog = connect(data_dir / "catalog.sqlite")
    rows = catalog.execute(
        "SELECT id, image_path FROM cards WHERE has_image = 1 AND image_path IS NOT NULL ORDER BY id"
    ).fetchall()
    catalog.close()
    if not rows:
        raise RuntimeError("No reference images available to embed")

    fingerprint = reference_fingerprint(rows)
    root = data_dir / "vectors" / preprocess_config
    active_path = root / "ACTIVE"
    if not force and active_path.is_file():
        current = root / active_path.read_text().strip() / "manifest.json"
        if current.is_file():
            manifest = json.loads(current.read_text())
            if (
                manifest.get("image_fingerprint") == fingerprint
                and manifest.get("model_revision") == model_revision
                and manifest.get("preprocess_config") == preprocess_config
            ):
                print(f"skip embeddings {preprocess_config}: images and model unchanged")
                return

    model_path = data_dir / "models" / DINOV2_FILENAME
    embedder = DinoEmbedder(str(model_path), intra_threads=1, inter_threads=1)
    vectors: list[np.ndarray] = []
    ids: list[str] = []
    for index, row in enumerate(rows, start=1):
        with Image.open(row["image_path"]) as image:
            vector = embedder.embed(image.convert("RGB"), preprocess_config)
        vectors.append(vector.astype(np.float32))
        ids.append(row["id"])
        if index % 25 == 0:
            print(f"  embed {preprocess_config} {index}/{len(rows)}")

    matrix = np.stack(vectors, axis=0)
    if matrix.shape[1] != DINOV2_DIM:
        raise RuntimeError(f"Unexpected embedding dim {matrix.shape[1]}")
    validate_embeddings(matrix, np.array(ids))

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    coverage = json.loads((data_dir / "catalogue-version.json").read_text())
    name = f"{coverage['catalogue_version']}-{stamp}".replace("/", "-")
    staging = root / f".staging-{stamp}-{os.getpid()}"
    staging.mkdir(parents=True, exist_ok=True)
    embeddings_path = staging / "embeddings.npy"
    ids_path = staging / "embedding_card_ids.npy"
    np.save(embeddings_path, matrix)
    np.save(ids_path, np.array(ids))

    manifest = {
        "preprocess_config": preprocess_config,
        "use_ocr": True,
        "catalogue_version": coverage["catalogue_version"],
        "model_name": "dinov2-small",
        "model_revision": model_revision,
        "embedding_dim": int(matrix.shape[1]),
        "card_count": coverage["cards"],
        "indexed_count": int(matrix.shape[0]),
        "missing_images": coverage["missing_images"],
        "embeddings_sha256": sha256_file(embeddings_path),
        "ids_sha256": sha256_file(ids_path),
        "dinov2_sha256": sha256_file(model_path),
        "image_fingerprint": fingerprint,
        "indexed_ids": ids,
    }
    (staging / "manifest.json").write_text(json.dumps(manifest, indent=2))
    final = root / name
    if final.exists():
        shutil.rmtree(final)
    staging.rename(final)
    _write_active(root, name)
    print(f"wrote {final}")
