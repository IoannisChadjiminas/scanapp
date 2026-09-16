from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response

from app.config import Settings
from app.db import Databases


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_session(
    request: Request,
    response: Response,
    dbs: Databases,
    settings: Settings,
) -> str:
    cookie = request.cookies.get(settings.session_cookie)
    if cookie:
        row = dbs.results.execute(
            "SELECT id FROM sessions WHERE id = ?", (cookie,)
        ).fetchone()
        if row:
            dbs.results.execute(
                "UPDATE sessions SET last_seen = ? WHERE id = ?",
                (_now().isoformat(), cookie),
            )
            dbs.results.commit()
            return cookie
    session_id = str(uuid.uuid4())
    stamp = _now().isoformat()
    dbs.results.execute(
        "INSERT INTO sessions (id, created_at, last_seen) VALUES (?, ?, ?)",
        (session_id, stamp, stamp),
    )
    dbs.results.commit()
    response.set_cookie(
        key=settings.session_cookie,
        value=session_id,
        max_age=int(timedelta(days=settings.session_ttl_days).total_seconds()),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )
    return session_id


def require_scan_owner(dbs: Databases, scan_id: str, session_id: str) -> None:
    row = dbs.results.execute(
        "SELECT session_id FROM scans WHERE id = ?", (scan_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    if row["session_id"] != session_id:
        raise HTTPException(status_code=403, detail="Scan does not belong to this session")
