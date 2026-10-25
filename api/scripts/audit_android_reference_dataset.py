#!/usr/bin/env python3
"""Audit exported catalogue vectors against local reference-image bytes."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath

import numpy as np
from PIL import Image


IMAGE_PREFIX = "/data/reference-images/"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_image_path(raw: str | None) -> str | None:
    if not raw or not raw.startswith(IMAGE_PREFIX):
        return None
    relative = PurePosixPath(raw[len(IMAGE_PREFIX):])
    if relative.is_absolute() or ".." in relative.parts:
        return None
    return relative.as_posix()


def alias_image_paths(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text())
    result: dict[str, str] = {}
    for card_id, owner in value.items():
        if isinstance(owner, str):
            try:
                owner = ast.literal_eval(owner)
            except (ValueError, SyntaxError):
                continue
        if isinstance(owner, dict):
            relative = relative_image_path(owner.get("image_path"))
            if relative:
                result[str(card_id)] = relative
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    root = args.dataset.resolve()
    catalogue = root / "catalogue"
    image_root = root / "reference-images"
    db_path = catalogue / "catalog.sqlite"
    vector_dir = catalogue / "vectors" / "pad"
    if not db_path.is_file() or not image_root.is_dir():
        parser.error("dataset must contain catalogue/catalog.sqlite and reference-images/")

    manifest = json.loads((vector_dir / "manifest.json").read_text())
    vector_ids = np.load(vector_dir / "embedding_card_ids.npy", allow_pickle=False)
    embeddings = np.load(vector_dir / "embeddings.npy", mmap_mode="r", allow_pickle=False)
    vector_id_set = {str(value) for value in vector_ids.tolist()}
    if len(vector_id_set) != len(vector_ids):
        raise SystemExit("vector ID array contains duplicates")
    if embeddings.ndim != 2 or embeddings.shape[0] != len(vector_ids):
        raise SystemExit("vector matrix and ID count do not match")

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    cards = [dict(row) for row in connection.execute(
        "SELECT id,language,set_id,collector_number,printed_collector_number,image_path,"
        "remote_image_url,has_image FROM cards ORDER BY id")]
    connection.close()
    aliases = alias_image_paths(catalogue / "visual_image_aliases.json")

    file_records: dict[str, dict] = {}
    dimension_buckets: Counter[str] = Counter()
    decode_errors: list[dict[str, str]] = []
    duplicate_hashes: dict[str, list[str]] = defaultdict(list)
    total_bytes = 0
    for path in sorted(image_root.rglob("*")):
        if not path.is_file() or path.is_symlink() or path.name.startswith("._"):
            continue
        relative = path.relative_to(image_root).as_posix()
        size = path.stat().st_size
        total_bytes += size
        digest = sha256_file(path)
        width = height = None
        error = None
        try:
            with Image.open(path) as image:
                image.verify()
                width, height = image.size
            if not width or not height:
                raise ValueError("empty image dimensions")
            long_edge = max(width, height)
            bucket = (
                "<128" if long_edge < 128 else "128-255" if long_edge < 256
                else "256-511" if long_edge < 512 else "512-999" if long_edge < 1000
                else ">=1000"
            )
            dimension_buckets[bucket] += 1
        except Exception as exc:  # record corrupt/unreadable source rather than aborting the audit
            error = type(exc).__name__
            decode_errors.append({"path": relative, "error": error})
        file_records[relative] = {
            "sha256": digest,
            "bytes": size,
            "width": width,
            "height": height,
            "decode_error": error,
        }
        duplicate_hashes[digest].append(relative)

    by_language: dict[str, Counter[str]] = defaultdict(Counter)
    card_records: list[dict] = []
    missing_files: list[str] = []
    alias_fallbacks = 0
    readable_indexed = 0
    referenced_paths: set[str] = set()
    card_hashes: dict[str, list[str]] = defaultdict(list)
    card_dimension_buckets: Counter[str] = Counter()
    for card in cards:
        card_id = str(card["id"])
        language = str(card["language"] or "en")
        has_image = bool(card["has_image"])
        by_language[language]["cards"] += 1
        by_language[language]["has_image"] += int(has_image)
        by_language[language]["vector"] += int(card_id in vector_id_set)
        raw_path = card["image_path"]
        relative = relative_image_path(raw_path)
        used_alias = False
        if has_image and (relative is None or relative not in file_records) and card_id in aliases:
            relative = aliases[card_id]
            used_alias = True
            alias_fallbacks += 1
        record = file_records.get(relative) if relative else None
        readable = bool(record and record["decode_error"] is None)
        if has_image and not record:
            missing_files.append(card_id)
        if has_image and readable:
            readable_indexed += 1
            referenced_paths.add(relative)
            card_hashes[record["sha256"]].append(card_id)
            long_edge = max(record["width"], record["height"])
            card_dimension_buckets[
                "<128" if long_edge < 128 else "128-255" if long_edge < 256
                else "256-511" if long_edge < 512 else "512-999" if long_edge < 1000
                else ">=1000"
            ] += 1
        by_language[language]["readable"] += int(has_image and readable)
        by_language[language]["missing_file"] += int(has_image and not record)
        by_language[language]["decode_error"] += int(has_image and bool(record and record["decode_error"]))
        card_records.append({
            "id": card_id,
            "language": language,
            "set_id": card["set_id"],
            "collector_number": card["collector_number"],
            "printed_collector_number": card["printed_collector_number"],
            "image_path": raw_path,
            "resolved_image_path": relative,
            "used_visual_alias": used_alias,
            "has_image": has_image,
            "has_teacher_vector": card_id in vector_id_set,
            "sha256": record["sha256"] if record else None,
            "width": record["width"] if record else None,
            "height": record["height"] if record else None,
            "decode_error": record["decode_error"] if record else None,
            "unavailable_reason": (
                None if readable else "catalogue_has_image_false" if not has_image
                else "image_path_outside_reference_root" if relative is None
                else "reference_file_missing" if not record
                else f"image_decode_failed:{record['decode_error']}"
            ),
            "provenance": "staging_reference_image_volume",
        })

    card_ids = {str(card["id"]) for card in cards}
    duplicate_groups = [paths for paths in duplicate_hashes.values() if len(paths) > 1]
    duplicate_card_groups = [ids for ids in card_hashes.values() if len(ids) > 1]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    records_path = args.out.with_suffix(".records.jsonl")
    with records_path.open("w") as stream:
        for record in card_records:
            stream.write(json.dumps(record, sort_keys=True) + "\n")

    summary = {
        "schema_version": 1,
        "source_import_id": manifest.get("exported_from", {}).get("import_id"),
        "source_schema": manifest.get("exported_from", {}).get("schema"),
        "catalogue_sha256": sha256_file(db_path),
        "vector_manifest_sha256": sha256_file(vector_dir / "manifest.json"),
        "visual_aliases_sha256": sha256_file(catalogue / "visual_image_aliases.json"),
        "catalogue_version": manifest.get("catalogue_version"),
        "catalogue_cards": len(cards),
        "catalogue_has_image": sum(bool(card["has_image"]) for card in cards),
        "catalogue_teacher_vectors": len(vector_id_set),
        "image_marked_without_teacher_vector": sum(
            bool(card["has_image"]) and str(card["id"]) not in vector_id_set for card in cards
        ),
        "vector_manifest_indexed_count": manifest.get("indexed_count"),
        "vector_embedding_dim": int(embeddings.shape[1]),
        "vector_ids_sha256": manifest.get("exported_from", {}).get("cloud_ids_sha256"),
        "vector_embeddings_sha256": manifest.get("exported_from", {}).get("cloud_embeddings_sha256"),
        "orphan_vector_ids": len(vector_id_set - card_ids),
        "reference_image_file_count": len(file_records),
        "referenced_image_file_count": len(referenced_paths),
        "unreferenced_image_file_count": len(set(file_records) - referenced_paths),
        "reference_image_total_bytes": total_bytes,
        "readable_indexed_cards": readable_indexed,
        "readable_indexed_rate": readable_indexed / max(1, sum(bool(card["has_image"]) for card in cards)),
        "unique_readable_card_image_hashes": len(card_hashes),
        "duplicate_readable_card_image_hash_groups": len(duplicate_card_groups),
        "duplicate_readable_card_id_count": sum(len(group) for group in duplicate_card_groups),
        "missing_reference_files": len(missing_files),
        "decode_errors": len(decode_errors),
        "visual_alias_fallbacks": alias_fallbacks,
        "unique_image_sha256_count": len(duplicate_hashes),
        "duplicate_image_hash_groups": len(duplicate_groups),
        "duplicate_image_file_count": sum(len(group) for group in duplicate_groups),
        "long_edge_dimension_buckets": dict(dimension_buckets),
        "readable_card_long_edge_dimension_buckets": dict(card_dimension_buckets),
        "languages": {language: dict(counts) for language, counts in sorted(by_language.items())},
        "missing_file_card_ids": missing_files,
        "decode_errors_sample": decode_errors[:100],
        "records_file": records_path.name,
    }
    args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value for key, value in summary.items()
                      if key not in {"missing_file_card_ids", "decode_errors_sample"}},
                     sort_keys=True))


if __name__ == "__main__":
    main()
