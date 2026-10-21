"""The phone's image-model vector, checked and then used only by the stage 1 gate.

The wire format is the JSON object the simulation and `stage0` already accept:
`{"model": "2ddf6ec79e37/coreml-pal8", "vector": "<base64 float16>"}`.
Parsing follows the checks from the device-hints branch: known model, 384
finite float16 values, and a vector that is already unit length.
"""
from __future__ import annotations

import base64
import binascii
import json
import re

import numpy as np

MODEL_ID = '2ddf6ec79e37/coreml-pal8'
DIM = 384
_MODEL = re.compile(r'^([0-9a-f]{12})/([a-z0-9][a-z0-9._-]{0,31})$')


def parse_client_embedding(raw: str | None, *, expected_model: str = MODEL_ID,
                           dim: int = DIM) -> tuple[np.ndarray | None, str]:
    """A unit vector, or None and why. Never raises."""
    if not raw:
        return None, 'absent'
    if len(raw) > 4 * dim + 128:
        return None, 'too_long'
    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError):
        return None, 'not_json'
    if not isinstance(body, dict):
        return None, 'not_json'
    model = body.get('model')
    vector = body.get('vector')
    match = _MODEL.fullmatch(model if isinstance(model, str) else '')
    expected = _MODEL.fullmatch(expected_model or '')
    if match is None or expected is None or match.group(1) != expected.group(1):
        return None, 'bad_model'
    if not isinstance(vector, str):
        return None, 'not_base64'
    try:
        data = base64.b64decode(vector, validate=True)
    except (binascii.Error, ValueError):
        return None, 'not_base64'
    if len(data) != 2 * dim:
        return None, 'bad_length'
    values = np.frombuffer(data, dtype='<f2').astype(np.float32)
    if not np.isfinite(values).all():
        return None, 'not_finite'
    norm = float(np.linalg.norm(values))
    if not 0.98 <= norm <= 1.02:
        return None, 'not_unit'
    return values / norm, 'ok'
