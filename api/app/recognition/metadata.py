"""Bounded, read-only OCR retrieval alongside visual retrieval.

This proposes candidates; it does not certify them. Both visible identity fields
must be confidence-qualified. Missing or contradictory evidence is not guessed.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from app.recognition.identity import structured_identity_agrees
from app.recognition.ocr import OcrHit
from app.recognition.rank import accepted_collector_numbers, parse_collector, normalize_text, artwork_evidence_compatible, name_match


class MetadataCandidateIndex:
    def __init__(self, rows: Iterable[dict], *, indexed_ids: set[str]) -> None:
        self.by_number: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self.by_name: dict[str, list[dict]] = defaultdict(list)
        for source in rows:
            row = dict(source)
            if row['id'] not in indexed_ids:
                continue
            self.by_name[normalize_text(row['name'])].append(row)
            keys = { (p.prefix, p.number) for value in accepted_collector_numbers(row)
                     if (p := parse_collector(value)) is not None }
            for key in keys:
                self.by_number[key].append(row)

    def candidates(self, *, ocr_name: str | None, name_confidence: float,
                   numbers: list[OcrHit], languages: tuple[str, ...],
                   limit: int = 32, promo_codes: bool = False) -> list[str]:
        # With promo_codes (NUMBER_LED_LOOKUP) a lettered collector read such as BW53 or
        # SWSH204 is looked up the same way a fraction is; both still need the name to agree.
        reliable = [h for h in numbers if h.region == 'collector'
                    and h.confidence is not None and h.confidence >= .85
                    and ('/' in h.text or (promo_codes and any(c.isalpha() for c in h.text)
                                           and any(c.isdigit() for c in h.text)))]
        if name_confidence < .85 or not reliable:
            return []
        pool: dict[str, dict] = {}
        for hit in reliable:
            parts = parse_collector(hit.text)
            if parts is None:
                continue
            for row in self.by_number.get((parts.prefix, parts.number), ()):
                pool[row['id']] = row
        matches = sorted(row['id'] for row in pool.values()
                         if structured_identity_agrees(row, ocr_name=ocr_name,
                             name_confidence=name_confidence, numbers=numbers,
                             languages=languages))
        # Do not silently truncate an ambiguous family into a false singleton.
        return matches if len(matches) <= limit else []

    def geometry_candidates(self, *, ocr_name: str | None, name_confidence: float,
                            numbers: list[OcrHit], languages: tuple[str, ...],
                            limit: int = 64) -> list[str]:
        """Weak title search hypotheses requiring independent artwork geometry.

        Unknown language stays unknown; no title/confidence is corrected. This
        separate channel never qualifies as structured identity/printing proof.
        A partial or over-budget family is not returned as a singleton.
        """
        title=normalize_text(ocr_name)
        if name_confidence<.65 or len(title)<4:
            return []
        if any(h.region=='collector' and h.confidence is not None and h.confidence>=.85
               and ('/' in h.text or any(c.isalpha() for c in h.text)) for h in numbers):
            return []
        pool=list(self.by_name.get(title,()))
        if not pool:
            pool=[r for key,rows in self.by_name.items()
                  if len(key)>=4 and name_match(ocr_name,key) for r in rows]
        matches=sorted(r['id'] for r in pool
            if not languages or r.get('language') in languages)
        return matches if len(matches)<=limit else []

    def title_candidates(self, *, ocr_name: str | None, name_confidence: float,
                         numbers: list[OcrHit], languages: tuple[str, ...],
                         limit: int = 32) -> list[str]:
        """Propose an entire exact-title family for geometry-only review.

        Never silently truncate a common title or override explicit numbering.
        The pipeline requires local verification; a title is not printing proof.
        """
        title = normalize_text(ocr_name)
        if name_confidence < .85 or len(title) < 4 or not languages:
            return []
        if any(h.region == 'collector' and h.confidence is not None
               and h.confidence >= .85 and ('/' in h.text or any(c.isalpha() for c in h.text))
               for h in numbers):
            return []
        pool=list(self.by_name.get(title, ()))
        if not pool:
            # Existing name tolerance only proposes references; no OCR title
            # is rewritten, no confidence boosted, and local geometry remains
            # mandatory. Include the complete bounded family, not one guess.
            pool=[r for key,rows in self.by_name.items() if len(key)>=4
                  and name_match(ocr_name,key) for r in rows]
        matches = sorted(row['id'] for row in pool
                         if artwork_evidence_compatible(row, ocr_name=ocr_name,
                             name_confidence=name_confidence, numbers=numbers,
                             languages=languages))
        return matches if len(matches) <= limit else []

    def bare_number_candidates(self, *, ocr_name: str | None, name_confidence: float,
                               numbers: list[OcrHit], languages: tuple[str, ...],
                               limit: int = 3) -> list[str]:
        """A confident bare footer number plus a confident name that agrees (NUMBER_LED_LOOKUP).

        Only proposes: the cards still meet the artwork checks and the status rules. A bare number
        alone is weak, so the read must be very confident, the name must agree with the title,
        the language must match, and the family must be small.
        """
        from app.recognition.identity import review_title_agrees
        name = normalize_text(ocr_name)
        minimum = 2 if any(ord(c) > 0x2E80 for c in name) else 4
        if name_confidence < .85 or len(name) < minimum or not languages:
            return []
        if any(h.region == 'collector' and h.confidence is not None and h.confidence >= .85
               and ('/' in h.text or any(c.isalpha() for c in h.text)) for h in numbers):
            return []
        bare = [h for h in numbers if h.region == 'collector' and h.confidence is not None
                and h.confidence >= .95 and h.text.isdigit()]
        # Each bare read is judged on its own (damage values are bare numbers too). Exactly one
        # read may name a small family; two reads that both do are ambiguous.
        families = []
        for hit in bare:
            parts = parse_collector(hit.text)
            if parts is None:
                continue
            ids = {row['id'] for row in self.by_number.get(('', parts.number), ())
                   if row.get('language') in languages and review_title_agrees(ocr_name, row['name'])}
            if ids:
                families.append(ids)
        if len(families) != 1 or len(families[0]) > limit:
            return []
        return sorted(families[0])
