from __future__ import annotations

from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore, Lock
from typing import Any

import numpy as np

from app.config import Settings
from app.cardmarket import grouped_expansion_skus
from app.recognition.artifacts import ArtifactError, ArtifactSnapshot, load_snapshot
from app.recognition.embed import DinoEmbedder
from app.recognition.ocr import CardOcr
from app.recognition.printing import ReferencePrintingIndex
from app.recognition.local_match import FULL_ART_BOX, FULL_ART_RARITIES, LocalArtworkVerifier
from app.recognition.artwork import ArtworkIndex
from app.recognition.metadata import MetadataCandidateIndex
from app.recognition.reference_features import ReferenceFeatureStore, SCHEMA_VERSION as FEATURES_VERSION


@dataclass
class Runtime:
    settings: Settings
    snapshot: ArtifactSnapshot | None = None
    embedder: DinoEmbedder | None = None
    ocr: CardOcr | None = None
    grading_ocr: CardOcr | None = None
    grading_executor: ThreadPoolExecutor | None = field(default=None, repr=False)
    grading_slots: Any = field(default_factory=lambda: BoundedSemaphore(1), repr=False)
    card_languages: np.ndarray | None = None
    error: str | None = None
    printing_index: ReferencePrintingIndex | None = None
    artwork_verifier: LocalArtworkVerifier | None = None
    artwork_index: ArtworkIndex | None = None
    metadata_index: MetadataCandidateIndex | None = None
    card_positions: dict[str, int] | None = None
    _sku_catalog: Any = field(default=None, repr=False)
    _sku_groups: dict | None = field(default=None, repr=False)
    _lock: Lock = Lock()

    @property
    def ready(self) -> bool:
        return self.snapshot is not None and self.embedder is not None

    def load(self, cloud_snapshot: ArtifactSnapshot | None = None) -> None:
        with self._lock:
            self.close()
            self._sku_catalog = None
            self._sku_groups = None
            try:
                snapshot = cloud_snapshot if cloud_snapshot is not None else load_snapshot(self.settings)
                embedder = DinoEmbedder(
                    str(self.settings.dinov2_path),
                    self.settings.ort_intra_threads,
                    self.settings.ort_inter_threads,
                )
                ocr = None
                grading_ocr = None
                if self.settings.use_ocr:
                    models = self.settings.models_dir
                    ocr = CardOcr(
                        det_path=str(models / "PP-OCRv6_det_small.onnx"),
                        rec_path=str(models / "PP-OCRv6_rec_small.onnx"),
                        cls_path=str(models / "ch_ppocr_mobile_v2.0_cls_mobile.onnx"),
                        intra_threads=self.settings.ort_intra_threads,
                        inter_threads=self.settings.ort_inter_threads,
                    )
                    if self.settings.use_grading and (self.settings.parallel_grading
                                                      or self.settings.grading_at_card_deadline):
                        grading_ocr = CardOcr(
                            det_path=str(models / "PP-OCRv6_det_small.onnx"),
                            rec_path=str(models / "PP-OCRv6_rec_small.onnx"),
                            cls_path=str(models / "ch_ppocr_mobile_v2.0_cls_mobile.onnx"),
                            intra_threads=self.settings.ort_intra_threads,
                            inter_threads=self.settings.ort_inter_threads,
                        )
                        grading_ocr.share_inference_sessions_from(ocr)
                self.snapshot = snapshot
                self.embedder = embedder
                self.ocr = ocr
                self.grading_ocr = grading_ocr
                if grading_ocr is not None:
                    self.grading_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='grading')
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
                self.close()
                self.card_languages = None
                self.printing_index = None
                self.artwork_verifier = None
                self.artwork_index = None
                self.metadata_index = None
                self.card_positions = None
                self.error = str(exc)

    def bind_card_languages(self, catalog) -> None:  # noqa: ANN001 - sqlite connection
        self._sku_catalog = None
        self._sku_groups = None
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
        # The validated cloud snapshot protects expansion products from writes.
        # Build its presentation groups once, rather than parsing every listing
        # during every scan. Editable SQLite catalogues must always read fresh.
        if getattr(catalog, 'catalogue_readonly', False):
            self._sku_groups = grouped_expansion_skus(catalog)
            self._sku_catalog = catalog
        if self.artwork_verifier is not None:
            self.artwork_verifier.reference_boxes = {
                str(row['id']): FULL_ART_BOX for row in catalog.execute('SELECT id, rarity FROM cards')
                if str(row['rarity'] or '').casefold() in FULL_ART_RARITIES}
        if self.settings.reference_features_dir is not None:
            try:
                store = ReferenceFeatureStore.load(self.settings.reference_features_dir,
                    [dict(row) for row in catalog.execute('SELECT id, image_path, rarity FROM cards')])
                self.artwork_verifier.feature_store = store
                self.printing_index.feature_store = store
            except ArtifactError as exc:
                self.snapshot = None
                self.embedder = None
                self.card_languages = None
                self.error = str(exc)
                return
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

    def close(self) -> None:
        if self.grading_executor is not None:
            self.grading_executor.shutdown(wait=False, cancel_futures=True)
        self.grading_executor = None
        self.grading_ocr = None
        self._sku_catalog = None
        self._sku_groups = None

    def listing_groups(self, catalog) -> dict:
        if (catalog is self._sku_catalog and self._sku_groups is not None
                and getattr(catalog, 'catalogue_readonly', False)):
            return self._sku_groups
        return grouped_expansion_skus(catalog)

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
        if self.settings.use_ocr and self.settings.ocr_complete_frame_first:
            versions['ocr'] += '+complete-frame-first-v1'
        if self.artwork_index is not None:
            versions["artwork"] = (self.artwork_index.manifest["schema_version"] + ":" +
                                    self.artwork_index.manifest["records_sha256"][:12])
        if self.artwork_verifier is not None and self.artwork_verifier.feature_store is not None:
            versions['reference_features'] = (FEATURES_VERSION + ':' +
                self.artwork_verifier.feature_store.manifest['catalogue_sha256'][:12])
        return versions

    def threshold_config(self) -> dict[str, Any]:
        return {
            "enable_matched": self.settings.enable_matched,
            "min_visual": self.settings.threshold_min_visual,
            "min_visual_ocr": self.settings.threshold_min_visual_ocr,
            "min_gap": self.settings.threshold_min_gap,
        }
