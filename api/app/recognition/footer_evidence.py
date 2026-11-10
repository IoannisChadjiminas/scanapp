"""Four footer-evidence rules from the retired sealed photos (all flags off by default).

Each rule only chooses which printing a review result shows first, or lets an existing review
through; none of them produces an automatic match.

PRINTING_EXACT_FRACTION: the footer reads one fraction cleanly (037/050) and it contradicts the
card shown (MDB-025, 025/046). When exactly one same-language card with the same title has that
number in a set with that printed total (BW5-Brn-037), that card is shown first and the photo
stays a printing review. Recovered cards have no vector of their own, so retrieval can only ever
find their twin; the fraction is the only evidence that tells the two apart.

PRINTING_BARE_NUMBER: promo and older Japanese footers print no total (113/DP-P reads "113").
Inside a printing group that already exists, one very confident bare number of three or more
digits that is one member's number, and not the shown card's, shows that member first.

OCR_SET_CODE_READ: a modern Japanese footer prints its set code beside the number (SM10a
027/054). Read as a lettered collector number, the code contradicts every card and blocks the
name-and-number lookup. A read that spells a set whose printed total equals the fraction's total
is the set code, not a collector number, and is taken out of the number reads.

RETRY_OWN_LANGUAGE: the boundary retry is judged against the first pass's languages. When the
first pass misread the script on a bad frame (an English card detected as Chinese) the retry is
thrown away although its own frame, name, fraction and language agree. A retry whose card is in
the retry's own languages and is confirmed by a clean fraction with the set's total is kept as a
review.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable

from app.recognition.rank import (accepted_collector_numbers, artwork_evidence_compatible,
                                  normalize_text, number_matches_identifiers, parse_collector)

MIN_READ_CONFIDENCE = 0.85
MIN_BARE_CONFIDENCE = 0.95


def _get(row: Any, key: str) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return None


def _titles(row: Any) -> set[str]:
    return {normalize_text(str(_get(row, key) or '')) for key in ('name', 'view_title')} - {''}


def _reliable(numbers) -> list:
    return [h for h in numbers or [] if getattr(h, 'region', None) == 'collector'
            and getattr(h, 'confidence', None) is not None and h.confidence >= MIN_READ_CONFIDENCE]


def clean_fraction(numbers):
    """(hit, number, total) when the footer's reliable fractions all say the same thing, else None."""
    found = {}
    for hit in _reliable(numbers):
        if '/' not in hit.text:
            continue
        parts = parse_collector(hit.text)
        if parts is None or parts.prefix or not parts.denominator or len(parts.denominator) < 2:
            return None
        found.setdefault((parts.number, parts.denominator), hit)
    if len(found) != 1:
        return None
    (number, total), hit = next(iter(found.items()))
    return hit, number, int(total)


def set_codes(set_id: str | None) -> set[str]:
    """How a footer spells a set: its id, and the id before a version suffix (BW1 for BW1-Bw)."""
    code = str(set_id or '').split(':')[-1].casefold()
    return {code, code.split('-')[0]} - {''}


def exact_fraction_printing(leader: dict[str, Any], numbers,
                            fetch: Callable[[str, list[str]], Iterable[Any]],
                            total_of: Callable[[Any], int | None]) -> str | None:
    """The one same-title card whose number and set total are the fraction read, else None.

    fetch(language, collector_numbers) returns the catalogue rows with one of those numbers;
    total_of(row) is the row's printed set total (None when unknown). A same-title card with that
    number in a set of unknown total could be the card too, so it leaves the question open.
    """
    read = clean_fraction(numbers)
    if read is None or not leader:
        return None
    hit, number, total = read
    if number_matches_identifiers([hit], accepted_collector_numbers(leader)) is not False:
        return None
    titles = _titles(leader)
    language = str(leader.get('language') or '')
    if not titles or not language:
        return None
    spellings = sorted({number, number.zfill(2), number.zfill(3)})
    exact, unknown = set(), set()
    for row in fetch(language, spellings):
        card_id = str(_get(row, 'id') or _get(row, 'card_id') or '')
        if not card_id or card_id == leader.get('card_id') or str(_get(row, 'language') or '') != language:
            continue
        parts = parse_collector(str(_get(row, 'collector_number') or ''))
        if parts is None or parts.prefix or parts.denominator or parts.number != number:
            continue
        if not titles & _titles(row):
            continue
        printed = parse_collector(str(_get(row, 'printed_collector_number') or ''))
        row_total = int(printed.denominator) if printed and printed.denominator else total_of(row)
        if row_total is None:
            unknown.add(card_id)
        elif row_total == total:
            exact.add(card_id)
    if len(exact) != 1 or unknown:
        return None
    return next(iter(exact))


