"""Which phone-index rows the app should not offer, decided from the card ids alone.

The phone index (`api/scripts/on_phone_index/export_index.py`) carries every row of the
recognition snapshot, in snapshot order. Each row gets a `row_kind`:

- `digital`: a Pokémon TCG Pocket card (`app.physical_cards`); it cannot be held or scanned.
- `language`: a Chinese row (`zh-tw:`, `zh-cn:`); the app does not support the language.
- `duplicate`: a legacy id without a language prefix whose `en:` twin is also indexed
  (base1, swsh3, sv01 from the first pilot): same card, same image, same vector.
- `reference`: any other id without a language prefix, an extra reference photo (`extra-*`).
  It is kept: it is the only vector of its print or a second photo of one.
- empty: an ordinary card.

`subset_ids` is the documented subset rule: the snapshot ids minus the rows whose kind is in
`excluded`, in snapshot order. The exporter writes it into the version file and the manifest
route recomputes it from the loaded snapshot, so a subset index is only served for the
snapshot it was cut from. The rule uses nothing but the ids, so both sides agree by construction.
"""
from __future__ import annotations

import hashlib
from typing import Iterable, Sequence

KINDS = ('digital', 'language', 'duplicate', 'reference')
# Kinds a published index may leave out. `reference` rows are never left out.
EXCLUDABLE = ('digital', 'language', 'duplicate')
RULE = 'phone-subset-v1'


def _is_pocket(card_id: str) -> bool:
    # Same rule as app.physical_cards.is_tcg_pocket_card_id, kept here so the exporter can load
    # this file on its own.
    rest = card_id.removeprefix('en:')
    if rest == card_id:
        return False
    sid = 'P-A' if rest.startswith('P-A') else rest.split('-', 1)[0]
    return sid == 'P-A' or (len(sid) >= 2 and sid[0] in 'AB' and sid[1].isdigit())


def row_kind(card_id: str, indexed: set[str] | frozenset[str]) -> str:
    if card_id.startswith(('zh-tw:', 'zh-cn:')):
        return 'language'
    if _is_pocket(card_id):
        return 'digital'
    if ':' not in card_id:
        return 'duplicate' if 'en:' + card_id in indexed else 'reference'
    return ''


def row_kinds(ids: Sequence[str]) -> list[str]:
    indexed = frozenset(ids)
    return [row_kind(card_id, indexed) for card_id in ids]


def normalize_excluded(excluded: Iterable[str]) -> tuple[str, ...]:
    chosen = tuple(sorted(set(excluded)))
    if any(kind not in EXCLUDABLE for kind in chosen):
        raise ValueError(f'excluded kinds must be among {EXCLUDABLE}')
    return chosen


def subset_ids(ids: Sequence[str], excluded: Iterable[str]) -> list[str]:
    chosen = set(normalize_excluded(excluded))
    if not chosen:
        return list(ids)
    return [card_id for card_id, kind in zip(ids, row_kinds(ids)) if kind not in chosen]


def ids_digest(ids: Iterable[str]) -> str:
    """sha256 of the ids file the exporter writes (`<id>\\n` per row)."""
    h = hashlib.sha256()
    for card_id in ids:
        h.update(card_id.encode('utf-8') + b'\n')
    return h.hexdigest()
