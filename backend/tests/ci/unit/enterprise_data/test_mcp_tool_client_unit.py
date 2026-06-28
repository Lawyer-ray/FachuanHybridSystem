"""mcp_tool_client.py 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.core.exceptions import AuthenticationError, ExternalServiceError, ValidationException


class TestMcpToolClientInit:

    def test_api_keys_normalized(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(
            provider_name="test",
            transport="streamable_http",
            base_url="http://example.com",
            sse_url="",
            api_key="key1",  # pragma: allowlist secret
            api_keys=["key1", "key2"],
        )
        assert client._api_key == "key1"

    def test_single_api_key(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(
            provider_name="test",
            transport="streamable_http",
            base_url="http://example.com",
            sse_url="",
            api_key="single_key",  # pragma: allowlist secret
        )
        assert client._api_key == "single_key"


class TestMcpToolClientHeaders:

    def test_streamable_http_uses_lowercase_bearer(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(
            provider_name="test",
            transport="streamable_http",
            base_url="http://example.com",
            sse_url="",
            api_key="key123",  # pragma: allowlist secret
        )
        headers = client._headers(transport="streamable_http", api_key="key123")  # pragma: allowlist secret
        assert headers["Authorization"] == "bearer key123"

    def test_sse_uses_capital_bearer(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(
            provider_name="test",
            transport="sse",
            base_url="",
            sse_url="http://example.com/sse",
            api_key="key123",  # pragma: allowlist secret
        )
        headers = client._headers(transport="sse", api_key="key123")  # pragma: allowlist secret
        assert headers["Authorization"] == "Bearer key123"


class TestMcpToolClientTryParseJson:

    def test_valid_json(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        assert McpToolClient._try_parse_json('{"key": "value"}') == {"key": "value"}

    def test_invalid_json(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        assert McpToolClient._try_parse_json("not json") is None

    def test_array_json(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        assert McpToolClient._try_parse_json("[1, 2, 3]") == [1, 2, 3]


class TestMcpToolClientContainsAuthToken:

    @pytest.mark.parametrize("text,expected", [
        ("authentication_error", True),
        ("unauthorized", True),
        ("invalid api key", True),
        ("normal error", False),
        ("", False),
        ("token expired", True),
        ("API key invalid", True),
    ])
    def test_contains_auth_token(self, text, expected):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        assert McpToolClient._contains_auth_token(text) == expected


class TestMcpToolClientIsAuthLikeHttpError:

    def test_401_is_auth(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        resp = MagicMock()
        resp.status_code = 401
        resp.text = ""
        resp.json.side_effect = ValueError
        error = type("HTTPStatusError", (Exception,), {"response": resp})()
        assert McpToolClient._is_auth_like_http_error(error) is True

    def test_403_is_auth(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        resp = MagicMock()
        resp.status_code = 403
        resp.text = ""
        resp.json.side_effect = ValueError
        error = type("HTTPStatusError", (Exception,), {"response": resp})()
        assert McpToolClient._is_auth_like_http_error(error) is True

    def test_500_is_not_auth(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "server error"
        resp.json.side_effect = ValueError
        error = type("HTTPStatusError", (Exception,), {"response": resp})()
        assert McpToolClient._is_auth_like_http_error(error) is False


class TestMcpToolClientShouldRetry:

    def test_timeout_is_retryable(self):
        import httpx

        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(
            provider_name="test", transport="streamable_http",
            base_url="http://example.com", sse_url="", api_key="key",  # pragma: allowlist secret
        )
        assert client._should_retry(httpx.TimeoutException("timeout")) is True

    def test_connect_error_is_retryable(self):
        import httpx

        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(
            provider_name="test", transport="streamable_http",
            base_url="http://example.com", sse_url="", api_key="key",
        )
        assert client._should_retry(httpx.ConnectError("refused")) is True

    def test_validation_not_retryable(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(
            provider_name="test", transport="streamable_http",
            base_url="http://example.com", sse_url="", api_key="key",
        )
        assert client._should_retry(ValidationException(message="err", code="X", errors={})) is False

    def test_auth_error_not_retryable(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(
            provider_name="test", transport="streamable_http",
            base_url="http://example.com", sse_url="", api_key="key",
        )
        assert client._should_retry(AuthenticationError(message="err", code="X", errors={})) is False


class TestMcpToolClientShouldSwitchApiKey:

    def test_auth_error_switches(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(
            provider_name="test", transport="streamable_http",
            base_url="http://example.com", sse_url="", api_key="key",
        )
        assert client._should_switch_api_key(
            AuthenticationError(message="err", code="X", errors={})
        ) is True

    def test_connect_error_does_not_switch(self):
        import httpx

        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(
            provider_name="test", transport="streamable_http",
            base_url="http://example.com", sse_url="", api_key="key",
        )
        assert client._should_switch_api_key(httpx.ConnectError("refused")) is False


class TestMcpToolClientFlattenErrorPayloadText:

    def test_flatten_dict(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        result = McpToolClient._flatten_error_payload_text({"error": "not found", "code": 404})
        assert "not found" in result
        assert "404" in result

    def test_flatten_nested(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        result = McpToolClient._flatten_error_payload_text({"errors": [{"msg": "bad"}]})
        assert "bad" in result

    def test_flatten_none(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        assert McpToolClient._flatten_error_payload_text(None) == ""


class TestMcpToolClientCollectRelatedExceptions:

    def test_single_exception(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        exc = ValueError("test")
        result = McpToolClient._collect_related_exceptions(exc)
        assert len(result) >= 1
        assert result[0] is exc

    def test_chained_exception(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        cause = ValueError("cause")
        exc = RuntimeError("wrapper")
        exc.__cause__ = cause
        result = McpToolClient._collect_related_exceptions(exc)
        assert cause in result
        assert exc in result


@pytest.mark.asyncio
async def test_acall_tool_success():
    from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
    client = McpToolClient(
        provider_name="test",
        transport="streamable_http",
        base_url="http://test",
        sse_url="",
        api_key="",
        api_keys=["key1"],
    )
    mock_result = {"payload": {"data": "test"}, "raw": {}}
    mock_meta = {"duration_ms": 100}
    client._acquire_rate_limit = MagicMock()
    client._aexecute_with_api_key_failover = AsyncMock(return_value=(mock_result, mock_meta))
    result = await client.acall_tool(tool_name="search", arguments={"q": "test"})
    assert result["payload"] == {"data": "test"}
    client._aexecute_with_api_key_failover.assert_called_once()
