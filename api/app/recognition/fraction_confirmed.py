"""Keep a card confirmed by a clean printed fraction ahead of its same-name twin.

Local artwork verification can confirm a same-artwork reprint (Base Set 2 Professor Oak 116/130)
while the photo's footer reads the original's fraction (88/102) cleanly. Keypoints certify shared
artwork, not which print it is, so the fraction decides between the two. Flag RANK_FRACTION_CONFIRMED.
"""
from __future__ import annotations

from typing import Any

from app.recognition.rank import _match_any, accepted_collector_numbers, normalize_text

MIN_FRACTION_CONFIDENCE = 0.80


def clean_fractions(numbers) -> list:
    """Collector-region reads with a slash (N/T) at confidence 0.80 or more."""
    return [h for h in numbers or [] if getattr(h, 'region', None) == 'collector'
            and getattr(h, 'confidence', None) is not None and h.confidence >= MIN_FRACTION_CONFIDENCE
            and '/' in str(getattr(h, 'text', ''))]


def _same_name(a: dict[str, Any], b: dict[str, Any]) -> bool:
    names = lambda r: {normalize_text(str(r.get(k) or '')) for k in ('name', 'view_title')} - {''}
    return bool(names(a) & names(b))


def fraction_confirmed_twin(combined: list[dict[str, Any]], chosen_id: str, numbers) -> str | None:
    """The one same-name card the fraction confirms when it contradicts the chosen card, else None."""
    hits = clean_fractions(numbers)
    if not hits:
        return None
    chosen = next((r for r in combined if r['card_id'] == chosen_id), None)
    if chosen is None or _match_any(hits, accepted_collector_numbers(chosen)) is not False:
        return None
    confirmed = [r for r in combined if r['card_id'] != chosen_id and _same_name(r, chosen)
                 and _match_any(hits, accepted_collector_numbers(r)) is True]
    # The same English card can be listed as "base1-88" and "en:base1-88"; count it once.
    distinct: dict[str, str] = {}
    for r in confirmed:
        key = _card_key(r['card_id'])
        if key not in distinct or ':' in r['card_id']:
            distinct[key] = r['card_id']
    return next(iter(distinct.values())) if len(distinct) == 1 else None


def _card_key(card_id: str) -> str:
    return card_id if ':' in card_id else 'en:' + card_id
