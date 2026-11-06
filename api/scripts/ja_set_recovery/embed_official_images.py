"""Build an isolated DINOv2 review-vector bundle from approved image inputs.

This does not modify the application catalogue or its active vector snapshot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from app.recognition.artifacts import validate_embeddings
from app.recognition.embed import DinoEmbedder


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--preprocess", default="pad", choices=("pad", "square"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = json.loads(args.input_manifest.read_text())
    records = source["records"]
    if not records:
        raise SystemExit("Input manifest has no image records")
    args.output.mkdir(parents=True, exist_ok=False)

    embedder = DinoEmbedder(str(args.model), 1, 1)
    vectors: list[np.ndarray] = []
    ids: list[str] = []
    output_records: list[dict] = []
    for record in records:
        image_path = Path(record["file"])
        if not image_path.is_file() or sha256(image_path) != record["sha256"]:
            raise ValueError(f"Input image missing or changed: {image_path}")
        with Image.open(image_path) as opened:
            image = opened.convert("RGB")
        vector = embedder.embed(image, args.preprocess)
        if vector.shape != (384,) or not np.isfinite(vector).all():
            raise ValueError(f"Invalid DINOv2 vector for {image_path}: {vector.shape}")
        norm = float(np.linalg.norm(vector))
        if not 0.999 <= norm <= 1.001:
            raise ValueError(f"Unexpected vector norm {norm} for {image_path}")
        code = str(record.get("set_code") or "").strip()
        printed = str(record.get("printed_number") or "").strip()
        if code and printed:
            local_number = printed.split("/", 1)[0]
            provider_id = f"{code}-{local_number}"
        else:
            provider_id = f"{record['group_id']}-ENERGY-{record['card_id']}"
        vector_id = f"ja:{provider_id}"
        ids.append(vector_id)
        vectors.append(vector.astype(np.float32, copy=False))
        output_records.append({
            "vector_id": vector_id,
            "provider_id": provider_id,
            "group_id": record["group_id"],
            "card_id": record["card_id"],
            "set_code": record.get("set_code", ""),
            "printed_number": record.get("printed_number", ""),
            "official_name_ja": record.get("official_name_ja", ""),
            "checklist_match": bool(record.get("checklist_match")),
            "image_file": str(image_path),
            "image_sha256": record["sha256"],
        })
        if len(vectors) % 20 == 0:
            print(f"embedded {len(vectors)}/{len(records)}", flush=True)

    matrix = np.stack(vectors).astype(np.float32, copy=False)
    id_array = np.asarray(ids)
    validate_embeddings(matrix, id_array)
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate vector IDs")
    vectors_path = args.output / "embeddings.npy"
    ids_path = args.output / "embedding_ids.npy"
    records_path = args.output / "records.json"
    np.save(vectors_path, matrix)
    np.save(ids_path, id_array)
    records_path.write_text(json.dumps(output_records, ensure_ascii=False, indent=2) + "\n")
    manifest = {
        "status": "isolated_review_bundle_not_active_catalogue",
        "preprocess_config": args.preprocess,
        "model_name": "dinov2-small",
        "model_revision": args.model_revision,
        "model_sha256": sha256(args.model),
        "embedding_dim": 384,
        "vector_count": len(ids),
        "checklist_matched_vectors": sum(r["checklist_match"] for r in output_records),
        "source_image_manifest": str(args.input_manifest),
        "source_image_manifest_sha256": sha256(args.input_manifest),
        "embeddings_sha256": sha256(vectors_path),
        "ids_sha256": sha256(ids_path),
        "records_sha256": sha256(records_path),
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
