from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any
import unicodedata

from app.config import get_settings
from app.recognition.ocr import OcrHit

COLLECTOR_RE = re.compile(
    r"\b((?:[A-Z]{1,4})?\d{1,4}(?:[A-Z])?(?:/\d{1,4})?)\b",
    re.IGNORECASE,
)
COLLECTOR_PARTS_RE = re.compile(
    r"^([A-Z]{1,4})?(\d{1,4})(?:[A-Z])?(?:/(\d{1,4}))?$",
    re.IGNORECASE,
)
RELIABLE_COLLECTOR_CONF = 0.55
NON_COLLECTOR_NUMBER_RE = re.compile(
    r"(?:[×x]\s*\d+|(?<!\w)[−–-]\s*\d+\b|#\s*\d+|\b(?:HP|LV\.?|IV|STAGE)\s*\d+|\d+\s*HP\b)",
    re.IGNORECASE,
)
# These are set abbreviations, not the distinct TG/GG/SM/SWSH collector
# namespaces. Only remove a known code when it directly precedes a fraction.
MODERN_SET_CODES = ('SVI', 'PAL', 'OBF', 'MEW', 'PAR', 'PAF', 'TEF',
                    'TWM', 'SFA', 'SCR', 'SSP', 'PRE', 'JTG', 'DRI')
# Set codes that print glued to the front of a fraction (30C077/128, 30CEN 077/128, SV077/198) when
# OCR_SET_CODE_PREFIX is on. Uppercase only: a lowercase or noisy read is not trusted.
GLUED_SET_CODE_RE = re.compile(r'(?<![A-Z0-9])(?:30C(?:EN|JP|JA)?|SV(?=\d{3}/))(?=\d{1,4}/\d{1,4})')
# Promo sets whose printed collector number carries the set id as a prefix (MEP078 for
# catalogue number 078). SVP is always accepted; the rest only under OCR_SET_CODE_PREFIX.
PROMO_NUMBER_PREFIX = {'mep': 'MEP', 'swshp': 'SWSH', 'smp': 'SM', 'bwp': 'BW', 'dpp': 'DP',
                       'hgssp': 'HGSS', 'xyp': 'XY'}
# Boxed modern regulation marks can touch the numeric fraction in OCR. This
# cleanup is OCR-only: catalogue IDs and real collector namespaces are intact.
REGULATION_FRACTION_RE = re.compile(r'\b[D-J](?=\d{1,4}/\d{1,4}\b)', re.IGNORECASE)


@dataclass(frozen=True)
class CollectorParts:
    prefix: str
    number: str
    denominator: str | None
    raw: str


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in text if char.isalnum())


def similar(a: str, b: str) -> float:
    left = normalize_text(a)
    right = normalize_text(b)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def set_code_prefix_enabled() -> bool:
    return bool(get_settings().ocr_set_code_prefix)


def promo_prefix_near_enabled() -> bool:
    return bool(get_settings().ocr_promo_prefix_near)


def cutoff_total_enabled() -> bool:
    return bool(get_settings().ocr_cutoff_total)


def _cutoff_total(read: str, total: str) -> bool:
    """OCR_CUTOFF_TOTAL: a set total that lost only its last digit at the edge of the read
    ("9/10" for 9/108). One digit, never two, and the read must keep at least two digits."""
    return len(read) >= 2 and len(total) == len(read) + 1 and total.startswith(read)


def bare_number_guard_enabled() -> bool:
    return bool(get_settings().rank_bare_number_guard)


def pokedex_number_enabled() -> bool:
    return bool(get_settings().rank_pokedex_number)


# RANK_POKEDEX_NUMBER: Japanese sets whose cards print no collector number. The catalogue
# number is only the set order (TCG Collector's "No. 001"); the number these cards print is
# the Pokedex number, e.g. "No.006" on Charizard PMCG1-021 (catalogue 021).
UNNUMBERED_SETS = frozenset(('ja', set_id) for set_id in (
    'pmcg1', 'pmcg2', 'pmcg3', 'pmcg4', 'pmcg5', 'pmcg6', 'neo1', 'neo2', 'neo3', 'neo4'))


def number_not_printed(item: dict[str, Any]) -> bool:
    """Whether the card prints no collector number."""
    if item.get('printed_collector_number'):
        return False
    set_id = str(item.get('set_id') or '').split(':')[-1]
    if not set_id:
        # Stored scans keep the card id only: ja:PMCG1-021.
        set_id = str(item.get('card_id') or '').split(':')[-1].rpartition('-')[0]
    return (str(item.get('language') or ''), set_id.lower()) in UNNUMBERED_SETS


def _species_key(name: str) -> str:
    # normalize_text drops the symbols that tell Nidoran female from male.
    return normalize_text(name.replace('♀', 'f').replace('♂', 'm'))


@lru_cache(maxsize=1)
def _pokedex_species() -> dict[int, tuple[str, ...]]:
    data = json.loads((Path(__file__).with_name('assets')/'pokedex_gen1_2.json').read_text(encoding='utf-8'))
    return {int(number): tuple(names) for number, names in data['species'].items()}


def species_names(number: int) -> tuple[str, ...]:
    """The English and Japanese names of a Gen 1-2 species, e.g. (リザードン, Charizard)."""
    return _pokedex_species().get(number, ())


