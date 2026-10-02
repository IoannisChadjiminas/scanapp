"""Literal holder metadata may order existing choices, never prove a printing.

This is a review-only hint scoped to one independently detected grading label.
No holder field supplies artwork identity, a translation, a missing catalogue
row, calibrated confidence, or an automatic card/finish confirmation.
"""
from __future__ import annotations

import math
import re

from app.recognition.grading import _condition, _label_identity, _text, brand_company
from app.recognition.rank import (
    accepted_collector_numbers, name_match, normalize_text, number_matches_identifiers,
    parse_collector,
)


def holder_printing_hint(rows, lines, *, printed_name, printed_name_confidence,
                         printed_numbers, language):
    """Return one existing same-name/language choice supported by set + #SKU.

    Every qualified printed fraction must still agree. Multiple holder number
    or set identities are an abstention. Weak/unlocated OCR cannot be a hint.
    """
    if not printed_name or printed_name_confidence < .85 or not language:
        return None
    reliable = [line for line in lines if line.box is not None
                and line.confidence is not None and math.isfinite(line.confidence)
                and line.confidence >= .85]
    texts = [_text(line.text) for line in reliable]
    # A brand watermark or a set name on its own does not establish a label.
    if (not any(_label_identity(t) for t in texts)
            or not any(_condition(t, None) for t in texts)
            or not (any(brand_company(t) for t in texts)
                    or any(re.fullmatch(r'(?:[A-Z])?\d{6,14}', t) for t in texts))):
        return None
    if not any(name_match(t, printed_name) for t in texts):
        return None
    numbers = {m.group(1).replace(' ', '') for text in texts
               for m in re.finditer(r'(?<![A-Z0-9])#\s*((?:[A-Z]{1,4})?\d{1,4}(?:\s*/\s*\d{1,4})?)(?![A-Z0-9/])', text)}
    if len(numbers) != 1:
        return None
    candidates = []
    for row in rows:
        if row.get('language') != language or not name_match(printed_name, row['name']):
            continue
        identifiers = accepted_collector_numbers(row)
        if number_matches_identifiers(list(numbers), identifiers) is not True:
            continue
        # Full expansion names, or literal standalone catalogue set codes.
        # No fuzzy set correction, release-year guess or provider alias table.
        set_name = normalize_text(row.get('set_name'))
        code = str(row.get('set_id') or '').upper()
        set_agrees = any((len(set_name) >= 6 and set_name in normalize_text(t))
                         or (re.fullmatch(r'[A-Z][A-Z0-9]{2,9}', code)
                             and re.search(r'(?<![A-Z0-9])'+re.escape(code)+r'(?![A-Z0-9])', t))
                         for t in texts)
        if not set_agrees:
            continue
        printed = [h for h in printed_numbers if h.region == 'collector'
                   and h.confidence is not None and math.isfinite(h.confidence)
                   and h.confidence >= .85 and (p := parse_collector(h.text))
                   and (p.denominator is not None or p.prefix)]
        if any(number_matches_identifiers([h], identifiers) is not True for h in printed):
            continue
        candidates.append(row['card_id'])
    return candidates[0] if len(candidates) == 1 else None
