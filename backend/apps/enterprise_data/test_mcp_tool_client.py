from __future__ import annotations

import httpx
import pytest
from django.core.cache import cache

from apps.core.exceptions import AuthenticationError, ValidationException
from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry


class _StubConfigService:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get_value(self, key: str, default: str = "") -> str:
        return self._values.get(key, default)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    cache.clear()


def _build_client(*, api_keys: tuple[str, ...]) -> McpToolClient:
    return McpToolClient(
        provider_name="tianyancha",
        transport="streamable_http",
        base_url="https://example.com/mcp",
        sse_url="",
        api_key=api_keys[0],
        api_keys=api_keys,
        retry_max_attempts=1,
    )


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.com/mcp")
    body = '{"detail":"Internal server error during authentication","type":"auth_error"}' if status_code == 500 else f"status={status_code}"
    response = httpx.Response(status_code=status_code, request=request, text=body)
    return httpx.HTTPStatusError(message=f"HTTP {status_code}", request=request, response=response)


def test_provider_registry_parses_multiple_tianyancha_api_keys() -> None:
    registry = EnterpriseProviderRegistry(
        config_service=_StubConfigService(
            {
                "TIANYANCHA_MCP_ENABLED": "True",
                "TIANYANCHA_MCP_TRANSPORT": "streamable_http",
                "TIANYANCHA_MCP_BASE_URL": "https://example.com/mcp",
                "TIANYANCHA_MCP_SSE_URL": "https://example.com/sse",
                "TIANYANCHA_MCP_API_KEY": " key-a \nkey-b,key-c;key-b ",
                "TIANYANCHA_MCP_TIMEOUT_SECONDS": "30",
            }
        )
    )

    provider = registry.get_provider("tianyancha")

    assert provider._client._api_key == "key-a"
    assert provider._client._api_key_pool.ordered_keys() == ["key-a", "key-b", "key-c"]


def test_call_tool_switches_to_next_api_key_after_auth_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_client(api_keys=("key-a", "key-b"))
    attempts: list[str] = []

    async def fake_call_tool_async(*, transport: str, tool_name: str, arguments: dict[str, str], api_key: str) -> dict[str, object]:
        attempts.append(api_key)
        if api_key == "key-a":
            raise AuthenticationError(message="bad key", code="MCP_AUTH_ERROR")
        return {
            "payload": {"selected_key": api_key},
            "raw": {"is_error": False, "structured_content": None, "content": []},
        }

    monkeypatch.setattr(client, "_call_tool_async", fake_call_tool_async)

    first_result = client.call_tool(tool_name="search_companies", arguments={"keyword": "腾讯"})

    assert attempts == ["key-a", "key-b"]
    assert first_result["payload"]["selected_key"] == "key-b"
    assert first_result["api_key_attempt_count"] == 2
    assert first_result["api_key_switched"] is True

    attempts.clear()
    second_result = client.call_tool(tool_name="search_companies", arguments={"keyword": "腾讯"})

    assert attempts == ["key-b"]
    assert second_result["payload"]["selected_key"] == "key-b"
    assert second_result["api_key_attempt_count"] == 1


def test_describe_tools_switches_to_next_api_key_after_remote_429(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_client(api_keys=("key-a", "key-b"))
    attempts: list[str] = []

    async def fake_describe_tools_async(*, transport: str, api_key: str) -> list[dict[str, object]]:
        attempts.append(api_key)
        if api_key == "key-a":
            raise _http_status_error(429)
        return [{"name": "search_companies", "description": "ok", "input_schema": {}}]

    monkeypatch.setattr(client, "_describe_tools_async", fake_describe_tools_async)

    tools = client.describe_tools()

    assert attempts == ["key-a", "key-b"]
    assert tools == [{"name": "search_companies", "description": "ok", "input_schema": {}}]

    attempts.clear()
    second_tools = client.describe_tools()

    assert attempts == ["key-b"]
    assert second_tools == tools


def test_call_tool_does_not_switch_api_key_for_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _build_client(api_keys=("key-a", "key-b"))
    attempts: list[str] = []

    async def fake_call_tool_async(*, transport: str, tool_name: str, arguments: dict[str, str], api_key: str) -> dict[str, object]:
        attempts.append(api_key)
        raise ValidationException(message="invalid arguments", code="INVALID_ARGUMENTS")

    monkeypatch.setattr(client, "_call_tool_async", fake_call_tool_async)

    with pytest.raises(ValidationException):
        client.call_tool(tool_name="get_company_info", arguments={"company_id": ""})

    assert attempts == ["key-a"]


def test_streamable_http_unhealthy_cache_prefers_sse_after_known_gateway_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = McpToolClient(
        provider_name="tianyancha",
        transport="streamable_http",
        base_url="https://example.com/mcp",
        sse_url="https://example.com/sse",
        api_key="key-a",
        api_keys=("key-a",),
        retry_max_attempts=1,
    )
    attempts: list[str] = []

    async def fake_describe_tools_async(*, transport: str, api_key: str) -> list[dict[str, object]]:
        attempts.append(transport)
        if transport == "streamable_http":
            raise _http_status_error(500)
        return [{"name": "search_companies", "description": "ok", "input_schema": {}}]

    monkeypatch.setattr(client, "_describe_tools_async", fake_describe_tools_async)

    first_tools = client.describe_tools()

    assert attempts == ["streamable_http", "sse"]
    assert first_tools == [{"name": "search_companies", "description": "ok", "input_schema": {}}]

    attempts.clear()
    second_tools = client.describe_tools()

    assert attempts == ["sse"]
    assert second_tools == first_tools
