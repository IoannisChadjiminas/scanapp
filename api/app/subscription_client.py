"""Fail-closed, server-to-server subscription checks.

Secrets and response bodies are never written to logs. The product API is the
authority for eligibility and rollout; this service never trusts phone claims.
"""
from __future__ import annotations

from urllib.parse import urlsplit

import httpx

from app.config import Settings


class SubscriptionUnavailable(Exception):
    pass


class SubscriptionClient:
    def __init__(self, settings: Settings, *, client: httpx.Client | None = None):
        self.base = settings.product_api_url.rstrip('/')
        self.token = settings.scanapp_service_token.get_secret_value()
        self.client = client
        parsed = urlsplit(self.base)
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment or len(self.token) < 32):
            raise SubscriptionUnavailable('product API is not configured')
        if parsed.scheme != 'https' and parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
            raise SubscriptionUnavailable('product API requires HTTPS')

    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            with httpx.Client(timeout=8, follow_redirects=False) if self.client is None else _borrow(self.client) as client:
                response = client.request(method, self.base + path,
                    headers={'Authorization': f'Bearer {self.token}'}, **kwargs)
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict):
                    raise ValueError('expected object')
                return result
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise SubscriptionUnavailable('product API unavailable') from exc

    def eligible(self, sample: str) -> bool:
        body = self._request('POST', '/internal/price-refresh/eligible', json={'samples': [sample]})
        eligible = body.get('samples')
        if not isinstance(eligible, list) or any(not isinstance(item, str) for item in eligible):
            raise SubscriptionUnavailable('invalid eligibility response')
        return sample in eligible

    def claim_price(self, permit: str, sample: str) -> tuple[str, str]:
        body = self._request('POST', '/internal/price-refresh/permits/claim',
                             json={'permit': permit, 'sampleKey': sample})
        request_id, permit_id = body.get('requestId'), body.get('permitId')
        if (body.get('state') != 'claimed' or not isinstance(request_id, str) or
                not isinstance(permit_id, str) or not permit_id.isascii() or not permit_id.isdecimal()):
            raise SubscriptionUnavailable('invalid price claim')
        return request_id, permit_id

    def authorize_price(self, request_id: str, permit_id: str, sample: str) -> bool:
        body = self._request('POST', '/internal/price-refresh/permits/authorize', json={
            'requestId': request_id, 'permitId': permit_id, 'sampleKey': sample,
        })
        value = body.get('authorized')
        if not isinstance(value, bool):
            raise SubscriptionUnavailable('invalid price authorization')
        return value

    def price_budget(self) -> tuple[int, int]:
        _, _, refresh = self.candidates(limit=1)
        pages, megabytes = refresh.get('dailyPageBudget'), refresh.get('dailyMegabyteBudget')
        if (type(pages) is not int or type(megabytes) is not int or
                not 0 <= pages <= 1_000_000 or not 0 <= megabytes <= 1_000_000):
            raise SubscriptionUnavailable('invalid price budget')
        return pages, megabytes

    def scan_quota_enforced(self) -> bool:
        value = self._request('GET', '/internal/scans/policy').get('quotaEnforced')
        if not isinstance(value, bool):
            raise SubscriptionUnavailable('invalid scan policy')
        return value

    def claim_scan(self, permit: str, execution_id: str, session_id: str, attempt_id: str) -> str:
        body = self._request('POST', '/internal/scans/permits/claim', json={
            'permit': permit, 'attemptId': attempt_id, 'executionId': execution_id, 'sessionId': session_id,
        })
        permit_id = body.get('permitId')
        if (body.get('state') != 'claimed' or body.get('attemptId') != attempt_id or
                not isinstance(permit_id, str) or not permit_id.isascii() or not permit_id.isdecimal()):
            raise SubscriptionUnavailable('invalid scan claim')
        return permit_id

    def heartbeat_scan(self, attempt_id: str, execution_id: str, session_id: str) -> None:
        body = self._request('POST', '/internal/scans/permits/heartbeat', json={
            'attemptId': attempt_id, 'executionId': execution_id, 'sessionId': session_id,
        })
        if body.get('state') != 'claimed':
            raise SubscriptionUnavailable('invalid scan heartbeat')

    def inspect_scan(self, attempt_id: str, execution_id: str, session_id: str) -> dict:
        body = self._request('POST', '/internal/scans/permits/inspect', json={
            'attemptId': attempt_id, 'executionId': execution_id, 'sessionId': session_id,
        })
        state = body.get('state')
        if state not in {'reserved', 'expired', 'claimed', 'settled', 'released'}:
            raise SubscriptionUnavailable('invalid scan state')
        if state in {'claimed', 'settled', 'released'}:
            permit_id = body.get('permitId')
            if not isinstance(permit_id, str) or not permit_id.isascii() or not permit_id.isdecimal():
                raise SubscriptionUnavailable('invalid scan state')
        return body

    def settle_scan(self, attempt_id: str, execution_id: str, session_id: str,
                    outcome: str, scan_id: str | None = None) -> None:
        payload = {'attemptId': attempt_id, 'executionId': execution_id, 'sessionId': session_id,
                   'outcome': outcome}
        if scan_id is not None:
            payload['resultReference'] = scan_id
        body = self._request('POST', '/internal/scans/permits/settle', json=payload)
        expected = 'settled' if outcome == 'usable' else 'released'
        if body.get('state') != expected or body.get('outcome') != outcome:
            raise SubscriptionUnavailable('invalid scan settlement')

    def candidates(self, *, after: str | None = None, limit: int = 100) -> tuple[list[str], str | None, dict]:
        params = {'limit': limit}
        if after is not None:
            params['after'] = after
        body = self._request('GET', '/internal/price-refresh/candidates', params=params)
        items, cursor, refresh = body.get('items'), body.get('next'), body.get('refresh')
        if (not isinstance(items, list) or len(items) > limit or
                any(not isinstance(item, str) or not item or len(item) > 2048 for item in items) or
                (cursor is not None and (not isinstance(cursor, str) or cursor not in items)) or
                not isinstance(refresh, dict)):
            raise SubscriptionUnavailable('invalid candidate response')
        return items, cursor, refresh


class _borrow:
    def __init__(self, client: httpx.Client):
        self.client = client

    def __enter__(self):
        return self.client

    def __exit__(self, *_):
        return False
