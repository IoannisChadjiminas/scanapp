from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
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
    collector_retry_used: bool = False
    collector_retry_contributed: bool = False


def _region(image: Image.Image, y0: float, y1: float) -> Image.Image:
    width, height = image.size
    top = int(height * y0)
    bottom = max(top + 8, int(height * y1))
    return image.crop((0, top, width, bottom))


NAME_BOILERPLATE = {
    "basic",
    "stage1",
    "stage2",
    "tage1",
    "tage2",
    "stagei",
    "bas1c",
    "basicpokemon",
    "pokemon",
    "trainer",
    "energy",
    "supporter",
    "item",
    "stadium",
    "tool",
    "pokemontool",
    "authentic",
    "graded",
    "mint",
    "gemmint",
    "nmmint",
    "nmmt",
    "evolvesfrom",
    "hp",
}
NAME_PREFIX_SKIP = ("evolves from", "put ")
NAME_EXACT_SKIP = {"たね", "基本", "トレーナー", "トレーナーズ", "エネルギー", "サポート", "サボート", "グッズ", "スタジアム", "gx", "vmax", "vstar", "star", "ex"}
STAGE_ONLY = {"gx", "vmax", "vstar", "ex"}


def _has_cjk(text: str) -> bool:
    return any(
        "\u3040" <= char <= "\u30ff" or "\u4e00" <= char <= "\u9fff" for char in text
    )


