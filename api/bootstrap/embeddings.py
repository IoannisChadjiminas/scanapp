from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from app.db import connect
from app.recognition.artifacts import sha256_file
from app.recognition.embed import DinoEmbedder
from bootstrap.pins import DINOV2_DIM, DINOV2_FILENAME


def build_embeddings(data_dir: Path, preprocess_config: str, model_revision: str) -> None:
    catalog = connect(data_dir / "catalog.sqlite")
    rows = catalog.execute(
        "SELECT id, image_path FROM cards WHERE has_image = 1 AND image_path IS NOT NULL ORDER BY id"
    ).fetchall()
    catalog.close()
    if not rows:
        raise RuntimeError("No reference images available to embed")

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
    out_dir = data_dir / "vectors" / preprocess_config
    out_dir.mkdir(parents=True, exist_ok=True)
    embeddings_path = out_dir / "embeddings.npy"
    ids_path = out_dir / "embedding_card_ids.npy"
    np.save(embeddings_path, matrix)
    np.save(ids_path, np.array(ids))

    coverage = json.loads((data_dir / "catalogue-version.json").read_text())
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
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {out_dir}")