@lru_cache(maxsize=1)
def _pokedex_names() -> dict[str, int]:
    """Gen 1-2 species names (English and Japanese) to Pokedex number; ambiguous names dropped."""
    found: dict[str, set[int]] = {}
    for number, names in _pokedex_species().items():
        for name in names:
            if key := _species_key(name):
                found.setdefault(key, set()).add(int(number))
    return {key: next(iter(numbers)) for key, numbers in found.items() if len(numbers) == 1}


@lru_cache(maxsize=8192)
def pokedex_number(name: str | None) -> int | None:
    """The species in a card name, longest match: わるいリザードン, Erika's Oddish, アンノーンK.

    Two different species of the same length in one name stay unknown, as do Trainers and Energy.
    """
    key = _species_key(name or '')
    if not key:
        return None
    hits = [(len(species), number) for species, number in _pokedex_names().items() if species in key]
    if not hits:
        return None
    longest = max(length for length, _ in hits)
    numbers = {number for length, number in hits if length == longest}
    return next(iter(numbers)) if len(numbers) == 1 else None


def _pokedex_read(hit: OcrHit | str, dex: int | None) -> bool:
    """A read without total or set code that is the card's printed Pokedex number."""
    parsed = parse_collector(hit.text if isinstance(hit, OcrHit) else str(hit))
    return bool(dex and parsed and not parsed.prefix and not parsed.denominator
                and parsed.number == str(dex))


# RANK_BARE_NUMBER_GUARD: how much weaker than the visual leader a card's picture may be before
# a bare number alone ("20", no total, no set code) can no longer put it first.
BARE_NUMBER_MAX_DROP = 0.15


# A promo prefix read as MP078 or ME078 for MEP078: exactly 3 digits, letters one edit away.
PROMO_NEAR_RE = re.compile(r'([A-Z]{2,4})(\d{3})')


def _one_letter_apart(read: str, canonical: str) -> bool:
    """True for one missing letter, one wrong letter, or one swapped pair.

    A 3-letter set id may lose one letter; a 2-letter id (SM, BW) may not, so a
    stray letter cannot turn into a whole other set code.
    """
    if read == canonical:
        return False
    if len(read) == len(canonical) - 1 and len(canonical) >= 3:
        return any(canonical[:i] + canonical[i + 1:] == read for i in range(len(canonical)))
    if len(read) != len(canonical):
        return False
    differing = [i for i, (a, b) in enumerate(zip(read, canonical)) if a != b]
    if len(differing) == 1:
        return True
    first, second = differing if len(differing) == 2 else (-1, -1)
    return second == first + 1 and read[first] == canonical[second] and read[second] == canonical[first]


def _near_promo_identifier(text: str, identifiers: list[str]) -> bool:
    """MP078 agrees with a catalogue MEP078 identifier only under OCR_PROMO_PREFIX_NEAR.

    Only the promo table's own set ids count. The read must be uppercase, with the
    same 3 digits and a prefix one letter away; any other read stays a conflict.
    """
    if not promo_prefix_near_enabled():
        return False
    read = PROMO_NEAR_RE.fullmatch(text.replace(' ', ''))
    if not read:
        return False
    for identifier in identifiers:
        expected = PROMO_NEAR_RE.fullmatch(identifier.replace(' ', ''))
        if (expected and expected.group(2) == read.group(2)
                and expected.group(1) in PROMO_NUMBER_PREFIX.values()
                and _one_letter_apart(read.group(1), expected.group(1))):
            return True
    return False


def _promo_set_prefix(item: dict[str, Any]) -> str | None:
    return PROMO_NUMBER_PREFIX.get(str(item.get('set_id') or '').split(':')[-1].lower())


def promo_bare_number_agrees(ocr_name: str | None, item: dict[str, Any],
                             candidates: list[dict[str, Any]]) -> bool:
    """A bare promo number (078) agrees only when the name and number name exactly one promo card."""
    number = parse_collector(str(item.get('collector_number') or ''))
    if not _promo_set_prefix(item) or number is None or not ocr_name or not name_match(ocr_name, item['name']):
        return False
    same = [row for row in candidates if _promo_set_prefix(row)
            and (other := parse_collector(str(row.get('collector_number') or ''))) is not None
            and other.number == number.number and name_match(ocr_name, row.get('name') or '')]
    return len(same) == 1 and same[0].get('card_id') == item.get('card_id')


def parse_collector(value: str | None) -> CollectorParts | None:
    compact = (value or "").replace(" ", "").upper()
    if not compact:
        return None
    match = COLLECTOR_PARTS_RE.fullmatch(compact)
    if not match:
        fraction = re.search(r"^([A-Z]{1,4})?(\d{1,4})/(\d{1,4})$", compact)
        if not fraction:
            return None
        match = fraction
    prefix = (match.group(1) or "").upper()
    number = (match.group(2) or "").lstrip("0") or "0"
    denom_raw = match.group(3) if match.lastindex and match.lastindex >= 3 else None
    denominator = None
    if denom_raw:
        denominator = denom_raw.lstrip("0") or "0"
    return CollectorParts(prefix=prefix, number=number, denominator=denominator, raw=compact)


