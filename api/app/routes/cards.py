from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.cardmarket import url_for_row
from app.recognition.language import expand_language
from app.schemas import CardSearchResponse, CardSummary

router = APIRouter()


def _image_url(card_id: str, has_image: bool) -> str | None:
    if not has_image:
        return None
    return f"/api/v1/cards/{card_id}/image"


def _summary(row) -> CardSummary:  # noqa: ANN001
    return CardSummary(
        id=row["id"],
        name=row["name"],
        set_id=row["set_id"],
        set_name=row["set_name"],
        collector_number=row["collector_number"],
        language=row["language"],
        has_image=bool(row["has_image"]),
        image_url=_image_url(row["id"], bool(row["has_image"])),
        variants=json.loads(row["variants_json"] or "{}"),
        cardmarket_url=url_for_row(row),
    )


@router.get("/cards", response_model=CardSearchResponse)
def search_cards(
    request: Request,
    q: str = Query(default="", min_length=0, max_length=80),
    language: str = Query(default="", max_length=16),
    limit: int = Query(default=20, ge=1, le=50),
) -> CardSearchResponse:
    catalog = request.app.state.dbs.catalog
    query = q.strip()
    langs = expand_language(language) if language and language != "auto" else ()
    lang_clause = ""
    lang_params: list[str] = []
    if langs:
        placeholders = ",".join("?" for _ in langs)
        lang_clause = f" AND cards.language IN ({placeholders})"
        lang_params = list(langs)

    has_cjk = any(ord(char) > 0x2E80 for char in query)
    tokens = re.findall(r"[A-Za-z0-9/]+", query)
    if has_cjk:
        like = f"%{query}%"
        rows = catalog.execute(
            f"""
            SELECT * FROM cards
            WHERE (name LIKE ? OR set_name LIKE ? OR collector_number LIKE ?)
            {lang_clause}
            ORDER BY set_name, collector_number
            LIMIT ?
            """,
            (like, like, like, *lang_params, limit),
        ).fetchall()
        total_row = catalog.execute(
            f"""
            SELECT COUNT(*) AS n FROM cards
            WHERE (name LIKE ? OR set_name LIKE ? OR collector_number LIKE ?)
            {lang_clause}
            """,
            (like, like, like, *lang_params),
        ).fetchone()
        total = int(total_row["n"] if total_row else 0)
    elif tokens:
        fts = " ".join(f"{token}*" for token in tokens)
        rows = catalog.execute(
            f"""
            SELECT cards.*
            FROM cards_fts
            JOIN cards ON cards.id = cards_fts.id
            WHERE cards_fts MATCH ?
            {lang_clause}
            LIMIT ?
            """,
            (fts, *lang_params, limit),
        ).fetchall()
        total_row = catalog.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM cards_fts
            JOIN cards ON cards.id = cards_fts.id
            WHERE cards_fts MATCH ?
            {lang_clause}
            """,
            (fts, *lang_params),
        ).fetchone()
        total = int(total_row["n"] if total_row else 0)
    else:
        rows = catalog.execute(
            f"""
            SELECT * FROM cards
            WHERE 1=1 {lang_clause}
            ORDER BY set_name, collector_number
            LIMIT ?
            """,
            (*lang_params, limit),
        ).fetchall()
        total_row = catalog.execute(
            f"SELECT COUNT(*) AS n FROM cards WHERE 1=1 {lang_clause}",
            lang_params,
        ).fetchone()
        total = int(total_row["n"] if total_row else 0)

    return CardSearchResponse(items=[_summary(row) for row in rows], total=total)


@router.get("/cards/{card_id}", response_model=CardSummary)
def get_card(card_id: str, request: Request) -> CardSummary:
    row = request.app.state.dbs.catalog.execute(
        "SELECT * FROM cards WHERE id = ?", (card_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return _summary(row)


@router.get("/cards/{card_id}/image")
def card_image(card_id: str, request: Request) -> FileResponse:
    row = request.app.state.dbs.catalog.execute(
        "SELECT image_path, has_image FROM cards WHERE id = ?", (card_id,)
    ).fetchone()
    if row is None or not row["has_image"] or not row["image_path"]:
        raise HTTPException(status_code=404, detail="Card image not found")
    path = Path(row["image_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Card image not found")
    media = "image/webp" if path.suffix.lower() == ".webp" else "image/jpeg"
    return FileResponse(path, media_type=media)
