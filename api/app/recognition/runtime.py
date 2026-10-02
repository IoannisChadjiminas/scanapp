from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

import numpy as np

from app.config import Settings
from app.recognition.artifacts import ArtifactError, ArtifactSnapshot, load_snapshot
from app.recognition.embed import DinoEmbedder
from app.recognition.ocr import CardOcr
from app.recognition.printing import ReferencePrintingIndex
from app.recognition.local_match import FULL_ART_BOX, FULL_ART_RARITIES, LocalArtworkVerifier
from app.recognition.artwork import ArtworkIndex
from app.recognition.metadata import MetadataCandidateIndex


@dataclass
class Runtime:
    settings: Settings
    snapshot: ArtifactSnapshot | None = None
    embedder: DinoEmbedder | None = None
    ocr: CardOcr | None = None
    card_languages: np.ndarray | None = None
    error: str | None = None
    printing_index: ReferencePrintingIndex | None = None
    artwork_verifier: LocalArtworkVerifier | None = None
    artwork_index: ArtworkIndex | None = None
    metadata_index: MetadataCandidateIndex | None = None
    card_positions: dict[str, int] | None = None
    _lock: Lock = Lock()

    @property
    def ready(self) -> bool:
        return self.snapshot is not None and self.embedder is not None

    def load(self, cloud_snapshot: ArtifactSnapshot | None = None) -> None:
        with self._lock:
            try:
                snapshot = cloud_snapshot if cloud_snapshot is not None else load_snapshot(self.settings)
                embedder = DinoEmbedder(
                    str(self.settings.dinov2_path),
                    self.settings.ort_intra_threads,
                    self.settings.ort_inter_threads,
                )
                ocr = None
                if self.settings.use_ocr:
                    models = self.settings.models_dir
                    ocr = CardOcr(
                        det_path=str(models / "PP-OCRv6_det_small.onnx"),
                        rec_path=str(models / "PP-OCRv6_rec_small.onnx"),
                        cls_path=str(models / "ch_ppocr_mobile_v2.0_cls_mobile.onnx"),
                        intra_threads=self.settings.ort_intra_threads,
                        inter_threads=self.settings.ort_inter_threads,
                    )
                self.snapshot = snapshot
                self.embedder = embedder
                self.ocr = ocr
                self.card_languages = None
                self.printing_index = ReferencePrintingIndex(self.settings.data_dir)
                self.artwork_verifier = LocalArtworkVerifier(self.settings.data_dir)
                self.artwork_index = None
                self.metadata_index = None
                self.card_positions = None
                self.error = None
            except Exception as exc:  # noqa: BLE001 - startup must report unreadiness, not crash
                self.snapshot = None
                self.embedder = None
                self.ocr = None
                self.card_languages = None
                self.printing_index = None
                self.artwork_verifier = None
                self.artwork_index = None
                self.metadata_index = None
                self.card_positions = None
                self.error = str(exc)

    def bind_card_languages(self, catalog) -> None:  # noqa: ANN001 - sqlite connection
        if self.snapshot is None:
            self.card_languages = None
            return
        lookup = {
            str(row["id"]): str(row["language"] or "en")
            for row in catalog.execute("SELECT id, language FROM cards")
        }
        self.card_languages = np.array(
            [lookup.get(str(card_id), "en") for card_id in self.snapshot.card_ids],
            dtype=object,
        )
        self.card_positions = {str(cid): i for i, cid in enumerate(self.snapshot.card_ids)}
        self.metadata_index = MetadataCandidateIndex(
            catalog.execute('SELECT id,name,collector_number,printed_collector_number,language FROM cards'),
            indexed_ids=set(self.card_positions))
        if self.artwork_verifier is not None:
            self.artwork_verifier.reference_boxes = {
                str(row['id']): FULL_ART_BOX for row in catalog.execute('SELECT id, rarity FROM cards')
                if str(row['rarity'] or '').casefold() in FULL_ART_RARITIES}
        if self.settings.artwork_bundle_dir is not None:
            try:
                self.artwork_index = ArtworkIndex.load(
                    self.settings.artwork_bundle_dir, snapshot=self.snapshot,
                    model_path=self.settings.dinov2_path, known_ids=set(lookup),
                    known_languages=lookup,
                )
            except ArtifactError as exc:
                # Explicitly configured incompatible artifacts fail readiness;
                # never silently run a different retrieval configuration.
                self.snapshot = None
                self.embedder = None
                self.card_languages = None
                self.artwork_index = None
                self.error = str(exc)

    def require(self) -> tuple[ArtifactSnapshot, DinoEmbedder, CardOcr | None]:
        if not self.ready or self.snapshot is None or self.embedder is None:
            raise ArtifactError(self.error or "Recognition artifacts are not ready")
        return self.snapshot, self.embedder, self.ocr

    def versions(self) -> dict[str, str]:
        snapshot = self.snapshot
        versions = {
            "model": snapshot.model_name if snapshot else self.settings.model_name,
            "model_revision": snapshot.model_revision if snapshot else "missing",
            "catalogue": snapshot.catalogue_version if snapshot else "missing",
            "preprocessing": self.settings.preprocess_config,
            "ocr": self.settings.ocr_version if self.settings.use_ocr else "off",
            "ranking": self.settings.ranking_version,
        }
        if self.artwork_index is not None:
            versions["artwork"] = (self.artwork_index.manifest["schema_version"] + ":" +
                                    self.artwork_index.manifest["records_sha256"][:12])
        return versions

    def threshold_config(self) -> dict[str, Any]:
        return {
            "enable_matched": self.settings.enable_matched,
            "min_visual": self.settings.threshold_min_visual,
            "min_visual_ocr": self.settings.threshold_min_visual_ocr,
            "min_gap": self.settings.threshold_min_gap,
        }