def extract_collector_candidates(
    lines: list[str],
    hits: list[OcrHit] | None = None,
) -> list[OcrHit]:
    found: list[OcrHit] = []
    seen: set[str] = set()
    # Japanese numeric set fractions followed by rarity establish footer
    # layout context. An isolated SV7 beside 131/102 SAR is a set code, not
    # an English shiny-vault collector. Preserve SV collectors otherwise.
    japanese_numeric_footer = any(re.search(
        r'(?i)(?<![A-Z0-9])\d{1,4}\s*/\s*\d{1,4}\s*(?:SAR|SR|AR|UR|RR|SSR|CHR|CSR)\b', text)
        for text in [*lines, *(h.text for h in hits or [] if h.region == 'collector')])

    def add(item: OcrHit) -> None:
        token = item.text.upper().replace(" ", "")
        if not token:
            return
        if token in seen:
            # A real footer observation must retain its region/confidence even
            # when a holder label happened to propose the same bare number.
            previous=next(h for h in found if h.text == token)
            if previous.region == 'holder_collector' and item.region == 'collector':
                found.remove(previous)
                found.append(OcrHit(token,item.confidence,item.region))
            elif (previous.region == item.region == 'collector'
                    and item.confidence is not None
                    and (previous.confidence is None or item.confidence > previous.confidence)):
                # Keep the strongest literal observation of this identical
                # footer token. Do not pool confidence across retries or
                # discard any different (possibly conflicting) token.
                found.remove(previous)
                found.append(OcrHit(token,item.confidence,item.region))
            return
        if parse_collector(token) is None:
            return
        seen.add(token)
        found.append(OcrHit(text=token, confidence=item.confidence, region=item.region))

    # Holder labels are explicitly labelled evidence, not bottom-of-card OCR.
    # Only an isolated #SKU next to grading boilerplate qualifies; its role is
    # a review-only ranking hint, never a hard contradiction/printing proof.
    if hits and any(h.region == 'name' and h.confidence is not None and h.confidence >= .85
                    and re.fullmatch(r'(?i)\s*GEM\s*MT\s*',h.text) for h in hits):
        for hit in hits:
            if hit.region == 'name' and hit.confidence is not None and hit.confidence >= .85:
                match=re.fullmatch(r'\s*#\s*([A-Za-z]{0,4}\d{1,4})\s*',hit.text)
                if match:
                    add(OcrHit(match[1],hit.confidence,'holder_collector'))

    def tokens(text: str) -> list[str]:
        # Bottom-of-card OCR also contains weakness, level and Pokedex text.
        # Region/confidence alone cannot make those numbers collectors.
        cleaned = NON_COLLECTOR_NUMBER_RE.sub(" ", text)
        if (re.search(r'(?i)(?:©|copyright|Nintendo|GAME\s*FREAK|\bIllus\b)', cleaned)
                or re.search(r'(?i)\bL[VY]\.?\s*\d+', text)
                or len(re.findall(r'\b[a-z]{3,}\b', text)) >= 4):
            # Older frames print the collector fraction on the copyright
            # line itself. Keep explicit fractions, not years/artist numbers.
            fractions = re.findall(r'(?i)\b((?:TG|GG)?\d{1,4}/(?:TG|GG)?\d{1,4})\b', cleaned)
            return [token for fraction in fractions for token in tokens(fraction)]
        compact = cleaned.replace(' ','')
        if set_code_prefix_enabled():
            compact = GLUED_SET_CODE_RE.sub('', compact)
        # Legacy Japanese set codes can abut their three-digit footer number.
        # Require a complete known series + fraction + printed rarity suffix;
        # English SM promo collectors and arbitrary prefix letters stay intact.
        compact = re.sub(r'(?i)^(?:SM|5M)(?:1[0-2]|[1-9])[A-Z]?(?=\d{3,4}/\d{3}(?:SAR|SR|AR|UR|RR|SSR|CHR|CSR)$)',
                         '',compact)
        if japanese_numeric_footer and re.fullmatch(r'(?i)SV\d{1,2}', compact):
            return []
        # OCR may attach regulation/set text to a fraction and repeat its
        # gallery namespace in the denominator. Retain the gallery prefix;
        # do not treat its denominator as a second bare collector number.
        compact = re.sub(r'(?i)^(?:[D-J])?S[VY]\d+[A-Z]?(?=\d{3,4}/)', '', compact)
        compact = re.sub(r'(?i)^[A-Z]?[D-J](?=(TG|GG)\d+/\1\d+\b)', '', compact)
        compact = re.sub(r'(?i)^(?:[D-J]|M[D-J])(?=(?:TG|GG)\d+/)', '', compact)
        compact = re.sub(r'(?i)\b(TG|GG)(\d{1,4})/\1(\d{1,4})\b', r'\1\2/\3', compact)
        # Modern set/language codes abut a numeric fraction in OCR, e.g.
        # PAL EN 269/193 or SV2a 173/165. They are not collector prefixes.
        compact = re.sub(r'(?i)\b[A-Z]{2,6}(?:EN|JP|JA)(?=\d{1,4}/\d{1,4})','',compact)
        compact = re.sub(r'(?i)\bSV\d+[A-Z]?(?=\d{1,4}/\d{1,4})','',compact)
        compact = re.sub(r'(?i)\b(?:' + '|'.join(MODERN_SET_CODES) +
                         r')(?:EN|E|N)?(?=\d{1,4}/\d{1,4})', '', compact)
        # McDonald's promos print M24 EN immediately before 001/015. The digits
        # hide it from the letter-only set-code rule, which otherwise keeps 015.
        compact = re.sub(r'(?i)\bM\d{2}(?:EN|JP|JA)?[D-J]?(?=\d{1,4}/\d{1,4})', '', compact)
        # Japanese rarity follows the denominator without a space in OCR.
        compact = re.sub(r'(?i)(/\d{1,4})(?:SAR|SR|AR|UR|RR|SSR|CHR|CSR)\b',
                         r'\1', compact)
        # "D 201/202" is regulation D + collector 201/202, not namespace D.
        # Never strip arbitrary letters, multi-letter TG/GG/SM prefixes, or a
        # bare promo number such as D201. Preserve the hit's actual confidence.
        compact = REGULATION_FRACTION_RE.sub('', compact)
        # An isolated alphanumeric Japanese set code (SV2a) must not become
        # the synthetic collector SV2A. Preserve plain SV2 shiny-vault IDs.
        if re.fullmatch(r'(?i)(?:SV\d+[A-Z]|S\d+[A-Z])', compact):
            return []
        return COLLECTOR_RE.findall(compact)

    # Scarlet/Violet promos print an isolated set/language code followed by
    # bare digits. Preserve the explicitly observed namespace; incidental HP
    # or retreat numbers without this adjacent footer code cannot qualify.
    for code,digits in zip(hits or [],(hits or [])[1:]):
        if (code.region==digits.region=='collector' and code.confidence is not None
                and digits.confidence is not None and min(code.confidence,digits.confidence)>=.85
                and re.fullmatch(r'(?i)SVP\s*EN',code.text.strip())
                and re.fullmatch(r'\d{3}',digits.text.strip())):
            add(OcrHit('SVP'+digits.text.strip(),min(code.confidence,digits.confidence),'collector'))
    for hit in hits or []:
        if hit.region == "name":
            continue
        for match in tokens(hit.text):
            add(OcrHit(text=match, confidence=hit.confidence, region=hit.region))
    for line in lines:
        for match in tokens(line):
            add(OcrHit(text=match, region="unknown"))
    return found


