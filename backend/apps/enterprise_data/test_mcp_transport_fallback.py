from __future__ import annotations

import pytest

from apps.core.exceptions import ExternalServiceError
from apps.enterprise_data.services.transports.mcp_transport import McpToolTransport


def _build_transport(*, sse_url: str = "https://mcp-service.tianyancha.com/sse") -> McpToolTransport:
    return McpToolTransport(
        provider_name="tianyancha",
        transport="streamable_http",
        base_url="https://mcp-service.tianyancha.com/mcp",
        sse_url=sse_url,
        api_key="test-api-key",
        timeout_seconds=10,
    )


def test_call_tool_fallback_to_sse_when_streamable_http_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def _fake_call_tool(
        self: McpToolTransport,
        *,
        transport: str,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        calls.append(transport)
        if transport == "streamable_http":
            raise RuntimeError("primary transport blocked")
        return {"payload": {"items": []}, "raw": {"is_error": False}}

    monkeypatch.setattr(McpToolTransport, "_call_tool_async", _fake_call_tool)

    transport = _build_transport()
    result = transport.call_tool(tool_name="search_companies", arguments={"keyword": "腾讯"})

    assert calls == ["streamable_http", "sse"]
    assert result["transport"] == "sse"
    assert result["requested_transport"] == "streamable_http"
    assert result["fallback_used"] is True


def test_list_tools_fallback_to_sse_when_streamable_http_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def _fake_describe_tools(self: McpToolTransport, *, transport: str) -> list[dict[str, object]]:
        calls.append(transport)
        if transport == "streamable_http":
            raise RuntimeError("primary transport blocked")
        return [
            {"name": "search_companies", "description": "", "input_schema": {}},
            {"name": "get_company_info", "description": "", "input_schema": {}},
        ]

    monkeypatch.setattr(McpToolTransport, "_describe_tools_async", _fake_describe_tools)

    transport = _build_transport()
    tools = transport.list_tools()

    assert calls == ["streamable_http", "sse"]
    assert tools == ["search_companies", "get_company_info"]


def test_call_tool_raises_when_fallback_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_tool(
        self: McpToolTransport,
        *,
        transport: str,
        tool_name: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        raise RuntimeError(f"{transport}:{tool_name}")

    monkeypatch.setattr(McpToolTransport, "_call_tool_async", _fake_call_tool)

    transport = _build_transport(sse_url="")
    with pytest.raises(ExternalServiceError) as exc_info:
        transport.call_tool(tool_name="search_companies", arguments={"keyword": "腾讯"})

    assert exc_info.value.code == "MCP_TRANSPORT_ERROR"
