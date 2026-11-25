"""Pro live-check permits: one claimed permit per live marketplace read.

When `product_api_live_gate_ready` is on, a live read needs the header
`x-pokesingle-live-permit`, claimed once at the product API for its kind.
The permit is a secret: it is never logged or stored here.
"""
from __future__ import annotations

from fastapi import HTTPException, Request

from app.config import get_settings
from app.subscription_client import PermitRefused, SubscriptionClient, SubscriptionUnavailable

HEADER = 'x-pokesingle-live-permit'
KINDS = frozenset({'ebay', 'cardtrader', 'cardmarket'})


def require_live_permit(request: Request, kind: str) -> None:
    """Claim the request's permit for [kind]; no-op while the gate is not ready."""
    assert kind in KINDS
    settings = get_settings()
    if not settings.product_api_live_gate_ready:
        return
    permit = request.headers.get(HEADER, '')
    if not 40 <= len(permit) <= 100:
        raise HTTPException(status_code=403, detail='subscription_required')
    try:
        SubscriptionClient(settings).claim_live(permit, kind)
    except PermitRefused:
        raise HTTPException(status_code=403, detail='subscription_required') from None
    except SubscriptionUnavailable:
        raise HTTPException(status_code=503, detail='Live checks unavailable') from None
