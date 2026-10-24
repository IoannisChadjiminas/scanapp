"""A port of PokeSingle's lib/data/card_text.dart, for offline replay only.

Rebuilds the ``client_text`` the phone would send from ML Kit lines. Only what
the replay needs is ported: card-space mapping, name and number picking, number
validity against the bundled set totals, and the JSON body. The set-total tables
are read from the app's own ``set_totals.dart`` so the two cannot drift.

Nothing here runs on the server.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
import unicodedata

import numpy as np

TITLE_BAND = .20
FOOTER_BAND = .80
CLIENT_TEXT_MAX_BYTES = 768

HP = re.compile(r'(?:\bHP\s*\d{2,3}|\d{2,3}\s*HP\b)', re.I)
BADGE = re.compile(
    r'^(?:basic|stage\s*\d|stage\d|trainer|supporter|item|stadium|tool|energy|'
    r'evolves\s+from.*|put\s+.*|たね|進化|1\s*進化|2\s*進化|ポケモンのどうぐ|サポート|グッズ|スタジアム)$', re.I)
STRICT_FRACTION = re.compile(
    r'(?<![A-Z0-9])((?:(?:TG|GG|SV|RC|H))?\d{1,4}[A-Z]?\s*/\s*(?:(?:TG|GG|SV|RC|H))?\d{1,4})(?!\d)', re.I)
FRACTION = re.compile(
    r'(?<![A-Z0-9])((?:TG|GG|SV|RC|H)[0-9OILSBZ|]{1,3}\s*/\s*(?:TG|GG|SV|RC|H)?[0-9OILSBZ|]{1,3}'
    r'|[0-9OILSBZ|]{1,4}[A-Z]?\s*/\s*(?:(?:SV|S)\s*-\s*P|[0-9OILSBZ|]{1,4}))(?![A-Z0-9])', re.I)
PROMO = re.compile(r'(?<!/)\b((?:SWSH|SVP|SM|XY|BW|DP|HGSS|SV)\s?-?[0-9OIL|SBZ]{2,4})\b(?!\s*/)', re.I)
PROTECT_PREFIX = re.compile(r'SV-P|S-P|SVP|SWSH|TG|GG|SV|RC|SM|XY|BW|DP|HGSS|EN')
DIGIT_SWAPS = {'O': '0', 'I': '1', 'L': '1', '|': '1', 'S': '5', 'B': '8', 'Z': '2'}
LEADING_BADGE = re.compile(r'^(?:BASI[CGS]|STAGE\s?[0-9IZT|]?)\s+(?=\w)', re.I)
GRADER = re.compile(r'\b(?:PSA|BGS|BECKETT|CGC|TAG|ACE|AGS|GRADE|GEM\s*MT|MINT|NM[-/ ]?MT)\b', re.I)
TRIMMED = ' .,:;-*'
GALLERY_TWICE = re.compile(r'^([A-Z]{1,4})(\d{1,4})/\1(\d{1,4})$')
NUMBER_SHAPE = re.compile(
    r'^(?:[A-Z]{1,5}[- ]?)?\d{1,4}[A-Z]?(?:\s*/\s*(?:(?:[A-Z]{1,4})?\d{1,4}|S-P|SV-P))?$', re.I)
PROMO_DENOMINATOR = re.compile(r'^\d{1,4}[A-Z]?/(?:S-P|SV-P)$')
COLLECTOR_PARTS = re.compile(r'^([A-Z]{1,4})?(\d{1,4})(?:[A-Z])?(?:/(\d{1,4}))?$')
COLLECTOR_FRACTION = re.compile(r'^([A-Z]{1,4})?(\d{1,4})/(\d{1,4})$')
VINTAGE_TOTALS = {102, 64, 62, 82, 130, 110, 105, 111, 75, 95, 132, 165, 144, 147, 182}


@dataclass(frozen=True)
class Line:
    text: str
    x: float
    y: float
    w: float
    h: float
    conf: float | None = None

    @property
    def centre_y(self) -> float:
        return self.y + self.h / 2


def load_set_totals(path: str) -> tuple[dict[str, dict[str, int]], dict[str, set[str]], set[str]]:
    """collectorTotals, collectorPromoPrefixes and collectorPromoDenominators from set_totals.dart."""
    text = open(path, encoding='utf-8').read()
    totals: dict[str, dict[str, int]] = {}
    body = text.split('const collectorPromoPrefixes')[0]
    language = None
    for raw in body.splitlines():
        header = re.match(r"^  '([a-z-]+)': \{", raw)
        if header:
            language = header.group(1)
            totals[language] = {}
            continue
        entry = re.match(r"^    '([^']*)': (\d+),", raw)
        if entry and language:
            totals[language][entry.group(1)] = int(entry.group(2))
    prefixes = {}
    tail = text.split('const collectorPromoPrefixes')[1].split('const collectorPromoDenominators')[0]
    for match in re.finditer(r"'([a-z-]+)': \{([^}]*)\}", tail):
        prefixes[match.group(1)] = set(re.findall(r"'([A-Z]+)'", match.group(2)))
    denominators = set(re.findall(r"'([A-Z-]+)'", text.split('const collectorPromoDenominators')[1]))
    return totals, prefixes, denominators


class CardText:
    def __init__(self, set_totals_dart: str):
        self.totals, self.promo_prefixes, self.promo_denominators = load_set_totals(set_totals_dart)

    # --- card space -------------------------------------------------------
    @staticmethod
    def _square_to_quad(q):
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = q
        sx, sy = x0 - x1 + x2 - x3, y0 - y1 + y2 - y3
        dx1, dx2, dy1, dy2 = x1 - x2, x3 - x2, y1 - y2, y3 - y2
        den = dx1 * dy2 - dx2 * dy1
        if abs(den) < 1e-12:
            return None
        g = (sx * dy2 - dx2 * sy) / den
        h = (dx1 * sy - sx * dy1) / den
        return np.array([[x1 - x0 + g * x1, x3 - x0 + h * x3, x0],
                         [y1 - y0 + g * y1, y3 - y0 + h * y3, y0],
                         [g, h, 1.]])

    def lines_on_card(self, lines: list[Line], width: int, height: int, quad=None):
        """Lines in card space, or None. ``quad``: 4 (x, y) fractions, clockwise from top-left."""
        if quad is not None and len(quad) == 4 and width > 0 and height > 0:
            c = [(x * width, y * height) for x, y in quad]
            across = (np.hypot(c[1][0] - c[0][0], c[1][1] - c[0][1]) + np.hypot(c[2][0] - c[3][0], c[2][1] - c[3][1])) / 2
            down = (np.hypot(c[3][0] - c[0][0], c[3][1] - c[0][1]) + np.hypot(c[2][0] - c[1][0], c[2][1] - c[1][1])) / 2
            square = self._square_to_quad(c) if 0 < across < down else None
            if square is not None and abs(np.linalg.det(square)) >= 1e-12:
                inverse = np.linalg.inv(square)

                def apply(x, y):
                    px, py = x * width, y * height
                    d = inverse[2, 0] * px + inverse[2, 1] * py + inverse[2, 2]
                    if abs(d) < 1e-12:
                        return None
                    return ((inverse[0, 0] * px + inverse[0, 1] * py + inverse[0, 2]) / d,
                            (inverse[1, 0] * px + inverse[1, 1] * py + inverse[1, 2]) / d)

                mapped = []
                for line in lines:
                    mid = line.x + line.w / 2
                    top, bottom = apply(mid, line.y), apply(mid, line.y + line.h)
                    left, right = apply(line.x, line.centre_y), apply(line.x + line.w, line.centre_y)
                    if None in (top, bottom, left, right):
                        continue
                    cx, cy = (left[0] + right[0]) / 2, (top[1] + bottom[1]) / 2
                    if cx < 0 or cx > 1 or cy < 0 or cy > 1:
                        continue
                    h, w = abs(bottom[1] - top[1]), abs(right[0] - left[0])
                    mapped.append(Line(line.text, min(left[0], right[0]), cy - h / 2, w, h, line.conf))
                return mapped
        if width > 0 and height > 0 and .62 <= width / height <= .80:
            return lines
        return None

    # --- number validity ----------------------------------------------------
    @staticmethod
    def gallery_once(value: str) -> str:
        text = value.upper()
        held = []

        def hold(match):
            held.append(match.group(0))
            return f'\0{len(held) - 1}\0'
        text = re.sub(r'SV-P|S-P', hold, text)
        text = re.sub(r'[\s-]', '', text)
        text = re.sub(r'\0(\d+)\0', lambda m: held[int(m.group(1))], text)
        return GALLERY_TWICE.sub(lambda m: f'{m[1]}{m[2]}/{m[3]}', text)

    @staticmethod
    def clean_number_span(raw: str) -> str:
        text = re.sub(r'\s+', '', re.sub(r'\s*/\s*', '/', raw.upper()))
        held = []

        def hold(match):
            held.append(match.group(0))
            return f'\0{len(held) - 1}\0'
        text = PROTECT_PREFIX.sub(hold, text).replace('-', '')
        text = ''.join(DIGIT_SWAPS.get(char, char) for char in text)
        return re.sub(r'\0(\d+)\0', lambda m: held[int(m.group(1))], text)

    def catalogue_number(self, number: str, language: str | None = None) -> bool:
        text = self.gallery_once(number)
        languages = list(self.totals) if language is None else [language]
        promo = re.match(r'^(SWSH|SVP|SM|XY|BW|DP|HGSS|SV)(\d{2,4})$', text)
        if promo:
            return any(promo[1] in self.promo_prefixes.get(lang, ()) for lang in languages)
        code = re.match(r'^\d{3}/(S-P|SV-P)$', text)
        if code:
            return (language is None or language == 'ja') and code[1] in self.promo_denominators
        fraction = re.match(r'^([A-Z]*)(\d{1,4})[A-Z]?/(\d{1,4})$', text)
        if not fraction:
            return False
        key = f'{fraction[1]}/{int(fraction[3])}'
        if key == 'H/32':
            n = int(fraction[2])
            return (language is None or language == 'en') and 0 < n <= 32
        numerator = int(fraction[2])
        return any((m := self.totals.get(lang, {}).get(key)) is not None and 0 < numerator <= m for lang in languages)

    # --- picking ------------------------------------------------------------
    @staticmethod
    def _strip(text: str) -> str:
        return text.strip(TRIMMED)

    def pick_name(self, lines: list[Line]):
        best = None
        for line in lines:
            if line.centre_y > TITLE_BAND:
                continue
            text = self._strip(LEADING_BADGE.sub('', HP.sub('', line.text), count=1))
            if not text or BADGE.search(text) or GRADER.search(text):
                continue
            letters = sum(c.isalpha() for c in text)
            digits = sum(unicodedata.category(c) == 'Nd' for c in text)
            cjk = any(ord(c) > 0x2E80 for c in text)
            if letters < (2 if cjk else 3) or digits >= letters:
                continue
            conf = line.conf or 0
            if best is None or line.h > best[0] or (line.h == best[0] and conf > best[1]):
                best = (line.h, conf, text[:64], line.conf)
        return None if best is None else (best[2], best[3])

    @staticmethod
    def has_vintage_layout(lines: list[Line]) -> bool:
        for line in lines:
            if line.centre_y > .75 and re.search(r'illus\.|wizards|199[5689]|200[0123]', line.text, re.I):
                return True
            if line.centre_y < .25 and re.search(r'\b\d{2,3}\s*HP\b', line.text, re.I):
                return True
            if re.search(r'\bretreat cost\b', line.text, re.I):
                return True
        return False

    def _vintage_compact(self, text: str):
        stripped = re.sub(r'\s*[●◆★*o]\s*$', '', text.strip(), flags=re.I)
        token = re.match(r'^([0-9OILSB|]{3,7})[●◆★*o]?$', stripped, re.I)
        if not token:
            return None
        digits = self.clean_number_span(token[1])
        found = set()
        for total in VINTAGE_TOTALS:
            suffix = str(total)
            if not digits.endswith(suffix) or len(digits) <= len(suffix):
                continue
            numerator = digits[:-len(suffix)]
            if numerator.isdigit() and 0 < int(numerator) <= total:
                found.add(f'{numerator}/{total}')
        return found.pop() if len(found) == 1 else None

    def pick_number(self, lines: list[Line], vintage: bool = False):
        vintage_crop = vintage
        vintage = vintage or self.has_vintage_layout(lines)
        best = None  # (conf, negx, text, raw)
        for line in lines:
            if line.centre_y < FOOTER_BAND:
                continue
            spans = [m[1] for pattern in (STRICT_FRACTION, FRACTION, PROMO) for m in pattern.finditer(line.text)]
            spans += [m[1] for m in re.finditer(r'^\s*#(\d{1,2})\s*[●◆★*]?\s*$', line.text, re.I)
                      if 0 < int(m[1]) <= 53]
            if vintage:
                compact = self._vintage_compact(line.text)
                if compact:
                    spans.append(compact)
            for span in spans:
                if not re.search(r'\d', span):
                    continue
                found = self.clean_number_span(span)
                if vintage_crop:
                    fraction = re.match(r'^([A-Z]*)(\d+)[A-Z]?/(\d+)$', self.gallery_once(found))
                    if fraction and int(fraction[3]) not in VINTAGE_TOTALS and not (fraction[1] == 'H' and fraction[3] == '32'):
                        continue
                if not self.catalogue_number(found) and not re.fullmatch(r'\d{1,2}', found):
                    continue
                conf = line.conf or 0
                negx = -line.x
                bare_promo = '/' not in found and found.isdigit()
                previous_bare = best is not None and best[2].isdigit()
                better = (best is None or (not bare_promo and previous_bare) or
                          (bare_promo == previous_bare and (
                              conf > best[0] or (conf == best[0] and (
                                  negx > best[1] or (negx == best[1] and found > best[2]))))))
                if better:
                    best = (conf, negx, found, line.conf)
        return None if best is None else (best[2], best[3])

    # --- the JSON body ------------------------------------------------------
    @staticmethod
    def _valid_name(name):
        if name is None:
            return None
        text = name.strip()
        if not 1 <= len(text) <= 64 or not any(c.isalpha() for c in text):
            return None
        if any(unicodedata.category(c).startswith('C') for c in text):
            return None
        return text

    def _valid_number(self, number):
        if number is None:
            return None
        text = number.strip()
        if len(text) > 16 or not NUMBER_SHAPE.match(text):
            return None
        if not self.catalogue_number(text) and not (re.fullmatch(r'\d{1,2}', text) and 0 < int(text) <= 53):
            return None
        compact = self.gallery_once(text)
        if PROMO_DENOMINATOR.match(compact):
            return text
        if not COLLECTOR_PARTS.match(compact) and not COLLECTOR_FRACTION.match(compact):
            return None
        return text

    @staticmethod
    def _round(conf):
        if conf is None or conf != conf:
            return None
        return round(min(max(conf, 0.0), 1.0) * 1000) / 1000

    def client_text(self, lines: list[Line], engine: str = 'mlkit-latin', ms: int = 200) -> str | None:
        name, number = self.pick_name(lines), self.pick_number(lines)
        name_text = self._valid_name(name[0] if name else None)
        number_text = self._valid_number(number[0] if number else None)
        if name_text is None and number_text is None:
            return None

        def encode(with_name):
            body = {'v': 1, 'engine': engine, 'name': name_text if with_name else None,
                    'name_conf': self._round(name[1]) if with_name and name_text and name else None,
                    'number': number_text,
                    'number_conf': self._round(number[1]) if number_text and number else None, 'ms': ms}
            return json.dumps(body, ensure_ascii=False, separators=(',', ':'))
        body = encode(True)
        if len(body.encode()) > CLIENT_TEXT_MAX_BYTES:
            if number_text is None:
                return None
            body = encode(False)
        return body
