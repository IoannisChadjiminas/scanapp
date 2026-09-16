from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.schemas import CardSearchResponse, CardSummary

router = APIRouter()


def _image_url(card_id: str, has_image: bool) -> str | None:
    if not has_image:
        return None
    return f"/api/v1/cards/{card_id}/image"


@router.get("/cards", response_model=CardSearchResponse)
def search_cards(
    request: Request,
    q: str = Query(default="", min_length=0, max_length=80),
    limit: int = Query(default=20, ge=1, le=50),
) -> CardSearchResponse:
    catalog = request.app.state.dbs.catalog
    query = q.strip()
    tokens = re.findall(r"[A-Za-z0-9/]+", query)
    fts = " ".join(f"{token}*" for token in tokens)
    if fts:
        rows = catalog.execute(
            """
            SELECT cards.*
            FROM cards_fts
            JOIN cards ON cards.id = cards_fts.id
            WHERE cards_fts MATCH ?
            LIMIT ?
            """,
            (fts, limit),
        ).fetchall()
        total_row = catalog.execute(
            "SELECT COUNT(*) AS n FROM cards_fts WHERE cards_fts MATCH ?",
            (fts,),
        ).fetchone()
        total = int(total_row["n"] if total_row else 0)
    else:
        rows = catalog.execute(
            "SELECT * FROM cards ORDER BY set_name, collector_number LIMIT ?",
            (limit,),
        ).fetchall()
        total_row = catalog.execute("SELECT COUNT(*) AS n FROM cards").fetchone()
        total = int(total_row["n"] if total_row else 0)

    items = [
        CardSummary(
            id=row["id"],
            name=row["name"],
            set_id=row["set_id"],
            set_name=row["set_name"],
            collector_number=row["collector_number"],
            language=row["language"],
            has_image=bool(row["has_image"]),
            image_url=_image_url(row["id"], bool(row["has_image"])),
            variants=json.loads(row["variants_json"] or "{}"),
        )
        for row in rows
    ]
    return CardSearchResponse(items=items, total=total)


@router.get("/cards/{card_id}", response_model=CardSummary)
def get_card(card_id: str, request: Request) -> CardSummary:
    row = request.app.state.dbs.catalog.execute(
        "SELECT * FROM cards WHERE id = ?", (card_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Card not found")
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
    )


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
