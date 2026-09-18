from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def tcgdex_display_url(image_base: str | None, quality: str = "high") -> str | None:
    base = (image_base or "").strip().rstrip("/")
    if not base.startswith("https://"):
        return None
    return f"{base}/{quality}.webp"


def display_image_url(row: Any) -> str | None:
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    remote = str(row["remote_image_url"] or "") if "remote_image_url" in keys else ""
    if remote.startswith("https://"):
        return remote
    card_id = str(row["id"] if "id" in keys else "")
    has_image = bool(row["has_image"]) if "has_image" in keys else False
    path = str(row["image_path"] or "") if "image_path" in keys else ""
    if card_id and has_image and path:
        return f"/api/v1/cards/{card_id}/image"
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
