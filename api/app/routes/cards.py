from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.card_images import display_image_url
from app.cardmarket import url_for_row, variants_for_row
from app.recognition.language import expand_language
from app.set_totals import set_total
from app.schemas import CardmarketVariant, CardSearchResponse, CardSummary
from app.visual_aliases import visual_image_owner

router = APIRouter()


def _summary(row, catalog=None) -> CardSummary:  # noqa: ANN001
    image_url = display_image_url(row, catalog)
    owner = visual_image_owner(row, catalog)
    return CardSummary(
        id=row["id"],
        name=row["name"],
        set_id=row["set_id"],
        set_name=row["set_name"],
        collector_number=row["collector_number"],
        set_total=set_total(catalog, row["language"], row["set_id"]) if catalog is not None else None,
        language=row["language"],
        rarity=str(row["rarity"] or ""),
        has_image=bool(image_url),
        image_url=image_url,
        image_owner_id=owner["id"] if owner is not row else None,
        variants=json.loads(row["variants_json"] or "{}"),
        cardmarket_url=url_for_row(row),
    )


@router.get("/cards", response_model=CardSearchResponse)
def search_cards(
    request: Request,
    q: str = Query(default="", min_length=0, max_length=80),
    language: str = Query(default="", max_length=16),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=10_000),
) -> CardSearchResponse:
    """One page of matches. Every query has a fixed order, so `offset` pages
    neither repeat nor skip cards."""
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
            ORDER BY set_name, collector_number, id
            LIMIT ? OFFSET ?
            """,
            (like, like, like, *lang_params, limit, offset),
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
            ORDER BY cards_fts.rowid
            LIMIT ? OFFSET ?
            """,
            (fts, *lang_params, limit, offset),
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
            ORDER BY set_name, collector_number, id
            LIMIT ? OFFSET ?
            """,
            (*lang_params, limit, offset),
        ).fetchall()
        total_row = catalog.execute(
            f"SELECT COUNT(*) AS n FROM cards WHERE 1=1 {lang_clause}",
            lang_params,
        ).fetchone()
        total = int(total_row["n"] if total_row else 0)

    return CardSearchResponse(items=[_summary(row, catalog) for row in rows], total=total)


@router.get("/cards/{card_id}", response_model=CardSummary)
def get_card(card_id: str, request: Request) -> CardSummary:
    row = request.app.state.dbs.catalog.execute(
        "SELECT * FROM cards WHERE id = ?", (card_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Card not found")
    summary = _summary(row, request.app.state.dbs.catalog)
    summary.cardmarket_variants = [
        CardmarketVariant.model_validate(variant)
        for variant in variants_for_row(request.app.state.dbs.catalog, row)
    ]
    return summary


@router.get("/cards/{card_id}/image")
def card_image(card_id: str, request: Request) -> FileResponse:
    row = request.app.state.dbs.catalog.execute(
        "SELECT * FROM cards WHERE id = ?", (card_id,)
    ).fetchone()
    if row is not None:
        row = visual_image_owner(row, request.app.state.dbs.catalog)
    if row is None or not row["has_image"] or not row["image_path"]:
        raise HTTPException(status_code=404, detail="Card image not found")
    path = Path(row["image_path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Card image not found")
    media = "image/webp" if path.suffix.lower() == ".webp" else "image/jpeg"
    return FileResponse(path, media_type=media)
