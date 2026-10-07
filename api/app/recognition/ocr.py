from __future__ import annotations

from dataclasses import dataclass, field
from contextlib import nullcontext
from difflib import SequenceMatcher
import re
import time
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
    collector_retry_skipped: bool = False
    # The caller asked for the title strip only; no footer evidence exists.
    footer_skipped: bool = False
    passes: list[dict] = field(default_factory=list)


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
    "tagteam",
    "megaevolutionblackstar",
    "ultrapremiumcollection",
    "certifiedguarantycompany",
    "universalgrade",
    "centering",
    "corners",
    "edges",
    "surface",
    "cgcuniversal",
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
    return bool(compact in {'basic','basicpokemon','stage1','stage2','stage','stag','trainer'}
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
        # Whole supported issuer fields and dated set headings belong to a
        # holder, not the card title. Do not fuzzy-correct them into issuers.
        from app.recognition.grading import brand_company, _label_identity, _text
        if (brand_company(text) or _label_identity(_text(text)) or compact.startswith('evolvesfrom')
                or re.fullmatch(r'(?i)(?:CENTERING|CENTRING|CORNERS?|EDGES?|SURFACES?)\s+\d+(?:\.\d+)?',text)):
            continue
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
        # Garbled barcode/certificate strings are not Pokémon titles. Keep
        # legitimate names containing a digit (e.g. Porygon2), not mostly
        # digits with one or two OCR letter substitutions.
        if (sum(c.isdigit() for c in text)>=.60*len(text)
                and sum(c.isalpha() for c in text)<=2):
            continue
        # Full sentences/copyright tails in a misplaced header region are
        # not a card title. Preserve internal punctuation (e.g. Mr. Mime).
        if text.endswith(('.',',')):
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


def inverted_card_layout(result: OcrResult) -> bool:
    """Two observed ends contradict an upright layout; not a vector-score vote."""
    reliable=[h for h in result.hits if h.confidence is not None and h.confidence>=.85]
    top_fraction=any(h.region=='name' and re.fullmatch(r'\s*(?:TG|GG)?\d{1,4}/(?:TG|GG)?\d{1,4}\s*',h.text,re.I)
                     for h in reliable)
    bottom_stage=any(h.region=='collector' and (_is_layout_badge(h.text)
                     or _compact_latin(h.text).startswith('evolvesfrom')) for h in reliable)
    return top_fraction and bottom_stage


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

        self._model_signature = (det_path, rec_path, cls_path, intra_threads, inter_threads)
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

    def share_inference_sessions_from(self, other: CardOcr) -> None:
        """Share read-only CPU model sessions, never mutable RapidOCR state.

        ONNX Runtime permits concurrent Run calls. Each reader still owns its
        detector preprocessing, recognizer buffers and pipeline flags. Validate
        the complete pair before replacing any session, and fail closed on an
        incompatible model/runtime rather than weakening the isolation guard.
        """
        from onnxruntime import InferenceSession

        if self is other or self.engine is other.engine:
            raise ValueError('OCR readers must own separate engines')
        if self._model_signature != other._model_signature:
            raise ValueError('Cannot share sessions from different OCR models/settings')
        pairs = []
        for component in ('text_det', 'text_cls', 'text_rec'):
            target = getattr(self.engine, component).session
            source = getattr(other.engine, component).session
            if target is source or not isinstance(source.session, InferenceSession):
                raise ValueError('Expected isolated CPU ONNX Runtime session wrappers')
            if source.session.get_providers() != ['CPUExecutionProvider']:
                raise ValueError('Only CPU sessions support this OCR sharing path')
            pairs.append((target, source.session))
        for target, session in pairs:
            target.session = session

    def _grading_lines(self, image: Image.Image):
        gate = getattr(self, 'auxiliary_gate', None)
        with gate.grading() if gate is not None else nullcontext():
            return self._grading_lines_unbudgeted(image)

    def _grading_lines_unbudgeted(self, image: Image.Image):
        from app.recognition.grading import LabelLine
        array = np.asarray(image.convert('RGB'))
        # Grading already evaluates whole-photo orientations explicitly. An
        # isolated digit classifier can flip an upright 9 into 6. Run the
        # existing detector/recognizer without line rotation, without changing
        # any shared RapidOCR flags used by later card scans.
        if all(hasattr(self.engine, name) for name in
               ('preprocess_img','get_det_res','get_rec_res','finalize_results')):
            from rapidocr.ch_ppocr_cls.utils import TextClsOutput
            from rapidocr.main import RapidOCRError
            try:
                pixels, record = self.engine.preprocess_img(array)
                patches, detected = self.engine.get_det_res(pixels, record)
                recognized = self.engine.get_rec_res(patches)
                output = self.engine.finalize_results(array, detected, TextClsOutput(),
                    recognized, patches, record)
            except RapidOCRError:
                from types import SimpleNamespace
                output = SimpleNamespace(txts=[], scores=[], boxes=[])
        else:
            output = self.engine(array)
        texts, scores = self._parse_output(output)
        boxes = []
        raw_texts, raw_boxes = getattr(output,'txts',None), getattr(output,'boxes',None)
        if raw_texts is not None and raw_boxes is not None and len(raw_texts) == len(raw_boxes):
            boxes = [box for text,box in zip(raw_texts,raw_boxes) if text]
        elif isinstance(output,(list,tuple)):
            boxes = [item[0] for item in output if isinstance(item,(list,tuple)) and len(item)>=2]
        lines = []
        for i,(text,score) in enumerate(zip(texts,scores)):
            box = None
            if i < len(boxes):
                points = np.asarray(boxes[i],dtype=float)
                if points.shape == (4,2) and np.isfinite(points).all():
                    left,top = points.min(axis=0); right,bottom = points.max(axis=0)
                    if 0 <= left < right <= image.width and 0 <= top < bottom <= image.height:
                        box = (left/image.width,top/image.height,right/image.width,bottom/image.height)
            lines.append(LabelLine(text,score,box))
        return lines

    def _grading_tokens(self, patches):
        gate = getattr(self, 'auxiliary_gate', None)
        with gate.grading() if gate is not None else nullcontext():
            return self._grading_tokens_unbudgeted(patches)

    def _grading_tokens_unbudgeted(self, patches):
        """Recognize isolated observed fields without mutating detector state."""
        from app.recognition.grading import LabelLine
        output = self.engine.get_rec_res([np.asarray(p.convert('RGB')) for p in patches])
        texts,scores = getattr(output,'txts',None),getattr(output,'scores',None)
        if texts is None or scores is None or len(texts) != len(patches) or len(scores) != len(patches):
            return []
        return [LabelLine(str(t),float(s)) for t,s in zip(texts,scores)]

    def read_holder_identity(self, image: Image.Image):
        """One original-frame label read for a review-only printing hint.

        Caller must already have a supported slab, matching printed identity
        and an ambiguous verified artwork family. These lines are not footer
        OCR, a grade fallback, or proof of holder authenticity.
        """
        strip = _region(image, 0., .36)
        scale = min(4., 1200/strip.width)
        patch = strip.resize((max(1, round(strip.width*scale)),
                              max(1, round(strip.height*scale))), Image.Resampling.LANCZOS)
        return self._grading_lines(patch)

    def read_grading(self, image: Image.Image):
        """Bounded label OCR, isolated from card identity/printing ranking.

        Ten image passes maximum, including exceptions. Normal readable labels exit
        after one. Rectified label/contrast passes are recovery hypotheses, not
        evidence by themselves. Never merge unrelated holders/orientations.
        """
        from app.recognition.grading import (
            MIN_CONFIDENCE, NUMBER, LabelLine, _condition, _label_identity, _text, brand_company, has_label_context, parse_label,
            recover_fuzzy_company,
        )
        from app.recognition.label_vision import contrast_label, grade_regions, label_panels, logo_company, logo_text_regions, text_label_panel
        from app.schemas import GradingEvidence
        from app.recognition.grading_control import GradingCancelled, check_grading_cancelled

        # Photograph aspect ratio is not holder orientation. A landscape photo
        # can contain an upright slab and wide margins; always try original
        # pixels before side rotations. Keep the same global bounded budget.
        angles = (0,90,270,180) if image.width > image.height else (0,180)
        observations, failed, calls = [], False, 0
        fuzzy_views = []
        conflict_codes = {'conflicting_grading_companies','conflicting_overall_grades',
                          'conflicting_condition_labels','certification_number_ambiguous',
                          'condition_grade_contradiction'}

        def resized(patch, width=1200):
            scale = min(4.,width/patch.width)
            return patch.resize((max(1,round(patch.width*scale)),
                                 max(1,round(patch.height*scale))),Image.Resampling.LANCZOS)

        def read(patch):
            nonlocal calls
            check_grading_cancelled()
            calls += 1
            lines = self._grading_lines(patch)
            fuzzy_views.append(list(lines))
            return lines

        def finish(result):
            # Fuzzy issuer evidence is applied only after the established
            # literal/shape OCR path finishes; it cannot cause an early exit.
            return recover_fuzzy_company(result, fuzzy_views)

        def read_tokens(patches):
            nonlocal calls
            check_grading_cancelled()
            # Invoke the recognizer directly, never change RapidOCR's shared
            # use_det/use_cls flags (which persist across subsequent scans).
            calls += len(patches)
            return self._grading_tokens(patches)

        def complete(result):
            return result.company is not None and result.grade is not None

        def independent_logo(panel, lines):
            # OCR boxes are normalized to the same panel. Avoid reusing an
            # observed word or numeral as independent issuer-shape evidence.
            boxes = [line.box for line in lines if line.box and line.confidence is not None
                     and line.confidence >= MIN_CONFIDENCE
                     and (len(_text(line.text)) >= 2 or _text(line.text).isdigit())]
            return logo_company(panel,text_boxes=boxes)

        def reconcile(result, prior):
            # Independent views of the same holder must not silently disagree.
            if (prior.grade is not None and result.grade is not None and prior.grade != result.grade):
                result.grade = None; result.is_graded = None; result.grading_status = 'unknown'
                result.warnings.append('conflicting_overall_grades')
            if prior.company and result.company and prior.company != result.company:
                return GradingEvidence(warnings=['conflicting_grading_companies'])
            if (prior.certification_number and result.certification_number
                    and prior.certification_number != result.certification_number):
                result.grade = None; result.is_graded = None; result.grading_status = 'unknown'
                result.certification_number = None
                result.warnings.append('certification_number_ambiguous')
            return result

        def recover_number(patch, lines, prior):
            if (calls > 7 or not prior.slab_detected or not prior.company or prior.grade is not None
                    or not hasattr(getattr(self,'engine',None),'get_rec_res')):
                return prior
            regions=grade_regions(patch,lines,prior.company,tight=True)[:max(0,9-calls)]
            tokens=read_tokens([p for p,_ in regions]) if regions else []
            located=[]
            for token,(tile,box) in zip(tokens,regions):
                text=_text(token.text)
                if (calls>=10 or token.confidence is None or token.confidence<MIN_CONFIDENCE
                        or not re.fullmatch(NUMBER,text)):
                    continue
                check=read_tokens([tile.resize((tile.width*2,tile.height*2),Image.Resampling.LANCZOS)])
                if (check and _text(check[0].text)==text and check[0].confidence is not None
                        and check[0].confidence>=MIN_CONFIDENCE):
                    located.append(LabelLine(text,min(token.confidence,check[0].confidence),box))
            return reconcile(parse_label([*lines,*located]),prior) if located else prior

        for angle in angles:
            check_grading_cancelled()
            if calls >= 10:
                break
            try:
                oriented = image.rotate(angle,expand=True) if angle else image
                strip = resized(_region(oriented,0.,.36),1000)
                lines = read(strip)
                initial = parse_label(lines)
                observations.append(initial)
                if complete(initial) or conflict_codes.intersection(initial.warnings):
                    return finish(initial)
                # Try the initial original-pixel glyph before rectification
                # can lose its bounds. Two literal reads are still required;
                # a condition descriptor never supplies a numeric grade.
                import re
                numeric = recover_number(strip,lines,initial)
                observations.append(numeric)
                if complete(numeric) or conflict_codes.intersection(numeric.warnings):
                    return finish(numeric)
                strip_fraction = .36
                identities = {_text(l.text) for l in lines if l.confidence is not None
                    and l.confidence >= MIN_CONFIDENCE and _label_identity(_text(l.text))}
                if not initial.slab_detected and len(identities) >= 2 and calls < 10:
                    # Large scene margins can place a holder label below the
                    # usual upper strip. Two separate label identity fields
                    # justify a wider OCR proposal, never a slab claim.
                    wider = read(resized(_region(oriented,0.,.60),1000))
                    candidate = reconcile(parse_label(wider),initial)
                    observations.append(candidate)
                    if complete(candidate) or conflict_codes.intersection(candidate.warnings):
                        return finish(candidate)
                    lines,initial,strip_fraction = wider,candidate,.60
                panels = label_panels(oriented)
                text_panel = text_label_panel(oriented,lines,strip_fraction=strip_fraction)
                if text_panel is not None:
                    # A known issuer with an unreadable number benefits from
                    # the rectified physical label first. For an unreadable
                    # issuer, text padding preserves overhanging logo pixels.
                    panels = [*panels,text_panel] if initial.company else [text_panel,*panels]
                    compact = text_label_panel(oriented,lines,compact=True,strip_fraction=strip_fraction)
                    if compact is not None:
                        panels.append(compact)
                for panel in panels:
                    if calls >= 10:
                        break
                    patch = resized(panel)
                    panel_lines = read(patch)
                    field_lines = panel_lines
                    # A rectified inner label may omit the company printed
                    # beside it. Only retain explicitly read issuer text from
                    # the same original frame; never transplant grade digits.
                    panel_identity = parse_label(panel_lines)
                    # Certificate equality scopes this transfer to the same
                    # holder, rather than a seller watermark/neighboring slab.
                    if (initial.certification_number is not None and
                            initial.certification_number == panel_identity.certification_number):
                        panel_lines += [LabelLine(line.text,line.confidence) for line in lines
                            if line.confidence is not None and line.confidence >= MIN_CONFIDENCE
                            and brand_company(line.text)]
                    # Shape evidence is only an issuer recovery path. It must
                    # not contradict an already literal supported issuer read
                    # by correlating with unrelated text or a decorative seal.
                    logo = independent_logo(panel,panel_lines) if (panel_identity.company is None
                        and has_label_context(panel_lines)) else None
                    result = parse_label(panel_lines,visual_company=logo[0] if logo else None)
                    result = reconcile(result,initial)
                    observations.append(result)
                    if complete(result) or conflict_codes.intersection(result.warnings):
                        return finish(result)
                    if (result.company is None and has_label_context(panel_lines) and calls <= 6
                            and hasattr(getattr(self,'engine',None),'get_rec_res')):
                        issuer_regions = logo_text_regions(panel)
                        issuer_tokens = read_tokens(issuer_regions) if issuer_regions else []
                        for token,tile in zip(issuer_tokens,issuer_regions):
                            if (calls >= 10 or token.confidence is None or token.confidence < MIN_CONFIDENCE
                                    or not brand_company(token.text)):
                                continue
                            confirmation = read_tokens([tile.resize((tile.width*2,tile.height*2),Image.Resampling.LANCZOS)])
                            if (confirmation and confirmation[0].confidence is not None
                                    and confirmation[0].confidence >= MIN_CONFIDENCE
                                    and brand_company(confirmation[0].text) == brand_company(token.text)):
                                panel_lines = [*panel_lines,token]
                                field_lines = panel_lines
                        result = reconcile(parse_label(panel_lines,visual_company=logo[0] if logo else None),initial)
                        observations.append(result)
                        if complete(result) or conflict_codes.intersection(result.warnings):
                            return finish(result)
                    # Retry only a supported brand or a structured label, not
                    # every raw-card rules panel. Keep observed digit boxes.
                    if calls < 10 and (has_label_context(panel_lines)
                            or any(brand_company(line.text) for line in panel_lines
                                   if line.confidence is not None and line.confidence >= MIN_CONFIDENCE)):
                        retry_lines = read(contrast_label(patch))
                        retry_logo = independent_logo(contrast_label(panel),retry_lines) if (
                            parse_label(retry_lines).company is None and has_label_context(retry_lines)) else None
                        # A contrast transform can erase a tiny printed '+'.
                        # Do not manufacture a second condition from the same
                        # observed field. Separate locations remain conflicts.
                        from app.recognition.grading import _condition_key
                        def lost_plus(other):
                            if not other.box or not _condition(_text(other.text),result.company):
                                return False
                            for original in panel_lines:
                                if (not original.box or original.confidence is None
                                        or original.confidence < MIN_CONFIDENCE
                                        or not _text(original.text).endswith('+')
                                        or _condition_key(_text(original.text)).rstrip('+') !=
                                           _condition_key(_text(other.text))):
                                    continue
                                a,b = original.box,other.box
                                overlap = max(0,min(a[2],b[2])-max(a[0],b[0])) * max(0,min(a[3],b[3])-max(a[1],b[1]))
                                area = min((a[2]-a[0])*(a[3]-a[1]),(b[2]-b[0])*(b[3]-b[1]))
                                if overlap > .6*area:
                                    return True
                            return False
                        field_lines = [*panel_lines,*[l for l in retry_lines if not lost_plus(l)]]
                        combined = parse_label(field_lines,
                            visual_company=(logo or retry_logo)[0] if logo or retry_logo else None)
                        combined = reconcile(combined,initial)
                        observations.append(combined)
                        if complete(combined) or conflict_codes.intersection(combined.warnings):
                            return finish(combined)
                        result = combined
                    if (calls <= 7 and result.slab_detected and result.company and result.grade is None
                            and hasattr(getattr(self,'engine',None),'get_rec_res')):
                        import re
                        regions = grade_regions(patch,field_lines,result.company)[:max(0,9-calls)]
                        tokens = read_tokens([p for p,_ in regions]) if regions else []
                        located = []
                        for token,(tile,box) in zip(tokens,regions):
                            text = _text(token.text)
                            if (calls >= 10 or token.confidence is None or token.confidence < MIN_CONFIDENCE
                                    or not re.fullmatch(NUMBER,text)):
                                continue
                            # Require a second literal read, from a different
                            # scale of original pixels. No threshold-only digit
                            # and no descriptor-to-number conversion is allowed.
                            check = read_tokens([tile.resize((tile.width*2,tile.height*2),Image.Resampling.LANCZOS)])
                            if (check and _text(check[0].text) == text and check[0].confidence is not None
                                    and check[0].confidence >= MIN_CONFIDENCE):
                                located.append(LabelLine(token.text,min(token.confidence,check[0].confidence),box))
                        combined = parse_label([*field_lines,*located],
                            visual_company=logo[0] if logo else None)
                        combined = reconcile(combined,result)
                        observations.append(combined)
                        if complete(combined) or conflict_codes.intersection(combined.warnings):
                            return finish(combined)
                # Preserve the original restricted logo-only retry when a
                # contour cannot isolate the label. New digits cannot replace
                # existing grades/certificates from an enlarged logo tile.
                if has_label_context(lines) and calls < 10:
                    original = _region(oriented,0.,.36)
                    tile = resized(original.crop((round(.25*original.width),0,
                                                  round(.75*original.width),original.height)),1000)
                    retry = read(tile)
                    import math
                    import re
                    retry_certificates = {line.text.strip() for line in retry
                        if line.confidence is not None and math.isfinite(line.confidence)
                        and line.confidence >= MIN_CONFIDENCE and re.fullmatch(r'\d{6,14}',line.text.strip())}
                    same_certificate = (initial.certification_number is not None and
                        retry_certificates == {initial.certification_number})
                    logos = [LabelLine(line.text,line.confidence) for line in retry
                             if line.confidence is not None and line.confidence >= MIN_CONFIDENCE
                             and brand_company(line.text) and same_certificate]
                    result = parse_label([*lines,*logos])
                    observations.append(result)
                    if result.slab_detected:
                        # A late logo-only attempt cannot erase a stronger
                        # same-frame panel read already collected above.
                        viable = [r for r in observations if r.slab_detected]
                        return finish(max(viable,key=lambda r:(complete(r),r.grade is not None,r.company is not None)))
                if initial.slab_detected:
                    break
            except GradingCancelled:
                raise
            except Exception:  # noqa: BLE001 - failure must not affect card recognition
                failed = True
                if any(result.slab_detected for result in observations):
                    break
        viable = [result for result in observations if result.slab_detected]
        if viable:
            result = max(viable,key=lambda r:(complete(r),r.grade is not None,r.company is not None))
            if failed:
                result.warnings.append('grading_ocr_failed')
            return finish(result)
        return GradingEvidence(label_text=observations[0].label_text if observations else [],
            warnings=(['grading_ocr_failed'] if failed else
                      ['no_supported_grading_label_detected','ungraded_status_not_proven']))

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

    def read(self, image: Image.Image, *, collector_retry_policy=None,
             read_footer: bool = True) -> OcrResult:
        passes = []
        def run(patch, region, reason):
            started = time.perf_counter()
            try:
                return self._run(patch)
            finally:
                passes.append(dict(region=region, reason=reason, width=patch.width,
                    height=patch.height, ms=round((time.perf_counter()-started)*1000, 2)))
        try:
            # Tiny detected cards/slab interiors have title/footer strips too
            # short for text detection. Interpolate regions before OCR, not
            # after an empty result has forced shared-art printing guesses.
            ocr_image = image
            if image.width < 450:
                scale = min(3., 600 / image.width)
                ocr_image = image.resize((round(image.width*scale),round(image.height*scale)),
                                         Image.Resampling.LANCZOS)
            reader = getattr(self, 'region_reader', None)
            executor = getattr(self, 'region_executor', None)
            gate = getattr(self, 'auxiliary_gate', None)
            if reader is not None and (reader is self or reader.engine is self.engine):
                raise RuntimeError('Parallel regions require isolated OCR engines')
            if (read_footer and reader is not None and executor is not None
                    and gate is not None and gate.try_reserve_card()):
                footer = _region(ocr_image, .82, 1.).copy()
                footer_record = {}
                def read_footer_strip():
                    started = time.perf_counter()
                    try:
                        return reader._run(footer)
                    finally:
                        footer_record.update(region='collector',reason='initial',
                            width=footer.width,height=footer.height,
                            ms=round((time.perf_counter()-started)*1000,2),parallel=True)
                        footer.close()
                        gate.release_card()
                try:
                    future = executor.submit(read_footer_strip)
                except Exception:
                    footer.close()
                    gate.release_card()
                    raise
                try:
                    name_lines, name_scores = run(_region(ocr_image, 0.0, 0.22), 'name', 'initial')
                finally:
                    # Drain before returning, including title failures. A late
                    # region may never mutate another request or its evidence.
                    try:
                        observed = future.result()
                    finally:
                        if footer_record:
                            passes.append(footer_record)
                number_lines, number_scores = observed
            else:
                name_lines, name_scores = run(_region(ocr_image, 0.0, 0.22), 'name', 'initial')
                number_lines, number_scores = (
                    run(_region(ocr_image, 0.82, 1.0), 'collector', 'initial')
                    if read_footer else ([], []))
            name_text = pick_confident_name(name_lines,name_scores)
            if name_text is None and any(_is_layout_badge(t) and s is not None and s>=.85
                                        for t,s in zip(name_lines,name_scores)):
                # A holder/window can put the stage badge at the very bottom
                # of the title strip and clip its following name. One wider
                # original-pixel header read; never replace a confident title.
                try:
                    wider=_region(image,0.,.35)
                    scale=min(3.,900/wider.width)
                    retry_lines,retry_scores=run(wider.resize(
                        (round(wider.width*scale),round(wider.height*scale)),Image.Resampling.LANCZOS),
                        'name', 'wider_header')
                    retry_name=pick_confident_name(retry_lines,retry_scores)
                    score=max((s or 0. for t,s in zip(retry_lines,retry_scores) if t==retry_name),default=0.)
                    if retry_name and score>=.85:
                        name_text=retry_name
                        name_lines.extend(retry_lines);name_scores.extend(retry_scores)
                except Exception:  # noqa: BLE001 - preserve the first read
                    pass
            collector_retry_used = False
            collector_retry_contributed = False
            collector_retry_skipped = False
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
                        retry_lines, retry_scores = run(header.resize(
                            (round(header.width * scale), round(header.height * scale)),
                            Image.Resampling.LANCZOS), 'name', 'weak_header')
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
            retry_allowed = True
            if collector_retry_policy is not None and name_text and name_confidence >= .85 and not has_identifier:
                # A failed optional policy must keep the established evidence
                # gathering path. Give it copies, never mutable reader buffers.
                initial = OcrResult(name_text=name_text, lines=[*name_lines, *number_lines], hits=[
                    *(OcrHit(t, s, 'name') for t, s in zip(name_lines, name_scores)),
                    *(OcrHit(t, s, 'collector') for t, s in zip(number_lines, number_scores))])
                try:
                    retry_allowed = bool(collector_retry_policy(initial))
                except Exception:  # noqa: BLE001 - optional optimization fails closed
                    retry_allowed = True
                collector_retry_skipped = not retry_allowed
            if not read_footer:
                retry_allowed = False
            if image.width < 450 and name_text and name_confidence >= .85 and not has_identifier and retry_allowed:
                collector_retry_used = True
                bottom = _region(image, .82, 1.)
                scale = min(3., 800 / bottom.width)
                enlarged = bottom.resize((round(bottom.width * scale), round(bottom.height * scale)),
                                         Image.Resampling.LANCZOS)
                try:
                    retry_lines, retry_scores = run(enlarged, 'collector', 'small_footer')
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
            if image.width >= 450 and name_text and name_confidence >= .85 and not has_identifier and retry_allowed:
                collector_retry_used = True
                bottom = _region(image, .88, 1.)
                for left, right in ((0., .60), (.40, 1.)):
                    tile = bottom.crop((round(left * bottom.width), 0,
                                        round(right * bottom.width), bottom.height))
                    scale = min(3., 900 / tile.width)
                    tile = tile.resize((round(tile.width * scale), round(tile.height * scale)),
                                       Image.Resampling.LANCZOS)
                    try:
                        retry_lines, retry_scores = run(tile, 'collector', 'footer_half')
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
                started = time.perf_counter()
                try:
                    extra_lines, extra_scores, extra_regions = self._run_located(image)
                finally:
                    passes.append(dict(region='full', reason='empty_regions', width=image.width,
                        height=image.height, ms=round((time.perf_counter()-started)*1000, 2)))
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
            # A holder's date/cert/subgrade header is not the physical card's
            # printed name. Preserve every read for diagnostics, but do not
            # let an unreadable issuer word veto a geometrically verified
            # card interior. A real stage badge keeps normal title evidence.
            from app.recognition.grading import _label_identity, _text, _condition, SUBGRADE, brand_company
            header=[_text(t) for t,s in zip(name_lines,name_scores) if s is not None and s>=.85]
            holder_header=(any(_label_identity(t) for t in header)
                and (any(re.fullmatch(r'\d{6,14}',t) for t in header)
                     or any(brand_company(t) for t in header))
                and (any(_condition(t,None) for t in header)
                     or sum(bool(SUBGRADE.search(t)) for t in header)>=2)
                and not any(_is_layout_badge(t) for t in name_lines))
            if holder_header:
                hits=[OcrHit(h.text,h.confidence,'holder_name' if h.region=='name' else h.region) for h in hits]
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
                collector_retry_skipped=collector_retry_skipped,
                footer_skipped=not read_footer,
                passes=passes,
            )
        except Exception:  # noqa: BLE001 - OCR must never block retrieval
            return OcrResult(failed=True, passes=passes)