def name_match(ocr_name: str | None, card_name: str) -> bool:
    if not ocr_name:
        return False
    # Catalogue listings append the depicted professor, but the printed title
    # is still "Professor's Research". Do not generally strip parentheses:
    # other cards can encode meaningful form/variant identity there.
    professor = re.fullmatch(r"(?i)(professor['’]s\s+research)\s+\(professor\s+[^)]+\)",card_name)
    if professor:
        card_name = professor.group(1)
    score = similar(ocr_name, card_name)
    left = normalize_text(ocr_name)
    right = normalize_text(card_name)
    if score >= 0.72:
        return True
    cjk = any(ord(char) > 0x2E80 for char in left)
    min_len = 2 if cjk else 4
    if left and right and len(left) >= min_len and (left in right or right in left):
        return True
    return False


def number_match(
    ocr_numbers: list[str] | list[OcrHit],
    collector_number: str,
) -> bool | None:
    expected = parse_collector(collector_number)
    if expected is None:
        return None
    parsed: list[CollectorParts] = []
    for token in ocr_numbers:
        text = token.text if isinstance(token, OcrHit) else str(token)
        parts = parse_collector(text)
        if parts:
            parsed.append(parts)
    if not parsed:
        return None
    for got in parsed:
        if got.prefix != expected.prefix:
            continue
        if got.number != expected.number:
            continue
        if got.denominator and expected.denominator and got.denominator != expected.denominator:
            if not (cutoff_total_enabled() and _cutoff_total(got.denominator, expected.denominator)):
                continue
        return True
    return False


def number_matches_identifiers(hits: list[OcrHit] | list[str], identifiers: list[str]) -> bool | None:
    """Prefer known printed denominators to incomplete catalogue aliases.

    A bare catalogue ID (186) must not make 186/198 agree with a known printed
    identifier 186/195. Unknown denominators remain unknown, not fabricated.
    """
    identifiers = [n for n in identifiers if parse_collector(n) is not None]
    if not identifiers:
        return None
    results = []
    structured = [n for n in identifiers if (p := parse_collector(n)) and p.denominator]
    for hit in hits:
        text = hit.text if isinstance(hit, OcrHit) else str(hit)
        parsed = parse_collector(text)
        if parsed is None:
            continue
        expected = structured if parsed.denominator and structured else identifiers
        results.append(any(number_match([hit], n) is True for n in expected)
                       or _near_promo_identifier(text, identifiers))
    return any(results) if results else None


