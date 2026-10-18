"""Physical catalogue cards are the ones a person can hold.

Pokémon TCG Pocket sets are digital. Their English set ids are P-A and the
A/B series (A1, A2b, B2a). Search and scan both leave those rows out.
"""

from __future__ import annotations


def is_tcg_pocket_card(language: str | None, set_id: str | None) -> bool:
    if str(language or "") != "en":
        return False
    sid = str(set_id or "")
    return sid == "P-A" or (len(sid) >= 2 and sid[0] in "AB" and sid[1].isdigit())


def is_tcg_pocket_card_id(card_id: str | None) -> bool:
    rest = str(card_id or "").removeprefix("en:")
    if rest == str(card_id or ""):
        return False
    return is_tcg_pocket_card("en", rest.split("-", 1)[0] if not rest.startswith("P-A") else "P-A")
