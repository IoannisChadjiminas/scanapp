"""One literal title read after recognition returns an unrelated candidate."""
from copy import deepcopy
import re
import time

from PIL import Image

from app.recognition.ocr import OcrHit, pick_confident_name
from app.recognition.rank import name_match, normalize_text


def title_retry_allowed(first) -> bool:
    # Keep all useful results, explicit identifiers and quality retakes on
    # their existing paths. A partial readable title is still useful if any
    # retrieved candidate agrees with it.
    return bool(first.response.status.value == 'uncertain' and not first.quality_retake
        and first.lead and first.lead.get('strong_name_conflict')
        and first.name_confidence >= .85 and first.languages
        and first.ocr.name_text and not first.ocr.failed
        and len(normalize_text(first.ocr.name_text)) >= 4
        and not any(name_match(first.ocr.name_text, r['name']) for r in first.ranked)
        and not any(h.region == 'collector' and h.confidence is not None
                    and h.confidence >= .85
                    and ('/' in h.text or any(c.isalpha() for c in h.text))
                    for h in first.numbers)
        and first.query_image is not None and min(first.query_image.size) >= 450
        and .62 <= first.query_image.width / first.query_image.height <= .85)


def title_observations_agree(original: str, observed: str) -> bool:
    # A stage badge can be merged into a partial title. Remove only a complete
    # separated badge for comparison, never for the actual saved OCR text.
    partial = re.sub(r'^(?:BASIC|STAGE\s*[12])\s+', '', original.strip(), flags=re.I)
    suffix = re.compile(r'(?:\s+)(ex|gx|vmax|vstar|v)\s*$', re.I)
    before, after = suffix.search(partial), suffix.search(observed)
    if before and after and before[1].casefold() != after[1].casefold():
        return False
    return name_match(partial, observed)


def read_conflicting_title(engine, image, original):
    """Return supplemented observations plus diagnostics, never guessed text."""
    patch = image.crop((round(.20 * image.width), 0,
                        round(.80 * image.width), round(.24 * image.height)))
    patch.thumbnail((1000, 1000), Image.Resampling.BICUBIC)
    started = time.perf_counter()
    record = dict(region='name', reason='conflicting_title', width=patch.width, height=patch.height)
    try:
        lines, scores = engine._run(patch)
        title = pick_confident_name(lines, scores)
        confidence = max((s or 0. for t, s in zip(lines, scores) if t == title), default=0.)
        record.update(lines=[dict(text=t, confidence=s) for t, s in zip(lines, scores)],
                      title=title, confidence=confidence)
        if not title or confidence < .90 or not title_observations_agree(original.name_text, title):
            return None, record
        observations = deepcopy(original)
        observations.name_text = title
        observations.lines.extend(lines)
        observations.hits.extend(OcrHit(t, s, 'name') for t, s in zip(lines, scores))
        return observations, record
    finally:
        record['ms'] = round((time.perf_counter() - started) * 1000, 2)
        patch.close()
