"""A slab label's own set line and number: candidates for a card the picture misses.

CGC prints "Burning Shadows - 18a/147", PSA "2017 POKEMON SM BURNING SHADOWS" over "#18A",
BGS "2017 Pokemon Sun & Moon Burning Shadows #18a". The set words are matched against the
catalogue's set names and the number against its collector numbers, letter suffixes and
prefixes included. Like the number+name path this only proposes 1-3 cards; the pipeline
verifies their artwork and otherwise asks for confirmation.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import re
import sqlite3
import time
import unicodedata

from PIL import Image

from app.recognition.ocr import OcrHit, grading_label_line
from app.recognition.rank import parse_collector
from app.recognition.text_identity import MAX_CANDIDATES, name_agrees, name_tokens

VERSION = 'slab-label-set-number-v1'
MIN_CONFIDENCE = .85
NUMBER = r'[A-Z]{0,5}\d{1,4}[A-Z]?'
# "<set> - 18a/147" (CGC; OCR may drop the space before the dash).
CGC_SET_LINE = re.compile(rf'^(?P<set>.*[A-Z].*?)\s*[-–—]\s*(?P<number>{NUMBER})(?:\s*/\s*{NUMBER})?$')
# "#18A" alone (PSA) or at the end of a set line (BGS, Beckett, ACE).
HASH_NUMBER = re.compile(rf'#\s*(?P<number>{NUMBER})\b')
DATED = re.compile(r'^(?:19|20)\d{2}(?:[- /]\d{2})?\s+')
# Header words that are not part of a set's name.
NOISE = {'pokemon', 'pokémon', 'jp', 'en', 'eng', 'japanese', 'english', 'p', 'm', 'game', 'tcg',
         'holo', 'reverse', 'rev', 'foil', '1st', 'edition', 'ed', 'the', 'and', 'of'}


def _text(value: str) -> str:
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', value)).strip().upper()


def _words(value: str) -> list[str]:
    folded = unicodedata.normalize('NFKD', value.casefold())
    return [w for w in re.findall(r'[a-z0-9]+', folded) if w not in NOISE]


def number_key(value: str | None) -> str | None:
    """'018a' -> '18A', 'SV059' -> 'SV59', 'TG01' -> 'TG1'; a fraction keeps its numerator."""
    if not value:
        return None
    head = str(value).upper().replace(' ', '').split('/')[0]
    match = re.fullmatch(r'([A-Z]{0,5})0*(\d{1,4})([A-Z]?)', head)
    if not match:
        return None
    return f'{match[1]}{int(match[2])}{match[3]}'


def label_lines(hits: list[OcrHit]) -> list[str]:
    """Confident title-strip lines, only when a grading label is visibly among them."""
    lines = [h.text for h in hits if h.region in ('name', 'holder_name')
             and h.confidence is not None and h.confidence >= MIN_CONFIDENCE]
    holder = any(h.region == 'holder_name' for h in hits)
    return lines if holder or any(grading_label_line(line) for line in lines) else []


def parse_label(lines: list[str]) -> tuple[list[str], str | None]:
    """Set-name texts and the label's collector number (None when absent or contradictory)."""
    sets, numbers = [], set()
    for raw in lines:
        line = _text(raw)
        cgc = CGC_SET_LINE.fullmatch(line)
        if cgc and not DATED.match(line):
            sets.append(cgc['set'])
            numbers.add(number_key(cgc['number']))
            continue
        hashed = HASH_NUMBER.search(line)
        if hashed:
            numbers.add(number_key(hashed['number']))
            before = line[:hashed.start()]
            if DATED.match(before):
                sets.append(DATED.sub('', before))
            continue
        if DATED.match(line) and re.search(r'POK[EÉ]MON', line):
            sets.append(DATED.sub('', line))
    numbers.discard(None)
    # CGC continues the set on its variant line ("Holo - Blastoise & Suicune ex Deck").
    sets.append(' '.join(_text(raw) for raw in lines))
    sets = [s for s in sets if _words(s)]
    return sets, (next(iter(numbers)) if len(numbers) == 1 else None)


