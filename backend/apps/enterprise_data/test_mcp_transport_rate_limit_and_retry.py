from __future__ import annotations

import uuid

import httpx
import pytest

from apps.core.exceptions import ValidationException
from apps.enterprise_data.services.transports.mcp_transport import McpToolTransport


def test_call_tool_retries_on_timeout_before_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def _fake_call_tool(
        self: McpToolTransport,
        *,
        transport: str,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        calls.append(transport)
        if len(calls) == 1:
            raise httpx.ReadTimeout("timeout")
        return {"payload": {"items": []}, "raw": {"is_error": False}}

    monkeypatch.setattr(McpToolTransport, "_call_tool_async", _fake_call_tool)

    transport = McpToolTransport(
        provider_name="tianyancha",
        transport="streamable_http",
        base_url="https://mcp-service.tianyancha.com/mcp",
        sse_url="",
        api_key="test-api-key",
        timeout_seconds=10,
        retry_max_attempts=2,
        retry_backoff_seconds=0,
    )
    result = transport.call_tool(tool_name="search_companies", arguments={"keyword": "腾讯"})

    assert calls == ["streamable_http", "streamable_http"]
    assert result["attempt_count"] == 2
    assert result["fallback_used"] is False


def test_call_tool_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_tool(
        self: McpToolTransport,
        *,
        transport: str,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        return {"payload": {"ok": True}, "raw": {"is_error": False}}

    monkeypatch.setattr(McpToolTransport, "_call_tool_async", _fake_call_tool)

    transport = McpToolTransport(
        provider_name=f"tianyancha-{uuid.uuid4().hex[:8]}",
        transport="streamable_http",
        base_url="https://mcp-service.tianyancha.com/mcp",
        sse_url="",
        api_key="test-api-key",
        timeout_seconds=10,
        rate_limit_requests=1,
        rate_limit_window_seconds=300,
    )

    transport.call_tool(tool_name="search_companies", arguments={"keyword": "腾讯"})
    with pytest.raises(ValidationException) as exc_info:
        transport.call_tool(tool_name="search_companies", arguments={"keyword": "腾讯"})

    assert exc_info.value.code == "MCP_RATE_LIMITED"