def _compact_latin(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return re.sub(r"[^a-z0-9]+", "", decomposed)


def _is_layout_badge(line: str) -> bool:
    normalized = unicodedata.normalize('NFKC', line).strip().casefold()
    compact = _compact_latin(line)
    # An inferred frame may clip one letter of the long Basic Pokémon badge.
    # Do not fuzzy-match short labels or arbitrary card names.
    clipped_basic = (abs(len(compact)-len('basicpokemon')) <= 1 and
                     SequenceMatcher(None, compact, 'basicpokemon').ratio() >= .90)
    return bool(compact in {'basic','basicpokemon','stage1','stage2','trainer'}
                or clipped_basic or normalized in {'たね','トレーナー','トレーナーズ'}
                or re.fullmatch(r'[12]\s*進化', normalized))


def _pick_name_line(lines: list[str]) -> str | None:
    for line in lines:
        text = line.strip()
        if not text:
            continue
        lowered = text.lower()
        normalized = unicodedata.normalize('NFKC', text)
        # A misplaced title region can include the printed supporter rule.
        # This is layout boilerplate, not a confident different card name.
        if re.match(r'サ[ポボ]ートは[、,\s]*自分の番', normalized):
            continue
        # Japanese stage badges and evolution instructions precede the title
        # in OCR reading order. They are layout labels, not identity evidence.
        if re.fullmatch(r'\s*[12]\s*進化\s*', normalized) or re.search(r'から\s*進化\s*$', normalized):
            continue
        if lowered in NAME_EXACT_SKIP or text in NAME_EXACT_SKIP:
            continue
        if any(lowered.startswith(prefix) for prefix in NAME_PREFIX_SKIP):
            continue
        compact = _compact_latin(text)
        if _is_layout_badge(text):
            continue
        # Collector-only grading labels are not titles. Preserve actual names
        # containing numbers (e.g. Porygon2), not standalone SKU identifiers.
        if re.fullmatch(r'\s*#\s*[A-Za-z]{0,4}\d{1,4}\s*', text):
            continue
        # HP, collector/copyright lines and grading labels are not card names.
        # Uncertain/missing names remain neutral rather than vetoing artwork.
        if not _has_cjk(text) and (
            not re.search(r"[a-zA-Z]", text)
            or re.fullmatch(r"(?:HP\s*)?\d{1,4}(?:\s*(?:HP|ex|vmax|v))?", text, re.I)
            or re.search(r"(?:\b\d{4}\s+POK[EÉ]MON\b|\bGEM\s*MT\b|\bPSA\b|\bGAME\s*FREAK\b|Nintendo|©|copyright)", text, re.I)
        ):
            continue
        if compact in NAME_BOILERPLATE:
            continue
        if compact in STAGE_ONLY and not _has_cjk(text):
            continue
        if len(text) < 2:
            continue
        return text
    return None


def pick_name_line(lines: list[str]) -> str | None:
    # Prefer a title after the card's stage/trainer badge, rather than a
    # background sign above it. This is reading-order layout evidence, not a
    # catalogue-specific name whitelist. Evolution instructions aren't badges.
    for i, line in enumerate(lines):
        if _is_layout_badge(line):
            title = _pick_name_line(lines[i+1:])
            if title:
                return title
    return _pick_name_line(lines)


def pick_confident_name(lines: list[str], scores: list[float | None]) -> str | None:
    first = pick_name_line(lines)
    if first is None:
        return None
    first_score = next((score or 0. for text,score in zip(lines,scores) if text == first),0.)
    if first_score >= .85:
        return first
    confident = [text for text,score in zip(lines,scores) if score is not None and score >= .85]
    return pick_name_line(confident) or first


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
        return self._parse_output(output)

    @staticmethod
    def _parse_output(output) -> tuple[list[str], list[float | None]]:
        texts: list[str] = []
        scores: list[float | None] = []
        if output is None:
            return texts, scores
        txts = getattr(output, "txts", None)
        raw_scores = getattr(output, "scores", None)
        if txts:
            score_values = list(raw_scores) if raw_scores is not None else []
            # Skip text and its score together. Empty OCR entries must not
            # give a later weak observation an unrelated high confidence.
            for i, item in enumerate(txts):
                if not item:
                    continue
                texts.append(str(item))
                score = score_values[i] if i < len(score_values) else None
                scores.append(float(score) if score is not None else None)
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

    def _run_located(self, image: Image.Image) -> tuple[list[str], list[float | None], list[str]]:
        """Full-frame fallback with observed locations, never guessed regions."""
        if not hasattr(self, 'engine'):
            texts, scores = self._run(image)
            return texts, scores, ['full'] * len(texts)
        output = self.engine(np.asarray(image.convert('RGB')))
        texts, scores = self._parse_output(output)
        raw_texts = getattr(output, 'txts', None)
        boxes = getattr(output, 'boxes', None)
        regions = []
        if raw_texts is not None and boxes is not None and len(raw_texts) == len(boxes):
            for text, box in zip(raw_texts, boxes):
                if not text:
                    continue
                points = np.asarray(box, dtype=float)
                region = 'full'
                if points.shape == (4,2) and np.isfinite(points).all():
                    if 0 <= points[:,1].min() and points[:,1].max() <= .22*image.height:
                        region = 'name'
                    elif .82*image.height <= points[:,1].min() and points[:,1].max() <= image.height:
                        region = 'collector'
                regions.append(region)
        if len(regions) != len(texts):
            regions = ['full'] * len(texts)
        return texts, scores, regions

    def read(self, image: Image.Image) -> OcrResult:
        try:
            # Tiny detected cards/slab interiors have title/footer strips too
            # short for text detection. Interpolate regions before OCR, not
            # after an empty result has forced shared-art printing guesses.
            ocr_image = image
            if image.width < 450:
                scale = min(3., 600 / image.width)
                ocr_image = image.resize((round(image.width*scale),round(image.height*scale)),
                                         Image.Resampling.LANCZOS)
            name_lines, name_scores = self._run(_region(ocr_image, 0.0, 0.22))
            number_lines, number_scores = self._run(_region(ocr_image, 0.82, 1.0))
            name_text = pick_confident_name(name_lines,name_scores)
            collector_retry_used = False
            collector_retry_contributed = False
            name_confidence = max((score or 0. for text, score in zip(name_lines, name_scores)
                                   if text == name_text), default=0.)
            # One higher-resolution title pass for weak reads. Require a
            # materially more confident, text-compatible reading; do not swap
            # an unrelated high-confidence title into the identity evidence.
            if name_text and .50 <= name_confidence < .90:
                header = _region(image, 0., .22)
                scale = min(3., 1200 / header.width)
                if scale > 1.:
                    try:
                        retry_lines, retry_scores = self._run(header.resize(
                            (round(header.width * scale), round(header.height * scale)),
                            Image.Resampling.LANCZOS))
                        retry_name = pick_confident_name(retry_lines, retry_scores)
                        retry_confidence = max((s or 0. for t,s in zip(retry_lines,retry_scores)
                                                if t == retry_name), default=0.)
                        if (retry_name and retry_confidence >= .90 and
                            retry_confidence > name_confidence and
                            SequenceMatcher(None, name_text.casefold(), retry_name.casefold()).ratio() >= .70):
                            name_text, name_confidence = retry_name, retry_confidence
                        name_lines.extend(retry_lines)
                        name_scores.extend(retry_scores)
                    except Exception:  # noqa: BLE001 - preserve first-pass evidence
                        pass
            # Small slab/card frames often leave the bottom digits only a few
            # pixels high. One bounded interpolation pass; no invented digits,
            # confidence boost, or replacement of a conflicting first read.
            has_identifier = any(COLLECTOR_FRACTION_RE.search(text) or
                re.search(r'\b[A-Z]{1,5}[- ]?\d{1,4}\b', text) for text in number_lines)
            if image.width < 450 and name_text and name_confidence >= .85 and not has_identifier:
                collector_retry_used = True
                bottom = _region(image, .82, 1.)
                scale = min(3., 800 / bottom.width)
                enlarged = bottom.resize((round(bottom.width * scale), round(bottom.height * scale)),
                                         Image.Resampling.LANCZOS)
                try:
                    retry_lines, retry_scores = self._run(enlarged)
                    # A shifted frame may contain attack/weakness text. This
                    # optional pass contributes only explicit fractions or
                    # whole promo codes, never incidental bare digits/"2N".
                    identifiers = [(text, score) for text, score in zip(retry_lines, retry_scores)
                        if score is not None and score >= .85 and
                        (COLLECTOR_FRACTION_RE.search(text) or
                         re.fullmatch(r'[A-Z]{1,5}[- ]?\d{1,4}', text.strip()))]
                    collector_retry_contributed = bool(identifiers)
                    number_lines = [*number_lines, *(text for text, _ in identifiers)]
                    number_scores = [*number_scores, *(score for _, score in identifiers)]
                except Exception:  # noqa: BLE001 - keep successful first-pass observations
                    pass
            # Large photographs can still have tiny footer text relative to
            # a wide OCR strip. Retry overlapping footer halves only when the
            # readable title has no explicit identifier. Never infer a number
            # from incidental damage/HP, and retain every first-pass conflict.
            if image.width >= 450 and name_text and name_confidence >= .85 and not has_identifier:
                collector_retry_used = True
                bottom = _region(image, .88, 1.)
                for left, right in ((0., .60), (.40, 1.)):
                    tile = bottom.crop((round(left * bottom.width), 0,
                                        round(right * bottom.width), bottom.height))
                    scale = min(3., 900 / tile.width)
                    tile = tile.resize((round(tile.width * scale), round(tile.height * scale)),
                                       Image.Resampling.LANCZOS)
                    try:
                        retry_lines, retry_scores = self._run(tile)
                        identifiers = [(text, score) for text, score in zip(retry_lines, retry_scores)
                            if score is not None and score >= .85 and
                            (COLLECTOR_FRACTION_RE.search(text) or
                             re.fullmatch(r'[A-Z]{1,5}[- ]?\d{1,4}', text.strip()))]
                        collector_retry_contributed |= bool(identifiers)
                        number_lines.extend(text for text, _ in identifiers)
                        number_scores.extend(score for _, score in identifiers)
                    except Exception:  # noqa: BLE001 - optional retry cannot erase first read
                        pass
            extra_lines: list[str] = []
            extra_scores: list[float | None] = []
            extra_regions: list[str] = []
            if not name_lines and not number_lines:
                extra_lines, extra_scores, extra_regions = self._run_located(image)
                title_pairs = [(t,s) for t,s,r in zip(extra_lines,extra_scores,extra_regions) if r == 'name']
                name_text = pick_confident_name([t for t,_ in title_pairs],[s for _,s in title_pairs])
                number_lines = [t for t,r in zip(extra_lines,extra_regions) if r == 'collector']
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
                    OcrHit(text=text, confidence=score, region=region)
                    for text, score, region in zip(extra_lines, extra_scores, extra_regions, strict=False)
                ],
            ]
            return OcrResult(
                # Footer observations must not become title evidence when a
                # slab/proposal misses the actual name region.
                name_text=name_text,
                collector_text=pick_collector_text(number_lines),
                lines=lines,
                hits=hits,
                failed=False,
                collector_retry_used=collector_retry_used,
                collector_retry_contributed=collector_retry_contributed,
            )
        except Exception:  # noqa: BLE001 - OCR must never block retrieval
            return OcrResult(failed=True)
