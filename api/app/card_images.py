from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.card_image_mirror import CARDMARKET_IMAGE_HOST, image_host, mirror_object_base
from app.visual_aliases import visual_image_owner


# This retired provider URL returns 404. Keep using the catalogue's stored
# reference image instead, including in recognition's printing suggestions.
_UNAVAILABLE_REMOTE_IMAGES = frozenset({
    "https://static.tcgcollector.com/content/images/8e/40/88/"
    "8e4088feac274f152f050116b685af4e18bb9a4de47dd5291ca935f879c5d5bf.jpg",
})


def tcgdex_display_url(image_base: str | None, quality: str = "high") -> str | None:
    base = (image_base or "").strip().rstrip("/")
    if not base.startswith("https://"):
        return None
    return f"{base}/{quality}.webp"


def display_image_url(row: Any, catalog: Any = None) -> str | None:
    """The image URL a client should load for this card.

    TCGdex art: the CDN copy once mirrored, else TCGdex. Any other remote
    address is a hotlink to a third-party site that may vanish (many
    tcgcollector images now return 404), so the catalogue's own stored copy
    wins: its CDN copy once mirrored, else the API's image route. Cardmarket
    product photos keep their own URL.
    """
    owner = visual_image_owner(row, catalog)
    if owner is not row:
        return f"/api/v1/cards/{quote(str(row['id']), safe=':')}/image"
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    card_id = str(row["id"] if "id" in keys else "")
    remote = str(row["remote_image_url"] or "") if "remote_image_url" in keys else ""
    if remote in _UNAVAILABLE_REMOTE_IMAGES or not remote.startswith("https://"):
        remote = ""
    cdn = getattr(catalog, "card_image_cdn", None)
    if remote and mirror_object_base(remote) is not None:
        # Mirrored TCGdex art is served from the catalogue's own CDN host.
        mirrored = cdn.url_for(card_id, remote) if cdn is not None else None
        return mirrored or remote
    has_image = bool(row["has_image"]) if "has_image" in keys else False
    path = str(row["image_path"] or "") if "image_path" in keys else ""
    own_copy = bool(card_id and has_image and path)
    if remote and (not own_copy or image_host(remote) == CARDMARKET_IMAGE_HOST):
        return remote
    if own_copy:
        mirrored = cdn.url_for(card_id, remote, path) if cdn is not None else None
        return mirrored or f"/api/v1/cards/{card_id}/image"
    return None


def backfill_remote_image_urls(
    conn: Any,
    data_dir: Path,
    *,
    quality: str = "high",
) -> int:
    cache = Path(data_dir) / "cache" / "cards"
    if not cache.is_dir():
        return 0
    updated = 0
    rows = conn.execute(
        """
        SELECT id, provider_id, language, remote_image_url
        FROM cards
        WHERE remote_image_url IS NULL OR remote_image_url = ''
        """
    ).fetchall()
    for row in rows:
        language = str(row["language"] or "en")
        provider_id = str(row["provider_id"] or "")
        path = cache / language / f"{provider_id}.json"
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        url = tcgdex_display_url(
            payload.get("image") if isinstance(payload, dict) else None,
            quality,
        )
        if not url:
            continue
        conn.execute(
            "UPDATE cards SET remote_image_url = ? WHERE id = ?",
            (url, row["id"]),
        )
        updated += 1
    if updated:
        conn.commit()
    return updated
