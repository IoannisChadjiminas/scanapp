import asyncio
import logging
from types import SimpleNamespace

import pytest
from starlette.responses import Response

from app.main import scan_diagnostics


def _request(trace="mobile-123"):
    return SimpleNamespace(method="POST", url=SimpleNamespace(path="/api/v1/scans"), headers={"x-scan-trace": trace}, state=SimpleNamespace())


def test_scan_logs_correlate_and_echo_trace(caplog):
    async def run():
        request = _request()
        async def next_handler(request):
            assert request.state.scan_trace == "mobile-123"
            return Response(status_code=200)
        return await scan_diagnostics(request, next_handler)
    with caplog.at_level(logging.INFO, logger="scan.diagnostics"):
        response = asyncio.run(run())
    assert response.headers["x-scan-trace"] == "mobile-123"
    assert "request_start trace=mobile-123" in caplog.text
    assert "request_done trace=mobile-123 status=200" in caplog.text


def test_invalid_trace_is_not_logged(caplog):
    async def run():
        async def next_handler(request):
            return Response()
        return await scan_diagnostics(_request("private-injected\ntrace"), next_handler)
    with caplog.at_level(logging.INFO, logger="scan.diagnostics"):
        response = asyncio.run(run())
    assert "private-injected" not in caplog.text
    assert "\n" not in response.headers["x-scan-trace"]


def test_scan_error_logs_category_not_private_message(caplog):
    async def run():
        async def next_handler(request):
            raise ValueError("private-secret-value")
        return await scan_diagnostics(_request(), next_handler)
    with caplog.at_level(logging.INFO, logger="scan.diagnostics"), pytest.raises(ValueError):
        asyncio.run(run())
    assert "error_type=ValueError" in caplog.text
    assert "private-secret-value" not in caplog.text
