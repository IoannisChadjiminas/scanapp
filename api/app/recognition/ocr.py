from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata

import numpy as np
from PIL import Image


@dataclass
class OcrHit:
    text: str
    confidence: float | None = None
    region: str = "unknown"

    @property
    def reliable(self) -> bool:
        if self.region != "collector":
            return False
        if self.confidence is None:
            return True
        return self.confidence >= 0.55


@dataclass
class OcrResult:
    name_text: str | None = None
    collector_text: str | None = None
    lines: list[str] = field(default_factory=list)
    hits: list[OcrHit] = field(default_factory=list)
    failed: bool = False


def _region(image: Image.Image, y0: float, y1: float) -> Image.Image:
    width, height = image.size
    top = int(height * y0)
    bottom = max(top + 8, int(height * y1))
    return image.crop((0, top, width, bottom))


NAME_BOILERPLATE = {
    "basicpokemon",
    "trainer",
    "energy",
    "evolvesfrom",
}
NAME_PREFIX_SKIP = ("evolves from", "put ")
NAME_EXACT_SKIP = {"たね", "基本", "トレーナー", "エネルギー", "gx", "vmax", "vstar", "ex"}
STAGE_ONLY = {"gx", "vmax", "vstar", "ex"}


def _has_cjk(text: str) -> bool:
    return any(
        "\u3040" <= char <= "\u30ff" or "\u4e00" <= char <= "\u9fff" for char in text
    )


def _compact_latin(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return re.sub(r"[^a-z0-9]+", "", decomposed)


def pick_name_line(lines: list[str]) -> str | None:
    for line in lines:
        text = line.strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in NAME_EXACT_SKIP or text in NAME_EXACT_SKIP:
            continue
        if any(lowered.startswith(prefix) for prefix in NAME_PREFIX_SKIP):
            continue
        compact = _compact_latin(text)
        if compact in NAME_BOILERPLATE:
            continue
        if compact in STAGE_ONLY and not _has_cjk(text):
            continue
        if len(text) < 2:
            continue
        return text
    return None


COLLECTOR_FRACTION_RE = re.compile(r"\d{1,4}\s*/\s*\d{1,4}")


def pick_collector_text(number_lines: list[str]) -> str | None:
    for line in number_lines:
        match = COLLECTOR_FRACTION_RE.search(line)
        if match:
            return re.sub(r"\s+", "", match.group(0))
    return number_lines[-1] if number_lines else None


class CardOcr:
    def __init__(
        self,
        det_path: str,
        rec_path: str,
        cls_path: str,
        intra_threads: int,
        inter_threads: int,
    ) -> None:
        from rapidocr import EngineType, RapidOCR

        self.engine = RapidOCR(
            params={
                "Det.engine_type": EngineType.ONNXRUNTIME,
                "Det.model_path": det_path,
                "Rec.engine_type": EngineType.ONNXRUNTIME,
                "Rec.model_path": rec_path,
                "Cls.engine_type": EngineType.ONNXRUNTIME,
                "Cls.model_path": cls_path,
                "EngineConfig.onnxruntime.use_cuda": False,
                "EngineConfig.onnxruntime.intra_op_num_threads": intra_threads,
                "EngineConfig.onnxruntime.inter_op_num_threads": inter_threads,
            }
        )

    def _run(self, image: Image.Image) -> tuple[list[str], list[float | None]]:
        array = np.asarray(image.convert("RGB"))
        output = self.engine(array)
        texts: list[str] = []
        scores: list[float | None] = []
        if output is None:
            return texts, scores
        txts = getattr(output, "txts", None)
        raw_scores = getattr(output, "scores", None)
        if txts:
            texts.extend(str(item) for item in txts if item)
            if raw_scores:
                scores.extend(
                    float(score) if score is not None else None for score in list(raw_scores)[: len(texts)]
                )
            while len(scores) < len(texts):
                scores.append(None)
            return texts, scores
        if isinstance(output, (list, tuple)):
            for item in output:
                if item is None:
                    continue
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    texts.append(str(item[1]))
                    score = item[2] if len(item) >= 3 else None
                    try:
                        scores.append(float(score) if score is not None else None)
                    except (TypeError, ValueError):
                        scores.append(None)
                elif isinstance(item, str):
                    texts.append(item)
                    scores.append(None)
        return texts, scores

    def read(self, image: Image.Image) -> OcrResult:
        try:
            name_lines, name_scores = self._run(_region(image, 0.0, 0.22))
            number_lines, number_scores = self._run(_region(image, 0.82, 1.0))
            extra_lines: list[str] = []
            extra_scores: list[float | None] = []
            if not name_lines and not number_lines:
                extra_lines, extra_scores = self._run(image)
            lines = [*name_lines, *number_lines, *extra_lines]
            hits = [
                *[
                    OcrHit(text=text, confidence=score, region="name")
                    for text, score in zip(name_lines, name_scores, strict=False)
                ],
                *[
                    OcrHit(text=text, confidence=score, region="collector")
                    for text, score in zip(number_lines, number_scores, strict=False)
                ],
                *[
                    OcrHit(text=text, confidence=score, region="full")
                    for text, score in zip(extra_lines, extra_scores, strict=False)
                ],
            ]
            return OcrResult(
                name_text=pick_name_line(name_lines) or pick_name_line(lines),
                collector_text=pick_collector_text(number_lines),
                lines=lines,
                hits=hits,
                failed=False,
            )
        except Exception:  # noqa: BLE001 - OCR must never block retrieval
            return OcrResult(failed=True)
