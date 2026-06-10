"""MCP tool client tests with mocked HTTP."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import AuthenticationError, ExternalServiceError, ValidationException
from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient


def _make_client(**kwargs):
    return McpToolClient(
        provider_name=kwargs.get("provider_name", "test-provider"),
        transport=kwargs.get("transport", "streamable_http"),
        base_url=kwargs.get("base_url", "https://mcp.example.com/mcp"),
        sse_url=kwargs.get("sse_url", "https://mcp.example.com/sse"),
        api_key=kwargs.get("api_key", "test-key-123"),
        api_keys=kwargs.get("api_keys", None),
        timeout_seconds=kwargs.get("timeout_seconds", 10),
        rate_limit_requests=kwargs.get("rate_limit_requests", 100),
        rate_limit_window_seconds=kwargs.get("rate_limit_window_seconds", 60),
        retry_max_attempts=kwargs.get("retry_max_attempts", 1),
        retry_backoff_seconds=kwargs.get("retry_backoff_seconds", 0.0),
    )


class TestMcpToolClientInit:
    def test_init_defaults(self):
        client = _make_client()
        assert client._provider_name == "test-provider"
        assert client._transport == "streamable_http"

    def test_init_with_api_keys(self):
        client = _make_client(api_keys=["key1", "key2", "key3"])
        assert client._api_key == "key1"

    def test_init_empty_api_key_fallback(self):
        client = McpToolClient(
            provider_name="test", transport="sse", base_url="", sse_url="",
            api_key="", api_keys=None,
        )
        assert client._api_key == ""


class TestMcpToolClientHelpers:
    def test_headers_streamable_http(self):
        client = _make_client(transport="streamable_http")
        headers = client._headers(transport="streamable_http", api_key="mykey")
        assert "bearer mykey" in headers["Authorization"]

    def test_headers_sse(self):
        client = _make_client(transport="sse")
        headers = client._headers(transport="sse", api_key="mykey")
        assert "Bearer mykey" in headers["Authorization"]

    def test_transport_attempts_primary(self):
        client = _make_client(transport="sse", sse_url="")
        attempts = client._transport_attempts()
        assert attempts == ["sse"]

    def test_try_parse_json_valid(self):
        assert McpToolClient._try_parse_json('{"key": "value"}') == {"key": "value"}

    def test_try_parse_json_invalid(self):
        assert McpToolClient._try_parse_json("not json") is None

    def test_serialize_content_item_with_model_dump(self):
        item = MagicMock()
        item.model_dump.return_value = {"type": "text", "value": "hello"}
        result = McpToolClient._serialize_content_item(item)
        assert result == {"type": "text", "value": "hello"}

    def test_serialize_content_item_without_model_dump(self):
        item = "plain text"
        result = McpToolClient._serialize_content_item(item)
        assert "value" in result


class TestMcpToolClientExtractPayload:
    def test_extract_payload_structured(self):
        client = _make_client()
        result = MagicMock()
        result.structuredContent = {"data": "value"}
        result.content = []
        payload = client._extract_payload(result)
        assert payload == {"data": "value"}

    def test_extract_payload_text_json(self):
        client = _make_client()
        text_item = MagicMock()
        text_item.type = "text"
        text_item.text = '{"result": "ok"}'
        result = MagicMock()
        result.structuredContent = None
        result.content = [text_item]
        payload = client._extract_payload(result)
        assert payload == {"result": "ok"}

    def test_extract_payload_text_plain(self):
        client = _make_client()
        text_item = MagicMock()
        text_item.type = "text"
        text_item.text = "plain result"
        result = MagicMock()
        result.structuredContent = None
        result.content = [text_item]
        payload = client._extract_payload(result)
        assert payload == "plain result"


class TestMcpToolClientRetry:
    def test_should_retry_timeout(self):
        import httpx

        client = _make_client()
        exc = httpx.TimeoutException("timeout")
        assert client._should_retry(exc) is True

    def test_should_retry_connect_error(self):
        import httpx

        client = _make_client()
        exc = httpx.ConnectError("connection refused")
        assert client._should_retry(exc) is True

    def test_should_not_retry_validation(self):
        client = _make_client()
        exc = ValidationException(message="bad input")
        assert client._should_retry(exc) is False

    def test_should_not_retry_auth(self):
        client = _make_client()
        exc = AuthenticationError(message="unauthorized")
        assert client._should_retry(exc) is False


class TestMcpToolClientApiKeySwitch:
    def test_should_switch_api_key_auth_error(self):
        client = _make_client()
        exc = AuthenticationError(message="unauthorized")
        assert client._should_switch_api_key(exc) is True

    def test_should_not_switch_api_key_timeout(self):
        import httpx

        client = _make_client()
        exc = httpx.TimeoutException("timeout")
        assert client._should_switch_api_key(exc) is False


class TestMcpToolClientAuthDetection:
    def test_contains_auth_token(self):
        assert McpToolClient._contains_auth_token("authentication error") is True
        assert McpToolClient._contains_auth_token("invalid api key") is True
        assert McpToolClient._contains_auth_token("normal error") is False

    def test_is_auth_like_http_error_401(self):
        import httpx

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = ""
        mock_resp.json.side_effect = ValueError
        exc = httpx.HTTPStatusError("unauthorized", request=MagicMock(), response=mock_resp)
        assert McpToolClient._is_auth_like_http_error(exc) is True

    def test_flatten_error_payload_text(self):
        result = McpToolClient._flatten_error_payload_text({"error": {"code": 401, "message": "unauthorized"}})
        assert "unauthorized" in result
        assert "401" in result

    def test_collect_related_exceptions(self):
        inner = ValueError("inner")
        outer = RuntimeError("outer")
        outer.__cause__ = inner
        collected = McpToolClient._collect_related_exceptions(outer)
        assert len(collected) >= 2


class TestMcpToolClientRateLimit:
    @patch("apps.enterprise_data.services.clients.mcp_tool_client.cache")
    def test_acquire_rate_limit_within_limit(self, mock_cache):
        mock_cache.add.return_value = True
        mock_cache.incr.return_value = 1
        client = _make_client(rate_limit_requests=10)
        client._acquire_rate_limit(action="test")  # Should not raise

    @patch("apps.enterprise_data.services.clients.mcp_tool_client.cache")
    def test_acquire_rate_limit_exceeded(self, mock_cache):
        mock_cache.add.return_value = False
        mock_cache.incr.return_value = 100
        client = _make_client(rate_limit_requests=10)
        with pytest.raises(ValidationException, match="频率过高"):
            client._acquire_rate_limit(action="test")


class TestMcpToolClientTransportHealth:
    @patch("apps.enterprise_data.services.clients.mcp_tool_client.cache")
    def test_mark_transport_unhealthy(self, mock_cache):
        client = _make_client()
        exc = Exception("test")
        client._mark_transport_unhealthy(transport="streamable_http", exc=exc)
        mock_cache.set.assert_called_once()

    @patch("apps.enterprise_data.services.clients.mcp_tool_client.cache")
    def test_clear_transport_unhealthy(self, mock_cache):
        client = _make_client()
        client._clear_transport_unhealthy("streamable_http")
        mock_cache.delete.assert_called_once()

    @patch("apps.enterprise_data.services.clients.mcp_tool_client.cache")
    def test_is_transport_unhealthy(self, mock_cache):
        mock_cache.get.return_value = True
        client = _make_client()
        assert client._is_transport_unhealthy("streamable_http") is True

    def test_should_quarantine_only_streamable(self):
        client = _make_client()
        assert client._should_quarantine_transport(transport="streamable_http", exc=Exception()) is True
        assert client._should_quarantine_transport(transport="sse", exc=Exception()) is False
