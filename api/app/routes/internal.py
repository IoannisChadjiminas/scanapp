"""Private PokeSingle API integration. No browser sessions or client credentials."""

from __future__ import annotations

from datetime import timezone
from hmac import compare_digest

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.cardmarket import is_verified_singles_url
from app.cardmarket_daily import replace_portfolio
from app.portfolio_db import connect_portfolio

router = APIRouter()


def require_service(request: Request, authorization: str | None = Header(default=None)) -> None:
    expected = request.app.state.settings.scanapp_service_token.get_secret_value()
    if not expected:
        raise HTTPException(status_code=404, detail="Not found")
    # Refuse weak/misconfigured credentials as well as absent configuration.
    if len(expected) < 32:
        raise HTTPException(status_code=503, detail="Service authentication unavailable")
    presented = (authorization or "").removeprefix("Bearer ")
    if not (authorization or "").startswith("Bearer ") or not compare_digest(
        presented.encode(), expected.encode()
    ):
        raise HTTPException(status_code=401, detail="Unauthenticated")


class ServiceProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=8, max_length=500)
    opened_at: AwareDatetime

    @field_validator("url")
    @classmethod
    def singles_url(cls, value: str) -> str:
        if not is_verified_singles_url(value):
            raise ValueError("Cardmarket Singles URL required")
        return value


class ServicePortfolio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Reserved namespace: cannot overwrite browser session UUIDs.
    owner_key: str = Field(pattern=r"^user:[A-Za-z0-9_-]{1,128}$")
    products: list[ServiceProduct] = Field(max_length=10_000)


@router.post("/internal/portfolio/products", dependencies=[Depends(require_service)])
def sync_member_portfolio(payload: ServicePortfolio, request: Request) -> dict[str, int]:
    url = request.app.state.settings.portfolio_database_url.get_secret_value()
    if not url:
        raise HTTPException(status_code=503, detail="Portfolio storage unavailable")
    # Separate connection and transaction from browser sessions, history writes,
    # and background price jobs. Empty snapshots implement account cleanup.
    conn = connect_portfolio(url)
    try:
        count = replace_portfolio(
            conn,
            payload.owner_key,
            [(item.url, item.opened_at.astimezone(timezone.utc).isoformat()) for item in payload.products],
            lock_owner=True,
        )
    finally:
        conn.close()
    return {"count": count}
