from __future__ import annotations

import sqlite3

from PIL import Image

from app.cardmarket import is_official_catalogue_id
from app.config import Settings
from app.recognition.embed import top_k
from app.recognition.runtime import Runtime


def official_visual_hit(
    conn: sqlite3.Connection,
    runtime: Runtime,
    settings: Settings,
    image: Image.Image,
) -> sqlite3.Row | None:
    """Return the unique official catalogue print that matches a listing photo."""
    if not runtime.ready:
        return None
    snapshot, embedder, _ocr = runtime.require()
    query = embedder.embed(image, settings.preprocess_config)
    indices, scores = top_k(snapshot.embeddings, query, k=8)
    if indices.size == 0:
        return None
    card_ids = [str(snapshot.card_ids[index]) for index in indices]
    placeholders = ",".join("?" for _ in card_ids)
    rows = {
        str(row["id"]): row
        for row in conn.execute(
            f"SELECT * FROM cards WHERE id IN ({placeholders})",
            card_ids,
        ).fetchall()
    }
    ranked: list[tuple[float, sqlite3.Row]] = []
    for index, score in zip(indices, scores, strict=True):
        card_id = str(snapshot.card_ids[index])
        if not is_official_catalogue_id(card_id):
            continue
        row = rows.get(card_id)
        if row is None or not int(row["has_image"] or 0):
            continue
        ranked.append((float(score), row))
    if not ranked:
        return None
    ranked.sort(key=lambda item: -item[0])
    best_score, best = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    if best_score < settings.threshold_min_visual:
        return None
    if second > 0.0 and (best_score - second) < settings.threshold_min_gap:
        return None
    return best