def fraction_named_printing(ranked: list[dict[str, Any]], members, hits) -> str | None:
    """Show the one printing named by a footer fraction that rejects the current card.

    An unknown number does not move the display. Two agreeing printings stay
    unresolved. This chooses the shown card and does not confirm the finish.
    """
    reliable = [hit for hit in hits if isinstance(hit, OcrHit) and hit.region == 'collector'
                and hit.confidence is not None and hit.confidence >= .85 and '/' in hit.text]
    if not reliable or not ranked:
        return None

    def verdicts(row: dict[str, Any]) -> list[bool | None]:
        return [number_matches_identifiers([hit], accepted_collector_numbers(row)) for hit in reliable]

    rows = [row for row in (members or ranked) if row.get('card_id')]
    matched = [row for row in rows if (found := verdicts(row)) and all(item is True for item in found)]
    leader = verdicts(ranked[0])
    if len(matched) != 1 or not leader or any(item is not False for item in leader):
        return None
    return str(matched[0].get('card_id'))


# Characters the footer reader confuses with digits when they sit inside a number.
LOOKALIKE_DIGITS = {'Z': '7', 'O': '0', 'I': '1', 'L': '1', 'S': '5', 'B': '8'}
_DAMAGED_FRACTION_RE = re.compile(r'^[A-Z]{0,4}([0-9A-Z]{1,5})/([0-9A-Z]{1,5})$')


def _damaged_fraction(text: str) -> tuple[str, str] | None:
    """Digits of a footer fraction that holds look-alike letters, else None.

    A clean read returns None so it stays with the normal matcher.
    """
    match = _DAMAGED_FRACTION_RE.fullmatch((text or '').replace(' ', '').upper())
    if not match:
        return None
    parts, damaged = [], False
    for part in match.groups():
        digits = ''
        for position, char in enumerate(part):
            if char.isdigit():
                digits += char
            elif char in LOOKALIKE_DIGITS and position > 0:
                digits += LOOKALIKE_DIGITS[char]
                damaged = True
            else:
                return None
        parts.append(digits)
    return (parts[0], parts[1]) if damaged else None


def _fits_damaged_fraction(read: tuple[str, str], identifier: str) -> bool:
    expected = re.fullmatch(r'[A-Za-z]{0,4}(\d{1,4})(?:[A-Za-z])?(?:/(\d{1,4}))?', identifier.replace(' ', ''))
    if not expected:
        return False
    number, denominator = read
    width = max(len(number), len(expected.group(1)))
    if number.zfill(width) != expected.group(1).zfill(width):
        return False
    if expected.group(2) is None:
        # The catalogue has no printed total for this card. Zero padding is
        # then the evidence: "007" fits a card numbered 007, not one numbered 7.
        return len(number) >= 2 and number == expected.group(1)
    # The denominator can lose its last digit: "03" against 034.
    printed, got = expected.group(2), denominator
    return got.lstrip('0') == printed.lstrip('0') or (len(got) >= 2 and printed.startswith(got))


def damaged_footer_named_printing(ranked: list[dict[str, Any]], members, hits) -> str | None:
    """Show the one printing that fits a footer fraction read with look-alike characters.

    Used only when a printing group is unproven. Zero or several fitting
    printings leave the order alone; this never confirms a printing.
    """
    reads = [read for hit in hits if isinstance(hit, OcrHit) and hit.region == 'collector'
             and hit.confidence is not None and hit.confidence >= RELIABLE_COLLECTOR_CONF
             and (read := _damaged_fraction(hit.text))]
    if len(reads) != 1 or not ranked:
        return None
    rows = [row for row in (members or ranked) if row.get('card_id')]
    fitting = [row for row in rows if any(_fits_damaged_fraction(reads[0], number)
                                          for number in accepted_collector_numbers(row))]
    if len(fitting) != 1 or fitting[0].get('card_id') == ranked[0].get('card_id'):
        return None
    return str(fitting[0].get('card_id'))


def accepted_collector_numbers(item: dict[str, Any]) -> list[str]:
    numbers = [str(item.get("collector_number") or "")]
    printed = str(item.get("printed_collector_number") or "")
    if printed and printed not in numbers:
        numbers.append(printed)
    # A known printed set total qualifies a bare numeric catalogue number.
    # Otherwise 3/185 falsely agrees with Torchic #3 from a 12-card set.
    # Explicit printed aliases take precedence: a reprint may retain its
    # original number/denominator rather than the reprint set's total.
    number = parse_collector(numbers[0])
    total = item.get("set_total")
    if (not printed and number and not number.prefix and not number.denominator
            and type(total) is int and total > 0):
        numbers.append(f"{numbers[0]}/{total}")
    if str(item.get('set_id') or '').lower()=='svp' and re.fullmatch(r'\d{1,3}',numbers[0]):
        numbers.append('SVP'+numbers[0].zfill(3))
    promo_prefix = PROMO_NUMBER_PREFIX.get(str(item.get('set_id') or '').split(':')[-1].lower())
    if promo_prefix and (set_code_prefix_enabled() or promo_prefix_near_enabled()) and re.fullmatch(r'\d{1,3}', numbers[0]):
        numbers.append(promo_prefix + numbers[0].zfill(3))
    return [number for number in numbers if number]