def bare_number_printing(leader: dict[str, Any], members, numbers) -> str | None:
    """The one printing-group member named by a single confident bare footer number, else None."""
    reliable = _reliable(numbers)
    if not leader or any('/' in h.text for h in reliable):
        return None
    lettered = [h.text.casefold() for h in reliable if any(c.isalpha() for c in h.text)]
    bare = {}
    for hit in numbers or []:
        text = str(getattr(hit, 'text', ''))
        if (getattr(hit, 'region', None) != 'collector' or getattr(hit, 'confidence', None) is None
                or hit.confidence < MIN_BARE_CONFIDENCE or not text.isdigit() or len(text) < 3):
            continue
        # 100 or 230 is attack damage or HP far more often than a card number.
        if text[0] != '0' and int(text) % 10 == 0:
            continue
        bare[text.lstrip('0') or '0'] = hit
    if len(bare) != 1:
        return None
    number = next(iter(bare))

    def plain_number(row) -> str | None:
        parts = parse_collector(str(row.get('collector_number') or ''))
        return parts.number if parts and not parts.prefix and not parts.denominator else None

    if plain_number(leader) == number:
        return None
    named = {str(m.get('card_id')): m for m in members or ()
             if m.get('card_id') and m.get('card_id') != leader.get('card_id') and plain_number(m) == number}
    if len(named) != 1:
        return None
    card_id, member = next(iter(named.items()))
    # A lettered read may only be this member's own set code (SM6 beside 027).
    if any(code not in set_codes(member.get('set_id')) for code in lettered):
        return None
    return card_id


def drop_set_code_reads(numbers: list, sets: dict[str, list[tuple[str, str]]],
                        total_of: Callable[[str, str], int | None],
                        languages: tuple[str, ...] = ()) -> tuple[list, list[str]]:
    """Take out collector reads that spell a set whose printed total the fraction confirms.

    sets maps a casefolded set code to its (language, set_id) pairs. Returns the remaining reads
    and the codes removed.
    """
    read = clean_fraction(numbers)
    if read is None:
        return list(numbers or []), []
    _, _, total = read
    kept, dropped = [], []
    for hit in numbers or []:
        text = str(getattr(hit, 'text', ''))
        is_code = (hit in _reliable([hit]) and '/' not in text and any(c.isalpha() for c in text)
                   and any(c.isdigit() for c in text)
                   and any(total_of(language, set_id) == total
                           for language, set_id in sets.get(text.casefold(), ())
                           if not languages or language in languages))
        if is_code:
            dropped.append(text)
        else:
            kept.append(hit)
    return kept, dropped


def set_code_index(rows: Iterable[Any]) -> dict[str, list[tuple[str, str]]]:
    index: dict[str, set[tuple[str, str]]] = {}
    for row in rows:
        language, set_id = str(_get(row, 'language') or ''), str(_get(row, 'set_id') or '')
        for code in set_codes(set_id):
            index.setdefault(code, set()).add((language, set_id))
    return {code: sorted(pairs) for code, pairs in index.items()}


def retry_language_supported(lead: dict[str, Any] | None, *, first_name: str | None,
                             first_name_confidence: float, first_numbers,
                             retry_name: str | None, retry_name_confidence: float,
                             retry_numbers, retry_languages: tuple[str, ...]) -> bool:
    """A boundary retry rejected only over the first pass's languages, and confirmed by its footer.

    The first pass's name and numbers must still not contradict the card; the retry's own name,
    numbers and languages must not either; and the retry must read one clean fraction that is the
    card's number over its set's known total.
    """
    if not lead or not retry_languages or lead.get('language') not in retry_languages:
        return False
    if any(lead.get(key) for key in ('strong_name_conflict', 'structured_collector_conflict',
                                     'language_conflict')):
        return False
    if not artwork_evidence_compatible(lead, ocr_name=first_name, name_confidence=first_name_confidence,
                                       numbers=first_numbers, languages=retry_languages):
        return False
    if not artwork_evidence_compatible(lead, ocr_name=retry_name, name_confidence=retry_name_confidence,
                                       numbers=retry_numbers, languages=retry_languages):
        return False
    read = clean_fraction(retry_numbers)
    if read is None:
        return False
    structured = [n for n in accepted_collector_numbers(lead)
                  if (parts := parse_collector(n)) and parts.denominator]
    return bool(structured) and number_matches_identifiers([read[0]], structured) is True
