"""Accept and log the phone's stage-0 evidence.

Nothing here changes a scan's answer. Optional gate diagnostics describe the
search already performed by stage 1; logging never runs a second search.
"""
from __future__ import annotations

import base64
import json
import math
import re
from dataclasses import dataclass
from typing import Any

TEXT_MAX_BYTES = 1280
QUALITY_MAX_BYTES = 256
EMBEDDING_MAX_BYTES = 2048
EMBEDDING_DIM = 384
EMBEDDING_MODELS = frozenset({
    '2ddf6ec79e37/coreml-pal8',
    '2ddf6ec79e37/litert-fp16',
})

_ENGINE = re.compile(r'^[a-z0-9][a-z0-9._-]{0,31}$')
_NUMBER = re.compile(
    r'^(?:[A-Z]{0,5})?\d{1,4}[A-Z]?(?:/(?:[A-Z]{0,4})?\d{1,4})?$',
    re.IGNORECASE,
)
_GRADE = re.compile(r'^(?:10|[1-9](?:\.5)?)$')
_LETTER = re.compile(r'[^\W\d_]', re.UNICODE)
_SPACE = re.compile(r'\s+')
_LANGUAGES = frozenset({'en', 'ja', 'ko', 'zh'})
_GRADERS = frozenset({
    'PSA', 'CGC', 'BGS', 'BECKETT', 'ACE', 'SGC', 'AGS', 'TAG', 'HGA', 'PI',
})


@dataclass(frozen=True)
class PhoneEvidence:
    """What of the phone's evidence was usable. Missing pieces stay empty."""

    text: bool = False
    label: bool = False
    name: str | None = None
    number: str | None = None
    label_name: str | None = None
    embedding: bool = False
    sharpness: float | None = None
    card_fraction: float | None = None
    glare: float | None = None

    @property
    def quality(self) -> bool:
        return any(value is not None for value in (self.sharpness, self.card_fraction, self.glare))


def phone_evidence(
    client_text: str | None,
    client_quality: str | None,
    client_embedding: str | None,
) -> PhoneEvidence:
    """Parse the three fields. Garbage is absent evidence, never an error."""
    text = _text(client_text)
    quality = _quality(client_quality)
    return PhoneEvidence(
        text=text['text'],
        label=text['label'],
        name=text['name'],
        number=text['number'],
        label_name=text['label_name'],
        embedding=_embedding(client_embedding),
        sharpness=quality[0],
        card_fraction=quality[1],
        glare=quality[2],
    )


def stage0_line(result: Any, *, trace: str, source: Any, evidence: PhoneEvidence,
                stage1: str | None = None, stage1_reason: str | None = None,
                stage1_margin: float | None = None, stage1_ms: float | None = None,
                gate: Any = None, number_candidate: str | None = None) -> str:
    """One line per scan: what arrived, and whether it agrees with the answer.

    ``would=text`` is only a planning mark for stage 1: the phone's name and
    number both match the top suggestion. Only catalogue IDs and scores from
    an existing gate decision are added, never vectors or raw OCR text.
    """
    suggestions = list(getattr(result, 'suggestions', None) or [])
    top = suggestions[0] if suggestions else None
    top_name = getattr(top, 'name', None) if top is not None else None
    top_number = getattr(top, 'collector_number', None) if top is not None else None
    name_agree = _agree(evidence.name, top_name)
    number_agree = _agree(evidence.number, top_number, number=True)
    label_agree = _agree(evidence.label_name, top_name)
    would = 'text' if name_agree == 'true' and number_agree == 'true' else 'none'
    quad = getattr(source, 'quad', 'none') if source is not None else 'none'
    quad_valid = bool(getattr(source, 'quad_valid', False)) if source is not None else False
    parts = [
        'stage0',
        f'trace={trace or "none"}',
        f'scan_id={getattr(result, "id", "none")}',
        f'quad={quad}',
        f'quad_valid={str(quad_valid).lower()}',
        f'text={int(evidence.text)}',
        f'label={int(evidence.label)}',
        f'embedding={int(evidence.embedding)}',
        f'quality={int(evidence.quality)}',
        f'sharpness={_metric(evidence.sharpness, 1)}',
        f'card_fraction={_metric(evidence.card_fraction, 3)}',
        f'glare={_metric(evidence.glare, 3)}',
        f'name_agree={name_agree}',
        f'number_agree={number_agree}',
        f'label_name_agree={label_agree}',
        'vector_top=' + (_card_id(getattr(gate, 'vector_top', None)) if gate is not None else 'off'),
        f'would={would}',
    ]
    if gate is not None:
        parts.extend([
            'vector_top_score=' + _metric(getattr(gate, 'vector_top_score', None), 4),
            'text_candidates=' + (','.join(_card_id(cid) for cid in gate.text_candidates[:5]) or 'none'),
            f'text_candidate_count={gate.text_candidate_count}',
        ])
        if gate.reason == 'visual_contradiction':
            parts.extend([
                'contradicting_card=' + _card_id(gate.contradicting_card),
                'contradiction_gap=' + _metric(gate.contradiction_gap, 4),
            ])
    if stage1:
        parts.append(f'stage1={stage1}')
        parts.append(f'stage1_reason={stage1_reason or "none"}')
        parts.append('stage1_margin=' + ('none' if stage1_margin is None else f'{stage1_margin:.4f}'))
        parts.append('stage1_ms=' + ('none' if stage1_ms is None else f'{stage1_ms:.1f}'))
    if isinstance(number_candidate, str) and re.fullmatch(r'[A-Za-z0-9/#|().-]{1,16}', number_candidate):
        # The raw phone read that number repair turned into the number the gate used.
        parts.append(f'number_candidate={number_candidate}')
    return ' '.join(parts)


