"""Whether a confident name read is a name, for local artwork verification.

Behind VERIFY_UNMATCHED_NAME. A blurry vintage photo can put other card text in the name strip
(PMCG4-017-2 read its evolution note モンスターカードに重ねて使います at 0.995). As a
"confident name" that read did two harmful things: it skipped local verification (the
close-neighbour trigger only fires for a weak name), and it vetoed the right card's artwork
(a Japanese-named row "does not match" it), while rows with English-only names stay neutral.

A confident read that names none of the shortlist's cards is no evidence of the card's name.
For the verification trigger and the artwork compatibility filters only, it counts as no name:
ranking and every other rule still see the read. Scoped to Japanese scans with no printed
collector fraction, where the name is otherwise the strongest text evidence. The rule itself
does not depend on the language.
"""
from __future__ import annotations

from typing import Any

from app.recognition.ocr import OcrHit
from app.recognition.rank import name_match
from app.recognition.text_identity import confident_fractions

MIN_CONFIDENT_NAME = .85


def in_scope(languages: tuple[str, ...], numbers: list[OcrHit]) -> bool:
    """A Japanese scan that read no printed collector fraction."""
    return 'ja' in languages and not confident_fractions(numbers)


def names_a_candidate(ocr_name: str | None, candidates: list[dict[str, Any]]) -> bool:
    return any(name_match(ocr_name, str(row.get('name') or ''))
               or (row.get('view_title') and name_match(ocr_name, str(row['view_title'])))
               for row in candidates)


def verification_name(ocr_name: str | None, name_confidence: float, candidates: list[dict[str, Any]],
                      *, languages: tuple[str, ...], numbers: list[OcrHit]) -> tuple[str | None, float, bool]:
    """The (name, confidence) local verification should use, and whether the read was set aside."""
    if (ocr_name and name_confidence >= MIN_CONFIDENT_NAME and candidates
            and in_scope(languages, numbers) and not names_a_candidate(ocr_name, candidates)):
        return None, 0.0, True
    return ocr_name, name_confidence, False
