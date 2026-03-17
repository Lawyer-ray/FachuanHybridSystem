from __future__ import annotations

from typing import Any

from apps.enterprise_data.services.providers.tianyancha_mcp import TianyanchaMcpProvider
from apps.enterprise_data.services.types import ProviderConfig


def _provider() -> TianyanchaMcpProvider:
    return TianyanchaMcpProvider(
        config=ProviderConfig(
            name="tianyancha",
            enabled=True,
            transport="streamable_http",
            base_url="https://mcp-service.tianyancha.com/mcp",
            sse_url="https://mcp-service.tianyancha.com/sse",
            api_key="test-api-key",
            timeout_seconds=10,
        )
    )


def test_search_companies_meta_uses_actual_transport_from_transport_result() -> None:
    provider = _provider()

    def _fake_call_tool(*, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        assert tool_name == "search_companies"
        assert arguments == {"keyword": "阿里巴巴"}
        return {
            "payload": {"items": [{"companyId": "1", "name": "阿里巴巴"}]},
            "raw": {"is_error": False},
            "transport": "sse",
            "requested_transport": "streamable_http",
        }

    provider._transport.call_tool = _fake_call_tool  # type: ignore[method-assign]
    response = provider.search_companies(keyword="阿里巴巴")

    assert response.meta["transport"] == "sse"
    assert response.meta["requested_transport"] == "streamable_http"
    assert response.meta["fallback_used"] is True


def test_search_companies_meta_defaults_to_provider_transport() -> None:
    provider = _provider()

    def _fake_call_tool(*, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        assert tool_name == "search_companies"
        assert arguments == {"keyword": "腾讯"}
        return {
            "payload": {"items": [{"companyId": "2", "name": "腾讯"}]},
            "raw": {"is_error": False},
        }

    provider._transport.call_tool = _fake_call_tool  # type: ignore[method-assign]
    response = provider.search_companies(keyword="腾讯")

    assert response.meta["transport"] == "streamable_http"
    assert response.meta["requested_transport"] == "streamable_http"
    assert response.meta["fallback_used"] is False
