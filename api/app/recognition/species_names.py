"""Japanese species names for Japanese rows the name read cannot be compared with (RANK_SPECIES_NAMES).

Most recovered older-era Japanese rows carry only an English provider title ("Ho-Oh ex"), and
part of the older-era Japanese names are machine transliterations (マチャンプ for Machamp, which is
カイリキー). A confident Japanese name read is unknown evidence for both today, so a wrong row
pays nothing for not being ルギア (neo1-072-1 on the all-eras catalogue).

`assets/ja_species_names.json` maps English species to their official Japanese names. It is
generated from the served catalogue's own Sun & Moon-onward Japanese rows by
`scripts/ja_set_recovery/build_species_names.py`; nothing in it is written by hand.

`species_verdict` applies only to a Japanese row whose name cannot be compared today: an
English-only name, or a Japanese name containing no official species. It answers True or False
only when both the read and the row resolve to known species; otherwise None, which keeps
today's behaviour. A read that names no species (an evolution note, a trainer, a misread)
therefore changes nothing.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

TABLE = Path(__file__).with_name("assets") / "ja_species_names.json"
MIN_JA_LENGTH = 2


def _ja_key(text: str | None) -> str:
    """NFKC, no spaces or separators: the same text normalisation on both sides."""
    if not text:
        return ""
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())


@lru_cache(maxsize=1)
def _table() -> tuple[dict[str, str], re.Pattern | None, tuple[str, ...]]:
    try:
        species: dict[str, str] = json.loads(TABLE.read_text(encoding="utf-8"))["species"]
    except (OSError, ValueError, KeyError):
        return {}, None, ()
    english = sorted(species, key=len, reverse=True)
    pattern = re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(e) for e in english) + r")(?![a-z0-9])")
    japanese = tuple(sorted({k for k in (_ja_key(v) for v in species.values()) if len(k) >= MIN_JA_LENGTH},
                            key=len, reverse=True))
    return species, pattern, japanese


def _maximal(found: set[str]) -> set[str]:
    """Drop a species contained in another found one (ミュウ inside ミュウツー)."""
    return {f for f in found if not any(f != g and f in g for g in found)}


def read_species(ocr_name: str | None) -> set[str]:
    """Official Japanese species contained in a name read, as normalised keys."""
    _, _, japanese = _table()
    text = _ja_key(ocr_name)
    return _maximal({j for j in japanese if j in text}) if text else set()


def row_species(item: dict[str, Any]) -> set[str]:
    """Japanese species keys for a Japanese row whose name cannot be compared today, else empty."""
    if item.get("language") != "ja":
        return set()
    species, pattern, japanese = _table()
    if pattern is None:
        return set()
    name = str(item.get("name") or "")
    if any(ord(c) > 0x2E80 for c in name):
        key = _ja_key(name)
        if any(j in key for j in japanese):
            return set()  # an official Japanese name: compared as today
        name = str(item.get("view_title") or "")  # a transliterated name: use the English title
        if any(ord(c) > 0x2E80 for c in name):
            return set()
    english = unicodedata.normalize("NFKC", name).casefold()
    found = {_ja_key(species[m]) for m in pattern.findall(english)}
    return _maximal({f for f in found if len(f) >= MIN_JA_LENGTH})


def species_verdict(ocr_name: str | None, item: dict[str, Any]) -> bool | None:
    """True / False when the read and the row both resolve to species; None keeps today's rule."""
    row = row_species(item)
    if not row:
        return None
    read = read_species(ocr_name)
    if not read:
        return None
    return bool(row & read)