def _card_id(value: str | None) -> str:
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9:._-]{1,128}', value) else 'none'


def _text(raw: str | None) -> dict[str, Any]:
    empty: dict[str, Any] = {
        'text': False, 'label': False, 'name': None, 'number': None, 'label_name': None,
    }
    if not raw or len(raw.encode('utf-8', errors='replace')) > TEXT_MAX_BYTES:
        return empty
    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError):
        return empty
    if not isinstance(body, dict):
        return empty
    version = body.get('v')
    engine = body.get('engine')
    if version not in (1, 2) or not isinstance(engine, str) or not _ENGINE.match(engine):
        return empty
    name = _words(body.get('name'), 64)
    number = _number(body.get('number'))
    label_name = None
    label = False
    if version == 2:
        label_name = _words(body.get('label_name'), 64)
        label_number = _number(body.get('label_number'))
        label_set = _words(body.get('label_set'), 64)
        language = body.get('label_language')
        grader = body.get('label_grader')
        grade = body.get('label_grade')
        language_ok = isinstance(language, str) and language in _LANGUAGES
        grader_ok = isinstance(grader, str) and grader.upper() in _GRADERS
        grade_ok = isinstance(grade, str) and bool(_GRADE.match(grade))
        if grader_ok and grader.upper() == 'PSA' and grade == '9.5':
            grade_ok = False
        label = any((
            label_name, label_number, label_set, language_ok, grader_ok, grade_ok,
        ))
    if name is None and number is None and not label:
        return empty
    return {
        'text': True,
        'label': label,
        'name': name,
        'number': number,
        'label_name': label_name,
    }


def _quality(raw: str | None) -> tuple[float | None, float | None, float | None]:
    if not raw or len(raw.encode('utf-8', errors='replace')) > QUALITY_MAX_BYTES:
        return (None, None, None)
    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError):
        return (None, None, None)
    if not isinstance(body, dict):
        return (None, None, None)
    return (
        _unit(body.get('sharpness'), 0.0, 1_000_000.0),
        _unit(body.get('card_fraction'), 0.0, 1.0),
        _unit(body.get('glare'), 0.0, 1.0),
    )


def _embedding(raw: str | None) -> bool:
    """True when the vector is 384 float16 values for a known model.

    This reporting helper does not return or search the vector. The optional
    stage 1 gate validates and searches its own parsed copy separately.
    """
    if not raw or len(raw.encode('utf-8', errors='replace')) > EMBEDDING_MAX_BYTES:
        return False
    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError):
        return False
    if not isinstance(body, dict):
        return False
    model = body.get('model')
    vector = body.get('vector')
    if model not in EMBEDDING_MODELS or not isinstance(vector, str):
        return False
    try:
        decoded = base64.b64decode(vector, validate=True)
    except (ValueError, TypeError):
        return False
    return len(decoded) == EMBEDDING_DIM * 2


def _words(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > limit or not _LETTER.search(text):
        return None
    if any(ord(char) < 32 for char in text):
        return None
    return text


def _number(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > 16 or not _NUMBER.match(text.replace(' ', '')):
        return None
    return text


def _unit(value: Any, low: float, high: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number < low or number > high:
        return None
    return number


def _fold(value: str | None) -> str:
    if not value:
        return ''
    return _SPACE.sub(' ', value).strip().casefold()


def _number_key(value: str | None) -> str:
    if not value:
        return ''
    return re.sub(r'[\s-]', '', value).upper().split('/', 1)[0]


def _agree(phone: str | None, answer: str | None, *, number: bool = False) -> str:
    if not phone or not answer:
        return 'none'
    if number:
        left, right = _number_key(phone), _number_key(answer)
        if not left or not right:
            return 'none'
        return 'true' if left == right else 'false'
    return 'true' if _fold(phone) == _fold(answer) else 'false'


def _metric(value: float | None, digits: int) -> str:
    if value is None:
        return 'none'
    return f'{value:.{digits}f}'