LANGUAGE_WORDS = {'JAPANESE': 'ja', 'JPN': 'ja', 'KOREAN': 'ko', 'CHINESE': 'zh-tw',
                  'SIMPLIFIED CHINESE': 'zh-cn', 'ENGLISH': 'en'}


def label_language(lines: list[str]) -> str | None:
    """A label that names the card's language ("Pokémon (2023) Japanese") decides it."""
    found = {code for raw in lines for word, code in LANGUAGE_WORDS.items()
             if re.search(rf'\b{word}\b', _text(raw))}
    if 'zh-cn' in found:
        found.discard('zh-tw')
    return next(iter(found)) if len(found) == 1 else None


def set_score(label_set: str, set_name: str, set_id: str = '') -> float:
    """Share of the catalogue set name's words on the label, or the whole-string similarity.

    A label word equal to the set code (PSA's "SVP") is a full match.
    """
    want, have = _words(set_name), set(_words(label_set))
    code = re.sub(r'[^a-z0-9]', '', set_id.casefold())
    if len(code) >= 3 and code in have:
        return 1.
    if not want:
        return 0.
    overlap = sum(w in have or any(len(w) >= 5 and SequenceMatcher(None, w, h).ratio() >= .8 for h in have)
                  for w in want) / len(want)
    whole = SequenceMatcher(None, ' '.join(want), ' '.join(_words(label_set))).ratio()
    return max(overlap, whole)


def label_identity_candidates(index, catalog: sqlite3.Connection, *, hits: list[OcrHit],
                              languages: tuple[str, ...]) -> tuple[list[str], str]:
    lines = label_lines(hits)
    if not lines:
        return [], 'no_label'
    sets, number = parse_label(lines)
    if number is None:
        return [], 'no_label_number'
    parts = parse_collector(number)
    if parts is None:
        return [], 'no_label_number'
    printed = label_language(lines)
    languages = (printed,) if printed else languages
    pool = [row for row in index.by_number.get((parts.prefix, parts.number), ())
            if not languages or row.get('language') in languages]
    ids = [row['id'] for row in pool]
    if not ids:
        return [], 'number_not_in_catalogue'
    placeholders = ','.join('?' for _ in ids)
    rows = [dict(r) for r in catalog.execute(
        f'SELECT id, name, set_id, set_name, collector_number, printed_collector_number, view_title '
        f'FROM cards WHERE id IN ({placeholders})', ids)]
    # The letter suffix and prefix must agree exactly: 18a is not 18, TG01 is not 1.
    rows = [r for r in rows if number in {number_key(r['collector_number']),
                                          number_key(r['printed_collector_number'])}]
    if not rows:
        return [], 'number_not_in_catalogue'
    scored = [(max((set_score(s, str(r['set_name'] or ''), str(r['set_id'] or '')) for s in sets), default=0.), r) for r in rows]
    in_set = [r for score, r in scored if score >= .6]
    tokens = name_tokens([OcrHit(line, 1., 'name') for line in lines])
    named = [r for r in (in_set or rows) if name_agrees(tokens, r['name'], str(r.get('view_title') or ''))]
    if in_set:
        # The label's card name breaks ties inside the set; it never empties the match.
        chosen = named or in_set
    else:
        # No set read: the number plus the label's card name must agree.
        chosen = named
    if not chosen:
        return [], 'no_set_or_name_agreement'
    if len(chosen) > MAX_CANDIDATES:
        return [], 'too_many_candidates'
    return sorted(r['id'] for r in chosen), 'candidates'


def read_label_half(engine, image: Image.Image) -> tuple[list[OcrHit], dict]:
    """One OCR read of the upload's upper half, where a slab label sits; label-region hits."""
    patch = image.crop((0, 0, image.width, round(.55 * image.height)))
    scale = min(1., 1200 / max(patch.size))
    if scale < 1.:
        patch = patch.resize((round(patch.width * scale), round(patch.height * scale)),
                             Image.Resampling.LANCZOS)
    started = time.perf_counter()
    try:
        lines, scores = engine._run(patch)
    finally:
        record = dict(region='label', reason='slab_label_number', width=patch.width, height=patch.height,
                      ms=round((time.perf_counter() - started) * 1000, 2))
        patch.close()
    return [OcrHit(t, s, 'holder_name') for t, s in zip(lines, scores)], record
