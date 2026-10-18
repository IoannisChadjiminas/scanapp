"""Catalogue titles.

`name` is the original title used for scan matching. `view_title` is the
English title shown to the user. Matching must not read `view_title`.
"""

from __future__ import annotations


def stored_view_title(row) -> str | None:
    if "view_title" not in row.keys():
        return None
    value = row["view_title"]
    if value is None:
        return None
    text = str(value).strip()
    return text or None
