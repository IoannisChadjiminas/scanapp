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


def _active_bundle(root: Path) -> Path | None:
    active_path = root / "ACTIVE"
    if not active_path.is_file():
        return None
    bundle = root / active_path.read_text().strip()
    if (
        bundle.is_dir()
        and (bundle / "embeddings.npy").is_file()
        and (bundle / "embedding_card_ids.npy").is_file()
        and (bundle / "manifest.json").is_file()
    ):
        return bundle
    return None


def _reusable_vectors(
    bundle: Path,
    *,
    preprocess_config: str,
    model_revision: str,
) -> dict[str, np.ndarray] | None:
    manifest = json.loads((bundle / "manifest.json").read_text())
    if (
        manifest.get("preprocess_config") != preprocess_config
        or manifest.get("model_revision") != model_revision
    ):
        return None
    embeddings = np.load(bundle / "embeddings.npy")
    card_ids = np.load(bundle / "embedding_card_ids.npy")
    if embeddings.ndim != 2 or embeddings.shape[0] != card_ids.shape[0]:
        return None
    reused: dict[str, np.ndarray] = {}
    for index, card_id in enumerate(card_ids.tolist()):
        reused[str(card_id)] = np.asarray(embeddings[index], dtype=np.float32)
    return reused


def _write_snapshot(
    *,
    data_dir: Path,
    root: Path,
    preprocess_config: str,
    model_revision: str,
    model_path: Path,
    fingerprint: str,
    matrix: np.ndarray,
    ids: list[str],
) -> Path:
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
    return final


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
    bundle = _active_bundle(root)
    if not force and bundle is not None:
        manifest = json.loads((bundle / "manifest.json").read_text())
        if (
            manifest.get("image_fingerprint") == fingerprint
            and manifest.get("model_revision") == model_revision
            and manifest.get("preprocess_config") == preprocess_config
        ):
            print(f"skip embeddings {preprocess_config}: images and model unchanged")
            return

    reused: dict[str, np.ndarray] = {}
    if not force and bundle is not None:
        loaded = _reusable_vectors(
            bundle,
            preprocess_config=preprocess_config,
            model_revision=model_revision,
        )
        if loaded:
            reused = loaded

    to_embed = [row for row in rows if str(row["id"]) not in reused]
    print(
        f"{preprocess_config}: reuse {len(rows) - len(to_embed)}, "
        f"embed {len(to_embed)} of {len(rows)}"
    )
    fresh: dict[str, np.ndarray] = {}
    model_path = data_dir / "models" / DINOV2_FILENAME
    if to_embed:
        embedder = DinoEmbedder(str(model_path), intra_threads=1, inter_threads=1)
        for index, row in enumerate(to_embed, start=1):
            with Image.open(row["image_path"]) as image:
                vector = embedder.embed(image.convert("RGB"), preprocess_config)
            fresh[str(row["id"])] = vector.astype(np.float32)
            if index % 25 == 0 or index == len(to_embed):
                print(f"  embed {preprocess_config} {index}/{len(to_embed)}")

    ids: list[str] = []
    vectors: list[np.ndarray] = []
    for row in rows:
        card_id = str(row["id"])
        vector = fresh.get(card_id, reused.get(card_id))
        if vector is None:
            raise RuntimeError(f"Missing embedding for {card_id}")
        ids.append(card_id)
        vectors.append(vector)
    matrix = np.stack(vectors, axis=0)
    _write_snapshot(
        data_dir=data_dir,
        root=root,
        preprocess_config=preprocess_config,
        model_revision=model_revision,
        model_path=model_path,
        fingerprint=fingerprint,
        matrix=matrix,
        ids=ids,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Rebuild DINOv2 vectors from downloaded reference images. "
            "Reuses existing vectors and only embeds new cards. Does not fetch TCGdex."
        )
    )
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR", "/data"))
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild every vector instead of only new cards.",
    )
    parser.add_argument(
        "--preprocess",
        default="pad,square",
        help="Comma-separated preprocess configs. Default: pad,square.",
    )
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    revision = read_model_revision(data_dir)
    modes = [item.strip() for item in args.preprocess.split(",") if item.strip()]
    for preprocess in modes:
        print(f"== embeddings {preprocess}")
        build_embeddings(data_dir, preprocess, revision, force=args.force)
    print("embeddings complete")


if __name__ == "__main__":
    main()
