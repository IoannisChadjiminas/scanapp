from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

from app.config import Settings
from app.recognition.artifacts import ArtifactError, ArtifactSnapshot, load_snapshot
from app.recognition.embed import DinoEmbedder
from app.recognition.ocr import CardOcr


@dataclass
class Runtime:
    settings: Settings
    snapshot: ArtifactSnapshot | None = None
    embedder: DinoEmbedder | None = None
    ocr: CardOcr | None = None
    error: str | None = None
    _lock: Lock = Lock()

    @property
    def ready(self) -> bool:
        return self.snapshot is not None and self.embedder is not None

    def load(self) -> None:
        with self._lock:
            try:
                snapshot = load_snapshot(self.settings)
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
                self.error = None
            except Exception as exc:  # noqa: BLE001 - startup must report unreadiness, not crash
                self.snapshot = None
                self.embedder = None
                self.ocr = None
                self.error = str(exc)

    def require(self) -> tuple[ArtifactSnapshot, DinoEmbedder, CardOcr | None]:
        if not self.ready or self.snapshot is None or self.embedder is None:
            raise ArtifactError(self.error or "Recognition artifacts are not ready")
        return self.snapshot, self.embedder, self.ocr

    def versions(self) -> dict[str, str]:
        snapshot = self.snapshot
        return {
            "model": snapshot.model_name if snapshot else self.settings.model_name,
            "model_revision": snapshot.model_revision if snapshot else "missing",
            "catalogue": snapshot.catalogue_version if snapshot else "missing",
            "preprocessing": self.settings.preprocess_config,
            "ocr": self.settings.ocr_version if self.settings.use_ocr else "off",
            "ranking": self.settings.ranking_version,
        }

    def threshold_config(self) -> dict[str, Any]:
        return {
            "enable_matched": self.settings.enable_matched,
            "min_visual": self.settings.threshold_min_visual,
            "min_gap": self.settings.threshold_min_gap,
        }
