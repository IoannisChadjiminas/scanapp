"""Lossless reference-side features. Upload-side extraction stays unchanged.

Bundles are immutable, opt-in and catalogue-bound. They contain no test-photo
features. Missing references retain their original incomplete-evidence state;
corrupt/configuration-mismatched bundles never silently use image fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import platform
from pathlib import Path
import re
from zipfile import BadZipFile
from collections import OrderedDict
from threading import RLock

import cv2
import numpy as np
from PIL import Image, __version__ as pillow_version

from app.recognition.artifacts import ArtifactError, sha256_file

SCHEMA_VERSION = "reference-features-v1"
SIFT_PROFILES = ((1000, .04), (2000, .02))


def processing_contract() -> dict:
    # Imported lazily to avoid a cycle with the two consumers.
    from app.recognition.local_match import FULL_ART_BOX, FULL_ART_RARITIES
    from app.recognition.printing import ART_BOX
    return dict(opencv=cv2.__version__, pillow=pillow_version,
                architecture=platform.machine(), numpy=np.__version__,
                opencv_build_sha256=hashlib.sha256(cv2.getBuildInformation().encode()).hexdigest(),
                pixel_size=720, pixel_conversion="RGB-to-OpenCV-gray-LANCZOS",
                mask_inset=8, sift_profiles=[list(p) for p in SIFT_PROFILES],
                standard_box=list(ART_BOX), full_art_box=list(FULL_ART_BOX),
                full_art_rarities=sorted(FULL_ART_RARITIES),
                thumbnail="printing-artwork-thumbnail-v1-64x32-BILINEAR-float32")


def catalogue_signature(rows: list[dict]) -> str:
    # The path binds features to the catalogue's actual image mapping. No image
    # files need to exist when validating/reading a completed bundle.
    values = sorted((str(r["id"]), str(r.get("image_path") or ""),
                     str(r.get("rarity") or "").casefold()) for r in rows)
    return hashlib.sha256(json.dumps(values, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class ReferenceFeatures:
    points: np.ndarray
    descriptors: np.ndarray | None
    size: tuple[int, int]


def extract_reference(image: Image.Image, art_box: tuple,
                      features: int, contrast: float) -> ReferenceFeatures:
    from app.recognition.local_match import _pixels
    pixels = _pixels(image)
    height, width = pixels.shape
    mask = np.zeros_like(pixels)
    x0, y0, x1, y1 = art_box
    mask[round(y0*height)+8:round(y1*height)-8,
         round(x0*width)+8:round(x1*width)-8] = 255
    keys, descriptors = cv2.SIFT_create(
        nfeatures=features, contrastThreshold=contrast).detectAndCompute(pixels, mask)
    points = np.float32([key.pt for key in keys]).reshape(-1, 2)
    return ReferenceFeatures(points, descriptors, (width, height))


def build_reference_bundle(rows: list[dict], data_dir: Path, output: Path,
                           progress=None, workers: int = 1) -> dict:
    """Offline builder; new directory only, no source catalogue/image writes."""
    from app.recognition.local_match import FULL_ART_BOX, FULL_ART_RARITIES
    from app.recognition.printing import ART_BOX, artwork_thumbnail
    if not 1 <= workers <= 8:
        raise ValueError("Feature build workers must be between 1 and 8")
    if len({str(r['id']) for r in rows}) != len(rows):
        raise ValueError("Duplicate catalogue card ID")
    output.mkdir(parents=True, exist_ok=False)
    root = (data_dir / "reference-images").resolve()
    records = {}
    def build_record(row):
        card_id = str(row["id"])
        raw_path = str(row.get("image_path") or "")
        path = Path(raw_path).resolve()
        box = FULL_ART_BOX if str(row.get("rarity") or "").casefold() in FULL_ART_RARITIES else ART_BOX
        record = dict(image_path=raw_path, art_box=list(box), available=False)
        if path.is_relative_to(root) and path.is_file():
            try:
                source_hash = sha256_file(path)
                with Image.open(path) as original:
                    thumbnail = artwork_thumbnail(original)
                    arrays = {"thumbnail": thumbnail if thumbnail is not None else np.empty(0, np.float32)}
                    for features, contrast in SIFT_PROFILES:
                        reference = extract_reference(original, box, features, contrast)
                        arrays[f"points_{features}"] = reference.points
                        arrays[f"descriptors_{features}"] = (reference.descriptors if reference.descriptors is not None
                                                               else np.empty((0, 128), np.float32))
                        arrays[f"size_{features}"] = np.asarray(reference.size, dtype=np.int32)
                if sha256_file(path) != source_hash:
                    raise ArtifactError("Reference image changed during bundle build")
            except (OSError, ValueError, cv2.error):
                # Exactly the legacy unavailable-reference behaviour. Explicit
                # entries prevent incomplete coverage masquerading as full.
                record["unavailable_reason"] = "unreadable_reference"
            else:
                filename = hashlib.sha256(card_id.encode()).hexdigest() + ".npz"
                np.savez_compressed(output / filename, **arrays)
                record.update(available=True, filename=filename,
                              sha256=sha256_file(output / filename), source_sha256=source_hash)
        return card_id, record
    ordered = sorted(rows, key=lambda r: str(r['id']))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        # Bound queued work and memory independently of catalogue size.
        for start in range(0, len(ordered), 512):
            for number, (card_id, record) in enumerate(pool.map(build_record, ordered[start:start+512]), start+1):
                records[card_id] = record
                if progress:
                    progress(number, len(rows))
    manifest = dict(schema_version=SCHEMA_VERSION, processing=processing_contract(),
                    catalogue_sha256=catalogue_signature(rows), records=records,
                    cards=len(records), available=sum(r["available"] for r in records.values()))
    # Published last. A partial build cannot be activated.
    (output / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2))
    return manifest


class ReferenceFeatureStore:
    def __init__(self, directory: Path, manifest: dict) -> None:
        self.directory = directory
        self.manifest = manifest
        self._arrays = OrderedDict()
        self._arrays_bytes = 0
        self._arrays_limit = 16 * 1024 * 1024
        self._arrays_lock = RLock()

    @classmethod
    def load(cls, directory: Path, rows: list[dict]) -> "ReferenceFeatureStore":
        try:
            manifest = json.loads((directory / "manifest.json").read_text())
            if manifest["schema_version"] != SCHEMA_VERSION or manifest["processing"] != processing_contract():
                raise ArtifactError("Reference-feature processing contract mismatch")
            if manifest["catalogue_sha256"] != catalogue_signature(rows):
                raise ArtifactError("Reference-feature catalogue/image mapping mismatch")
            records = manifest["records"]
            if set(records) != {str(r["id"]) for r in rows} or manifest["cards"] != len(rows):
                raise ArtifactError("Reference-feature catalogue coverage mismatch")
            from app.recognition.local_match import FULL_ART_BOX, FULL_ART_RARITIES
            from app.recognition.printing import ART_BOX
            for row in rows:
                record = records[str(row["id"])]
                box = FULL_ART_BOX if str(row.get("rarity") or "").casefold() in FULL_ART_RARITIES else ART_BOX
                if record["image_path"] != str(row.get("image_path") or "") or record["art_box"] != list(box):
                    raise ArtifactError("Reference-feature record mapping/profile mismatch")
                if not isinstance(record["available"], bool):
                    raise ArtifactError("Invalid reference-feature availability")
                if record["available"]:
                    expected_name = hashlib.sha256(str(row["id"]).encode()).hexdigest() + ".npz"
                    if record["filename"] != expected_name or not re.fullmatch(r"[a-f0-9]{64}", record["sha256"]):
                        raise ArtifactError("Unsafe reference-feature record")
                    if not re.fullmatch(r"[a-f0-9]{64}", record["source_sha256"]):
                        raise ArtifactError("Missing reference-feature source provenance")
                    path = directory / expected_name
                    if path.is_symlink() or not path.is_file():
                        raise ArtifactError("Missing reference-feature file")
                    if sha256_file(path) != record['sha256']:
                        raise ArtifactError("Reference-feature checksum mismatch")
            if manifest["available"] != sum(r["available"] for r in records.values()):
                raise ArtifactError("Reference-feature availability count mismatch")
            return cls(directory, manifest)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise ArtifactError("Unreadable or malformed reference-feature bundle") from exc

    def read(self, card_id: str, raw_path: str, art_box: tuple | None = None) -> dict | None:
        try:
            record = self.manifest["records"][card_id]
            if record["image_path"] != raw_path or (art_box is not None and record["art_box"] != list(art_box)):
                raise ArtifactError("Reference-feature lookup mapping/profile mismatch")
            if not record["available"]:
                return None
            path = self.directory / record["filename"]
            if path.is_symlink() or sha256_file(path) != record["sha256"]:
                raise ArtifactError("Reference-feature checksum mismatch")
            # Keep checksum verification on every access, including hits.
            # Cache only immutable decoded arrays bound to this store/record.
            with self._arrays_lock:
                key = (card_id, record['sha256'])
                if key in self._arrays:
                    self._arrays.move_to_end(key)
                    return dict(self._arrays[key][0])
            with np.load(path, allow_pickle=False) as source:
                arrays = {key: source[key] for key in source.files}
            expected = {"thumbnail"} | {f"{key}_{f}" for f, _ in SIFT_PROFILES
                                             for key in ("points", "descriptors", "size")}
            if set(arrays) != expected:
                raise ArtifactError("Reference-feature fields mismatch")
            for features, _ in SIFT_PROFILES:
                points, desc, size = (arrays[f"{key}_{features}"] for key in ("points", "descriptors", "size"))
                if (points.dtype != np.float32 or points.ndim != 2 or points.shape[1] != 2
                    or desc.dtype != np.float32 or desc.shape != (len(points), 128)
                    or size.dtype != np.int32 or size.shape != (2,) or np.any(size < 1) or np.any(size > 720)
                    or not np.isfinite(points).all() or not np.isfinite(desc).all()
                    or np.any(points < 0) or np.any(points >= size)):
                    raise ArtifactError("Invalid reference-feature geometry/descriptors")
            thumb = arrays["thumbnail"]
            if thumb.dtype != np.float32 or thumb.shape not in ((0,), (6144,)) or not np.isfinite(thumb).all():
                raise ArtifactError("Invalid reference-feature printing thumbnail")
            for array in arrays.values():
                array.flags.writeable = False
            size = sum(array.nbytes for array in arrays.values())
            if size <= self._arrays_limit:
                with self._arrays_lock:
                    if key not in self._arrays:
                        self._arrays[key] = (arrays, size)
                        self._arrays_bytes += size
                    while self._arrays_bytes > self._arrays_limit or len(self._arrays) > 64:
                        _, (_, old_size) = self._arrays.popitem(last=False)
                        self._arrays_bytes -= old_size
            return dict(arrays)
        except (OSError, ValueError, TypeError, KeyError, AttributeError, BadZipFile) as exc:
            raise ArtifactError("Unreadable or malformed reference features") from exc

    def features(self, card_id: str, raw_path: str, art_box: tuple,
                 features: int, contrast: float) -> ReferenceFeatures | None:
        if (features, contrast) not in SIFT_PROFILES:
            raise ArtifactError("Unsupported reference-feature extraction profile")
        arrays = self.read(card_id, raw_path, art_box)
        if arrays is None:
            return None
        desc = arrays[f"descriptors_{features}"]
        return ReferenceFeatures(arrays[f"points_{features}"], desc if len(desc) else None,
                                 tuple(int(v) for v in arrays[f"size_{features}"]))

    def thumbnail(self, card_id: str, raw_path: str) -> np.ndarray | None:
        arrays = self.read(card_id, raw_path)
        if arrays is None or not len(arrays["thumbnail"]):
            return None
        return arrays["thumbnail"]