def name_evidence_comparable(ocr_name: str | None, item: dict[str, Any]) -> bool:
    """A missing localized catalogue title is unknown, not a translation.

    Some localized rows contain a Latin provider title. Do not invent aliases
    or compare different scripts as a strong contradiction. This only applies
    to an explicitly localized row, never a foreign-language candidate.
    """
    observed, expected = normalize_text(ocr_name), normalize_text(item['name'])
    return not (item.get('language') in {'ja', 'ko', 'zh', 'zh-cn', 'zh-tw'}
        and any(ord(c) > 0x2E80 for c in observed)
        and expected and all(ord(c) < 128 for c in expected))


def artwork_evidence_compatible(item: dict[str, Any], *, ocr_name: str | None,
                                name_confidence: float, numbers: list[OcrHit],
                                languages: tuple[str, ...]) -> bool:
    """Artwork rescue must not override strong, structured identity evidence.

    Bare numbers in a misaligned bottom ROI (HP/weakness/attack costs) are not
    printing proof. They can still lower ordinary ranking, but cannot veto
    geometric artwork verification. Unknown evidence remains neutral.
    """
    if languages and item.get("language") not in languages:
        return False
    name = normalize_text(ocr_name)
    min_name_length = 2 if any(ord(c) > 0x2E80 for c in name) else 4
    if name_evidence_comparable(ocr_name, item) and name_confidence >= .85 and len(name) >= min_name_length and not name_match(ocr_name, item["name"]):
        return False
    reliable = [h for h in numbers if h.region == "collector" and
                h.confidence is not None and h.confidence >= .85 and
                ("/" in h.text or any(c.isalpha() for c in h.text))]
    expected = accepted_collector_numbers(item)
    return not any(expected and number_matches_identifiers([h], expected) is False for h in reliable)


def _match_any(
    ocr_numbers: list[str] | list[OcrHit],
    collector_numbers: list[str],
) -> bool | None:
    return number_matches_identifiers(ocr_numbers, collector_numbers)


def _has_reliable_conflict(
    ocr_numbers: list[OcrHit] | list[str],
    collector_numbers: list[str],
) -> bool:
    hits = [
        item
        for item in ocr_numbers
        if isinstance(item, OcrHit) and item.reliable
    ]
    if not hits:
        return False
    return _match_any(hits, collector_numbers) is False


def rerank(
    visual: list[dict[str, Any]],
    ocr_name: str | None,
    ocr_numbers: list[str] | list[OcrHit],
    ocr_failed: bool,
    detected_languages: tuple[str, ...] = (),
    name_confidence: float | None = None,
    require_confident_ocr: bool = False,
) -> list[dict[str, Any]]:
    name_weight = (max(0.0, min(1.0, name_confidence or 0.0))
                   if require_confident_ocr else 1.0)
    known_numbers = [h for h in ocr_numbers if isinstance(h, OcrHit) and
                     h.confidence is not None and h.region == "collector"]
    # A visible explicit identifier takes precedence over incidental footer
    # values (retreat costs, years, attack damage). Conflicting explicit
    # identifiers are all retained; a later reading cannot erase one.
    explicit = [h for h in known_numbers if h.confidence >= .85
                and ('/' in h.text or any(c.isalpha() for c in h.text))]
    if require_confident_ocr and explicit:
        known_numbers = explicit
    guard = bare_number_guard_enabled()
    pokedex = pokedex_number_enabled()
    ranked: list[dict[str, Any]] = []
    for item in visual:
        combined = float(item["visual_score"])
        consistent: bool | None = None
        name_ok = name_match(ocr_name, item["name"])
        comparable_name = name_evidence_comparable(ocr_name, item)
        numbers = accepted_collector_numbers(item)
        if (promo_prefix_near_enabled() and _promo_set_prefix(item)
                and not promo_bare_number_agrees(ocr_name, item, visual)):
            # A bare 078 is not promo proof unless its name and number name one promo card.
            numbers = [n for n in numbers if (parts := parse_collector(n)) and parts.prefix]
        item_numbers, item_known = ocr_numbers, known_numbers
        if pokedex and number_not_printed(item):
            # The card's printed No.006 says nothing either way; any other number still conflicts.
            dex = pokedex_number(item.get("name"))
            item_numbers = [h for h in ocr_numbers if not _pokedex_read(h, dex)]
            item_known = [h for h in known_numbers if not _pokedex_read(h, dex)]
        number_ok = _match_any(item_numbers, numbers)
        collector_conflict = _has_reliable_conflict(item_known if require_confident_ocr else item_numbers, numbers)
        language = str(item.get("language") or "")
        if detected_languages:
            if language in detected_languages:
                combined += 0.05
            elif language:
                combined -= 0.04
        if ocr_failed:
            consistent = None
        elif require_confident_ocr:
            match_weight = max((max(0.0, min(1.0, h.confidence)) for h in item_known
                                if _match_any([h], numbers) is True), default=0.0)
            conflict_weight = max((max(0.0, min(1.0, h.confidence)) for h in item_known
                                   if _match_any([h], numbers) is False), default=0.0)
            combined += .08*match_weight - .12*conflict_weight
            if not explicit and name_ok and name_weight >= .85:
                holder_weight=max((h.confidence or 0. for h in item_numbers
                    if isinstance(h,OcrHit) and h.region == 'holder_collector'
                    and _match_any([h],numbers) is True),default=0.)
                combined += .08*holder_weight
            if collector_conflict:
                combined -= .08*conflict_weight
            if name_ok:
                combined += .06*name_weight
            elif comparable_name and ocr_name and similar(ocr_name, item["name"]) < .4:
                combined -= .04*name_weight
            if collector_conflict or (conflict_weight >= RELIABLE_COLLECTOR_CONF and
                                      match_weight < RELIABLE_COLLECTOR_CONF):
                consistent = False
            elif match_weight >= RELIABLE_COLLECTOR_CONF or (name_ok and name_weight >= RELIABLE_COLLECTOR_CONF):
                consistent = True
            elif comparable_name and ocr_name and name_weight >= RELIABLE_COLLECTOR_CONF and similar(ocr_name, item["name"]) < .4:
                consistent = False
        elif number_ok is False and item_numbers:
            consistent = False
            combined -= 0.12
            if collector_conflict:
                combined -= 0.08
        elif name_ok or number_ok is True:
            consistent = True
            if name_ok:
                combined += 0.06 * name_weight
            if number_ok is True:
                combined += 0.08
        elif ocr_name and not name_ok:
            consistent = False if name_weight >= RELIABLE_COLLECTOR_CONF and similar(ocr_name, item["name"]) < 0.4 else None
            if consistent is False:
                combined -= 0.04 * name_weight
        stored = dict(item)
        language_conflict = bool(detected_languages and language and language not in detected_languages)
        strong_name_conflict = bool(comparable_name and require_confident_ocr and name_weight >= .85
            and len(normalize_text(ocr_name)) >= (2 if any(ord(c)>0x2E80 for c in normalize_text(ocr_name)) else 4)
            and not name_ok and similar(ocr_name,item['name']) < .4)
        if require_confident_ocr and (language_conflict or strong_name_conflict):
            consistent = False
        structured_conflict = any(h.region == 'collector' and h.confidence is not None
            and h.confidence >= .85 and '/' in h.text
            and _match_any([h], numbers) is False for h in known_numbers)
        if guard:
            # What a bare number cannot fake: the name, or a total or set code that agrees.
            stored["name_agrees"] = bool(name_ok)
            stored["structured_collector_match"] = any(
                h.confidence >= .85 and ('/' in h.text or any(c.isalpha() for c in h.text))
                and _match_any([h], numbers) is True for h in known_numbers)
        ranked.append(
            {
                **stored,
                "combined_score": combined,
                "ocr_consistent": consistent,
                "collector_conflict": collector_conflict,
                "structured_collector_conflict": structured_conflict,
                "language_conflict": language_conflict,
                "strong_name_conflict": strong_name_conflict,
                "localized_name_unknown": not comparable_name,
            }
        )
    ranked.sort(key=lambda row: row["combined_score"], reverse=True)
    ranked = _prefer_language_print(ranked, detected_languages,
                                    qualified_evidence=require_confident_ocr)
    return _keep_visual_leader(ranked, languages=detected_languages, guard=guard)


