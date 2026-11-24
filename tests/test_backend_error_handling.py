"""Regression tests for safe API error responses."""

import pytest
from starlette.requests import Request

from src_tauri.backend.main import global_exception_handler


@pytest.mark.asyncio
async def test_global_exception_handler_does_not_expose_exception_details():
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/system/status",
            "raw_path": b"/api/system/status",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 54321),
            "server": ("127.0.0.1", 8765),
        }
    )
    response = await global_exception_handler(
        request,
        RuntimeError("private database path C:\\Users\\example\\secret.db"),
    )

    assert response.status_code == 500
    assert response.body == b'{"error":"Internal server error"}'
    assert b"secret.db" not in response.body
