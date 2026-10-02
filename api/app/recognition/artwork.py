"""Optional, separately versioned artwork retrieval; never printing proof.

Profiles are explicit crop hypotheses, not a trained layout classifier. Records
retain card IDs and profile provenance. No reference-photo queries are indexed.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
from PIL import Image

from app.recognition.artifacts import ArtifactError, sha256_file
from app.recognition.printing import ART_BOX


SCHEMA_VERSION = "artwork-hypotheses-v1"
PROFILES = {
    "conventional_window": ART_BOX,
    "broad_center_hypothesis": (.08, .10, .92, .62),
}


def crop_profile(image: Image.Image, profile: str) -> Image.Image:
    box = PROFILES[profile]
    w, h = image.size
    return image.crop(tuple(round(v * (w if i % 2 == 0 else h))
                            for i, v in enumerate(box)))


@dataclass(frozen=True)
class ArtworkHit:
    card_id: str
    score: float
    reference_profile: str
    query_profile: str


class ArtworkIndex:
    def __init__(self, embeddings: np.ndarray, records: list[dict], manifest: dict) -> None:
        self.embeddings = embeddings
        self.records = records
        self.manifest = manifest

    @classmethod
    def load(cls, directory: Path, *, snapshot: Any, model_path: Path,
             known_ids: set[str], known_languages: dict[str, str] | None = None) -> "ArtworkIndex":
        try:
            return cls._validated_load(directory, snapshot=snapshot, model_path=model_path,
                                       known_ids=known_ids, known_languages=known_languages)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise ArtifactError("Unreadable or malformed artwork index") from exc

    @classmethod
    def _validated_load(cls, directory: Path, *, snapshot: Any, model_path: Path,
                        known_ids: set[str], known_languages: dict[str, str] | None) -> "ArtworkIndex":
        manifest = json.loads((directory / "manifest.json").read_text())
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise ArtifactError("Unsupported artwork index schema")
        if manifest.get("base_embeddings_sha256") != snapshot.embeddings_sha256:
            raise ArtifactError("Artwork index full-card snapshot mismatch")
        if manifest.get("base_ids_sha256") != snapshot.ids_sha256:
            raise ArtifactError("Artwork index card-ID snapshot mismatch")
        if manifest.get("model_sha256") != sha256_file(model_path):
            raise ArtifactError("Artwork index model mismatch")
        if manifest.get("preprocess_config") != snapshot.preprocess_config:
            raise ArtifactError("Artwork index preprocessing mismatch")
        if manifest.get("profiles") != {k: list(v) for k, v in PROFILES.items()}:
            raise ArtifactError("Artwork index crop profile mismatch")
        for filename, key in (("embeddings.npy", "embeddings_sha256"),
                              ("records.json", "records_sha256")):
            if sha256_file(directory / filename) != manifest.get(key):
                raise ArtifactError(f"Artwork index {filename} checksum mismatch")
        vectors = np.load(directory / "embeddings.npy", mmap_mode="r", allow_pickle=False)
        records = json.loads((directory / "records.json").read_text())
        if (vectors.ndim != 2 or vectors.dtype != np.float32 or
            vectors.shape != (len(records), snapshot.embedding_dim) or not len(records) or
            manifest.get("indexed_regions") != len(records) or not np.isfinite(vectors).all()):
            raise ArtifactError("Invalid artwork vector shape or values")
        if np.max(np.abs(np.linalg.norm(vectors, axis=1) - 1)) > .01:
            raise ArtifactError("Artwork vectors must be normalized")
        keys = []
        for record in records:
            card_id, profile = record.get("card_id"), record.get("profile")
            if card_id not in known_ids or profile not in PROFILES:
                raise ArtifactError("Artwork index has unknown card IDs or profiles")
            language = record.get("language")
            if not isinstance(language, str) or not language or (
                known_languages is not None and known_languages.get(card_id) != language
            ):
                raise ArtifactError("Artwork index language metadata mismatch")
            keys.append((card_id, profile))
        if len(set(keys)) != len(keys):
            raise ArtifactError("Artwork index has duplicate card/profile records")
        if manifest.get("indexed_cards") != len({key[0] for key in keys}):
            raise ArtifactError("Artwork index card count mismatch")
        vectors.flags.writeable = False
        return cls(vectors, records, manifest)

    def search(self, image: Image.Image, embedder: Any, *, mode: str,
               as_supplied_vector: np.ndarray | None = None,
               languages: tuple[str, ...] = (), k: int = 15) -> tuple[list[ArtworkHit], dict[str, float]]:
        """Search as-is always. Extra crops are optional portrait hypotheses.

        Never force a partial image to a card aspect ratio. Distinct scores are
        retained for retrieval provenance, not added to full-card scores.
        """
        if k < 1:
            return [], {"artwork_embed_ms": 0., "artwork_retrieve_ms": 0.}
        keep = np.array([not languages or r["language"] in languages
                         for r in self.records], dtype=bool)
        if not np.any(keep):
            return [], {"artwork_embed_ms": 0., "artwork_retrieve_ms": 0.}
        hypotheses = [("as_supplied", image)]
        if .60 <= image.width / image.height <= .82:
            hypotheses.extend((name, crop_profile(image, name)) for name in PROFILES)
        hits: dict[str, ArtworkHit] = {}
        embed_ms = retrieve_ms = 0.
        for name, pixels in hypotheses:
            mark = time.perf_counter()
            query = as_supplied_vector if name == "as_supplied" else None
            if query is None:
                query = embedder.embed(pixels, mode)
            embed_ms += (time.perf_counter() - mark) * 1000
            mark = time.perf_counter()
            scores = np.asarray(self.embeddings @ query, dtype=np.float32)
            # Oversample region rows so multiple profiles/aliases do not consume
            # every slot. Take the best row per distinct card ID per hypothesis.
            order = np.argsort(-np.where(keep, scores, -np.inf))
            seen = set()
            for i in order:
                if not keep[i]:
                    break
                record = self.records[int(i)]
                card_id = record["card_id"]
                if card_id in seen:
                    continue
                seen.add(card_id)
                hit = ArtworkHit(card_id, float(scores[i]), record["profile"], name)
                old = hits.get(card_id)
                if old is None or hit.score > old.score:
                    hits[card_id] = hit
                if len(seen) >= k:
                    break
            retrieve_ms += (time.perf_counter() - mark) * 1000
        return sorted(hits.values(), key=lambda h: (-h.score, h.card_id)), {
            "artwork_embed_ms": embed_ms, "artwork_retrieve_ms": retrieve_ms,
        }