def _prefer_language_print(
    ranked: list[dict[str, Any]],
    languages: tuple[str, ...],
    max_drop: float = 0.10,
    *, qualified_evidence: bool = False,
) -> list[dict[str, Any]]:
    if not languages or len(ranked) < 2:
        return ranked
    matching = [row for row in ranked if row.get("language") in languages
                and not row.get('structured_collector_conflict')
                and not row.get('strong_name_conflict')]
    if not matching:
        return ranked
    if ranked[0].get("language") in languages:
        return ranked
    best = max(matching, key=lambda row: float(row["visual_score"]))
    if best.get('collector_conflict') and not qualified_evidence:
        return ranked
    # Unstructured numbers from a misaligned bottom ROI (attack damage, HP)
    # must not force a known-language conflict into first place. They still
    # lower the score and prevent automatic confirmation in decide_status.
    visual_best = max(ranked, key=lambda row: float(row["visual_score"]))
    drop = float(visual_best["visual_score"]) - float(best["visual_score"])
    if drop > max_drop:
        return ranked
    rest = [row for row in ranked if row["card_id"] != best["card_id"]]
    return [best, *rest]


def _keep_visual_leader(
    ranked: list[dict[str, Any]],
    *,
    min_visual: float = 0.78,
    min_gap: float = 0.04,
    languages: tuple[str, ...] = (),
    guard: bool = False,
) -> list[dict[str, Any]]:
    if len(ranked) < 2:
        return ranked
    visual = sorted(ranked, key=lambda row: float(row["visual_score"]), reverse=True)
    lead = visual[0]
    if languages and lead.get('language') not in languages:
        return ranked
    second = visual[1]
    if guard and languages:
        # The leader's own print in another language is not a rival: measure to the next card
        # in a language the scan reads as.
        second = next((row for row in visual[1:] if row.get('language') in languages), second)
    gap = float(lead["visual_score"]) - float(second["visual_score"])
    # Same name is not proof of a reprint: e.g. a rainbow trainer can share art
    # with its non-rainbow printing while having a different collector number.
    # Do not reinstate an explicitly conflicting visual leader over OCR ranking.
    if lead.get('structured_collector_conflict') and any(
        not r.get('structured_collector_conflict') for r in ranked
    ):
        return ranked
    if guard and _lifted_by_bare_number(ranked[0], lead, min_visual=min_visual):
        rest = [row for row in ranked if row["card_id"] != lead["card_id"]]
        return [lead, *rest]
    # A wide gap is the picture itself. A small one can still be a false
    # collector hit, such as "LV. 18" agreeing with catalogue number 018.
    if lead.get("collector_conflict") and not _same_name_reprint(lead, visual[1]) and gap < 0.10:
        return ranked
    if float(lead["visual_score"]) < min_visual or gap < min_gap:
        return ranked
    rest = [row for row in ranked if row["card_id"] != lead["card_id"]]
    return [lead, *rest]


def _lifted_by_bare_number(top: dict[str, Any], lead: dict[str, Any], *, min_visual: float) -> bool:
    """Whether [top] is first over the visual [lead] only through a bare number.

    Attack damage or HP read from a footer strip that missed the footer agrees with
    whatever card has that number. That is not enough for a card whose picture is
    BARE_NUMBER_MAX_DROP or more below a leader that clears the visual floor. The
    leader keeps its conflict flags, so it still needs confirmation.
    """
    return bool(
        top["card_id"] != lead["card_id"]
        and float(lead["visual_score"]) >= min_visual
        and float(lead["visual_score"]) - float(top["visual_score"]) >= BARE_NUMBER_MAX_DROP
        and not top.get("name_agrees")
        and not top.get("structured_collector_match")
    )


def _same_name_reprint(lead: dict[str, Any], other: dict[str, Any]) -> bool:
    """A reprint often prints the original collector number.

    That number agrees with the older print and conflicts with the reprint's
    catalogue number, so it cannot separate the two. The closer image can.
    """
    name = lead.get("name")
    return bool(
        name
        and name == other.get("name")
        and (lead.get("language") or "") == (other.get("language") or "")
    )


def _visual_second(suggestions: list[dict[str, Any]], top_id: str) -> float:
    second = 0.0
    for row in sorted(suggestions, key=lambda item: float(item["visual_score"]), reverse=True):
        if row["card_id"] != top_id and not row.get('language_conflict'):
            return float(row["visual_score"])
    return second


def _finish_twins(
    suggestions: list[dict[str, Any]], top: dict[str, Any], min_gap: float
) -> list[dict[str, Any]]:
    twins = []
    for row in suggestions:
        if row["card_id"] == top["card_id"]:
            continue
        if row.get("name") != top.get("name"):
            continue
        if row.get("collector_number") != top.get("collector_number"):
            continue
        if row.get("language") != top.get("language"):
            continue
        if abs(float(row["visual_score"]) - float(top["visual_score"])) >= min_gap:
            continue
        twins.append(row)
    return twins


def decide_status_with_reason(
    suggestions: list[dict[str, Any]],
    *,
    enable_matched: bool,
    min_visual: float,
    min_gap: float,
    retake: bool,
    min_visual_ocr: float | None = None,
) -> tuple[str, str]:
    """The status plus a short code saying which branch produced it."""
    if retake:
        return "retake", "retake_input"
    if not suggestions:
        return "no_match", "no_candidates"
    ocr_floor = min_visual if min_visual_ocr is None else min_visual_ocr
    top = suggestions[0]
    # Unknown translation only downgrades an otherwise eligible match. It
    # must never turn a below-floor nearest neighbour into a useful result.
    enable_matched = enable_matched and not top.get('localized_name_unknown', False)
    compatible = [row for row in suggestions if not row.get('language_conflict')]
    visual_lead = max(compatible or suggestions, key=lambda row: float(row["visual_score"]))
    if (visual_lead.get("collector_conflict") or top.get("collector_conflict")
        or top.get('structured_collector_conflict') or top.get('language_conflict') or top.get('strong_name_conflict')):
        return "uncertain", "conflict"
    second = _visual_second(suggestions, top["card_id"])
    gap = float(top["visual_score"]) - second
    visual_ok = float(top["visual_score"]) >= min_visual and (second <= 0.0 or gap >= min_gap)
    if _finish_twins(suggestions, top, min_gap):
        return "uncertain", "finish_twins"
    if visual_ok:
        if not enable_matched:
            return "uncertain", "matched_disabled"
        return "matched", "visual_ok"
    if float(top["visual_score"]) >= min_visual and top.get("ocr_consistent") is True:
        twins = [
            row
            for row in suggestions
            if abs(float(row["visual_score"]) - float(top["visual_score"])) < min_gap
        ]
        others = [row for row in twins if row["card_id"] != top["card_id"]]
        if others and all(row.get("ocr_consistent") is False for row in others):
            if not enable_matched:
                return "uncertain", "matched_disabled"
            return "matched", "ocr_twin_resolved"
        if others:
            return "uncertain", "visual_twins"
    if (
        top.get("ocr_consistent") is True
        and visual_lead.get("card_id") == top.get("card_id")
        and float(top["visual_score"]) >= ocr_floor
        and (second <= 0.0 or gap >= min_gap)
    ):
        if not enable_matched:
            return "uncertain", "matched_disabled"
        return "matched", "ocr_floor"
    return "no_match", "below_visual_floor"


def decide_status(*args, **kwargs) -> str:
    return decide_status_with_reason(*args, **kwargs)[0]
