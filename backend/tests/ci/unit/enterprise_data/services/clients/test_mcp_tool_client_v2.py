"""Tests for McpToolClient."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import httpx
import pytest

from apps.core.exceptions import AuthenticationError, ExternalServiceError, ValidationException
from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(**overrides: Any) -> McpToolClient:
    defaults: dict[str, Any] = {
        "provider_name": "test_provider",
        "transport": "streamable_http",
        "base_url": "https://api.example.com/mcp",
        "sse_url": "https://api.example.com/sse",
        "api_key": "test-key-123",
    }
    defaults.update(overrides)
    with patch("apps.enterprise_data.services.clients.mcp_tool_client.McpApiKeyPool"):
        return McpToolClient(**defaults)


# ===========================================================================
# Init tests
# ===========================================================================


class TestInit:
    def test_default_transport_normalised(self) -> None:
        client = _make_client(transport="  Streamable_HTTP  ")
        assert client._transport == "streamable_http"

    def test_empty_transport_defaults_to_streamable(self) -> None:
        client = _make_client(transport="")
        assert client._transport == "streamable_http"

    def test_timeout_min_5(self) -> None:
        client = _make_client(timeout_seconds=1)
        assert client._timeout_seconds == 5

    def test_rate_limit_min_1(self) -> None:
        client = _make_client(rate_limit_requests=0)
        assert client._rate_limit_requests == 1

    def test_retry_max_clamped_to_5(self) -> None:
        client = _make_client(retry_max_attempts=10)
        assert client._retry_max_attempts == 5

    def test_retry_backoff_clamped_to_5(self) -> None:
        client = _make_client(retry_backoff_seconds=10.0)
        assert client._retry_backoff_seconds == 5.0

    def test_api_key_from_pool(self) -> None:
        with patch("apps.enterprise_data.services.clients.mcp_tool_client.McpApiKeyPool") as MockPool:
            client = McpToolClient(
                provider_name="p",
                transport="sse",
                base_url="http://x",
                sse_url="http://x/sse",
                api_key="",
                api_keys=["key-a", "key-b"],
            )
            MockPool.assert_called_once_with(provider_name="p", api_keys=["key-a", "key-b"])
            assert client._api_key == "key-a"

    def test_api_key_fallback_from_single_key(self) -> None:
        client = _make_client(api_key="single-key")  # allowlist secret
        assert client._api_key == "single-key"


# ===========================================================================
# Headers
# ===========================================================================


class TestHeaders:
    def test_streamable_http_uses_lowercase_bearer(self) -> None:
        client = _make_client(transport="streamable_http")
        headers = client._headers(transport="streamable_http", api_key="k")
        assert headers["Authorization"] == "bearer k"

    def test_sse_uses_standard_bearer(self) -> None:
        client = _make_client(transport="sse")
        headers = client._headers(transport="sse", api_key="k")
        assert headers["Authorization"] == "Bearer k"

    def test_fallback_to_instance_key(self) -> None:
        client = _make_client(api_key="inst-key")  # allowlist secret
        headers = client._headers(transport="sse", api_key="")
        assert "inst-key" in headers["Authorization"]


# ===========================================================================
# Transport attempts
# ===========================================================================


class TestTransportAttempts:
    def test_streamable_always_has_sse_fallback(self) -> None:
        client = _make_client(transport="streamable_http", sse_url="https://x/sse")
        with patch.object(client, "_is_transport_unhealthy", return_value=False):
            attempts = client._transport_attempts()
        assert attempts == ["streamable_http", "sse"]

    def test_streamable_unhealthy_skips_to_sse(self) -> None:
        client = _make_client(transport="streamable_http", sse_url="https://x/sse")
        with patch.object(client, "_is_transport_unhealthy", return_value=True):
            attempts = client._transport_attempts()
        assert attempts == ["sse"]

    def test_sse_only(self) -> None:
        client = _make_client(transport="sse")
        attempts = client._transport_attempts()
        assert attempts == ["sse"]

    def test_streamable_no_sse_url(self) -> None:
        client = _make_client(transport="streamable_http", sse_url="")
        with patch.object(client, "_is_transport_unhealthy", return_value=False):
            attempts = client._transport_attempts()
        assert attempts == ["streamable_http"]


# ===========================================================================
# Should retry
# ===========================================================================


class TestShouldRetry:
    def test_timeout_is_retryable(self) -> None:
        client = _make_client()
        assert client._should_retry(httpx.TimeoutException("t")) is True

    def test_connect_error_is_retryable(self) -> None:
        client = _make_client()
        assert client._should_retry(httpx.ConnectError("c")) is True

    def test_validation_exception_not_retryable(self) -> None:
        client = _make_client()
        assert client._should_retry(ValidationException("v")) is False

    def test_auth_error_not_retryable(self) -> None:
        client = _make_client()
        assert client._should_retry(AuthenticationError("a")) is False

    def test_http_429_not_retryable(self) -> None:
        client = _make_client()
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 429
        exc = httpx.HTTPStatusError("429", request=MagicMock(), response=resp)
        assert client._should_retry(exc) is False

    def test_http_500_retryable(self) -> None:
        client = _make_client()
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 500
        exc = httpx.HTTPStatusError("500", request=MagicMock(), response=resp)
        assert client._should_retry(exc) is True

    def test_http_400_not_retryable(self) -> None:
        client = _make_client()
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 400
        exc = httpx.HTTPStatusError("400", request=MagicMock(), response=resp)
        assert client._should_retry(exc) is False


# ===========================================================================
# Should switch API key
# ===========================================================================


class TestShouldSwitchApiKey:
    def test_auth_error_switches(self) -> None:
        client = _make_client()
        assert client._should_switch_api_key(AuthenticationError("a")) is True

    def test_http_401_switches(self) -> None:
        client = _make_client()
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 401
        exc = httpx.HTTPStatusError("401", request=MagicMock(), response=resp)
        assert client._should_switch_api_key(exc) is True

    def test_http_403_switches(self) -> None:
        client = _make_client()
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 403
        resp.text = ""
        resp.json.return_value = {}
        exc = httpx.HTTPStatusError("403", request=MagicMock(), response=resp)
        assert client._should_switch_api_key(exc) is True

    def test_http_429_switches(self) -> None:
        client = _make_client()
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 429
        exc = httpx.HTTPStatusError("429", request=MagicMock(), response=resp)
        assert client._should_switch_api_key(exc) is True

    def test_http_500_does_not_switch(self) -> None:
        client = _make_client()
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 500
        exc = httpx.HTTPStatusError("500", request=MagicMock(), response=resp)
        assert client._should_switch_api_key(exc) is False

    def test_external_service_error_429_switches(self) -> None:
        client = _make_client()
        exc = ExternalServiceError(message="e", code="MCP_HTTP_ERROR", errors={"status_code": 429})
        assert client._should_switch_api_key(exc) is True


# ===========================================================================
# Mark API key failure
# ===========================================================================


class TestMarkApiKeyFailure:
    def test_auth_error_marks_auth_failed(self) -> None:
        client = _make_client()
        client._api_key_pool = MagicMock()
        client._mark_api_key_failure(api_key="k", exc=AuthenticationError("a"))
        client._api_key_pool.mark_auth_failed.assert_called_once_with("k")

    def test_429_marks_rate_limited(self) -> None:
        client = _make_client()
        client._api_key_pool = MagicMock()
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 429
        exc = httpx.HTTPStatusError("429", request=MagicMock(), response=resp)
        client._mark_api_key_failure(api_key="k", exc=exc)
        client._api_key_pool.mark_rate_limited.assert_called_once_with("k")

    def test_empty_key_is_noop(self) -> None:
        client = _make_client()
        client._api_key_pool = MagicMock()
        client._mark_api_key_failure(api_key="", exc=AuthenticationError("a"))
        client._api_key_pool.mark_auth_failed.assert_not_called()


# ===========================================================================
# Extract payload
# ===========================================================================


class TestExtractPayload:
    def test_structured_content_preferred(self) -> None:
        client = _make_client()
        result = MagicMock()
        result.structuredContent = {"data": 42}
        result.content = []
        assert client._extract_payload(result) == {"data": 42}

    def test_single_json_text(self) -> None:
        client = _make_client()
        text_item = MagicMock()
        text_item.type = "text"
        text_item.text = '{"key": "val"}'
        result = MagicMock()
        result.structuredContent = None
        result.content = [text_item]
        payload = client._extract_payload(result)
        assert payload == {"key": "val"}

    def test_single_plain_text(self) -> None:
        client = _make_client()
        text_item = MagicMock()
        text_item.type = "text"
        text_item.text = "hello"
        result = MagicMock()
        result.structuredContent = None
        result.content = [text_item]
        payload = client._extract_payload(result)
        assert payload == "hello"

    def test_multiple_json_texts(self) -> None:
        client = _make_client()
        items = []
        for txt in ['"a"', '"b"']:
            item = MagicMock()
            item.type = "text"
            item.text = txt
            items.append(item)
        result = MagicMock()
        result.structuredContent = None
        result.content = items
        payload = client._extract_payload(result)
        assert payload == ["a", "b"]

    def test_empty_content_fallback(self) -> None:
        client = _make_client()
        result = MagicMock()
        result.structuredContent = None
        result.content = []
        payload = client._extract_payload(result)
        assert payload == []

    def test_non_text_items_serialised(self) -> None:
        client = _make_client()
        img_item = MagicMock(spec=[])  # no model_dump
        img_item.type = "image"
        img_item.text = "not-a-text"
        result = MagicMock()
        result.structuredContent = None
        result.content = [img_item]
        payload = client._extract_payload(result)
        assert isinstance(payload, list)


# ===========================================================================
# Try parse JSON
# ===========================================================================


class TestTryParseJson:
    def test_valid_json(self) -> None:
        assert McpToolClient._try_parse_json('{"a": 1}') == {"a": 1}

    def test_invalid_json(self) -> None:
        assert McpToolClient._try_parse_json("not json") is None

    def test_none_input(self) -> None:
        assert McpToolClient._try_parse_json(None) is None  # type: ignore[arg-type]


# ===========================================================================
# Serialize content item
# ===========================================================================


class TestSerializeContentItem:
    def test_model_dump(self) -> None:
        item = MagicMock()
        item.model_dump.return_value = {"type": "text", "text": "hi"}
        assert McpToolClient._serialize_content_item(item) == {"type": "text", "text": "hi"}

    def test_plain_object(self) -> None:
        item = "plain-string"
        assert McpToolClient._serialize_content_item(item) == {"value": "plain-string"}


# ===========================================================================
# Is auth-like HTTP error
# ===========================================================================


class TestIsAuthLikeHttpError:
    def test_401(self) -> None:
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 401
        exc = httpx.HTTPStatusError("401", request=MagicMock(), response=resp)
        assert McpToolClient._is_auth_like_http_error(exc) is True

    def test_403(self) -> None:
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 403
        resp.text = ""
        resp.json.return_value = {}
        exc = httpx.HTTPStatusError("403", request=MagicMock(), response=resp)
        assert McpToolClient._is_auth_like_http_error(exc) is True

    def test_400_with_auth_token_in_text(self) -> None:
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 400
        resp.text = '{"error": "invalid api key"}'
        resp.json.return_value = {"error": "invalid api key"}
        exc = httpx.HTTPStatusError("400", request=MagicMock(), response=resp)
        assert McpToolClient._is_auth_like_http_error(exc) is True

    def test_400_no_auth_signal(self) -> None:
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 400
        resp.text = '{"error": "bad request"}'
        resp.json.return_value = {"error": "bad request"}
        exc = httpx.HTTPStatusError("400", request=MagicMock(), response=resp)
        assert McpToolClient._is_auth_like_http_error(exc) is False


# ===========================================================================
# Contains auth token
# ===========================================================================


class TestContainsAuthToken:
    def test_known_tokens(self) -> None:
        assert McpToolClient._contains_auth_token("authentication error") is True
        assert McpToolClient._contains_auth_token("unauthorized access") is True
        assert McpToolClient._contains_auth_token("invalid api key") is True
        assert McpToolClient._contains_auth_token("token expired") is True

    def test_no_match(self) -> None:
        assert McpToolClient._contains_auth_token("connection timeout") is False
        assert McpToolClient._contains_auth_token("") is False


# ===========================================================================
# Flatten error payload text
# ===========================================================================


class TestFlattenErrorPayloadText:
    def test_nested_dict(self) -> None:
        payload = {"error": {"message": "Auth Error", "code": 401}}
        text = McpToolClient._flatten_error_payload_text(payload)
        assert "auth error" in text
        assert "401" in text

    def test_list(self) -> None:
        payload = [{"msg": "a"}, {"msg": "b"}]
        text = McpToolClient._flatten_error_payload_text(payload)
        assert "a" in text
        assert "b" in text

    def test_none_value(self) -> None:
        assert McpToolClient._flatten_error_payload_text(None) == ""


# ===========================================================================
# Collect related exceptions
# ===========================================================================


class TestCollectRelatedExceptions:
    def test_simple_exception(self) -> None:
        exc = ValueError("v")
        collected = McpToolClient._collect_related_exceptions(exc)
        assert exc in collected

    def test_cause_chain(self) -> None:
        inner = ValueError("inner")
        outer = RuntimeError("outer")
        outer.__cause__ = inner
        collected = McpToolClient._collect_related_exceptions(outer)
        assert inner in collected
        assert outer in collected

    def test_context_chain(self) -> None:
        ctx_exc = TypeError("ctx")
        main_exc = RuntimeError("main")
        main_exc.__context__ = ctx_exc
        collected = McpToolClient._collect_related_exceptions(main_exc)
        assert ctx_exc in collected

    def test_exception_group(self) -> None:
        e1 = ValueError("a")
        e2 = TypeError("b")
        group = ExceptionGroup("grp", [e1, e2])
        collected = McpToolClient._collect_related_exceptions(group)
        assert e1 in collected
        assert e2 in collected

    def test_no_duplicates(self) -> None:
        exc = RuntimeError("dup")
        exc.__cause__ = exc  # circular
        collected = McpToolClient._collect_related_exceptions(exc)
        assert collected.count(exc) == 1


# ===========================================================================
# Raise transport error
# ===========================================================================


class TestRaiseTransportError:
    def test_raises_validation_exception(self) -> None:
        client = _make_client()
        ve = ValidationException("v")
        with pytest.raises(ValidationException):
            client._raise_transport_error(action="test", exc=ve)

    def test_raises_authentication_error(self) -> None:
        client = _make_client()
        ae = AuthenticationError("a")
        with pytest.raises(AuthenticationError):
            client._raise_transport_error(action="test", exc=ae)

    def test_raises_external_service_error(self) -> None:
        client = _make_client()
        ese = ExternalServiceError(message="e", code="c")
        with pytest.raises(ExternalServiceError):
            client._raise_transport_error(action="test", exc=ese)

    def test_http_500_raises_external_service_error(self) -> None:
        client = _make_client()
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 500
        resp.text = ""
        resp.json.return_value = {}
        exc = httpx.HTTPStatusError("500", request=MagicMock(), response=resp)
        with pytest.raises(ExternalServiceError) as exc_info:
            client._raise_transport_error(action="test", exc=exc)
        assert exc_info.value.code == "MCP_HTTP_ERROR"

    def test_timeout_raises_external_service_error(self) -> None:
        client = _make_client()
        exc = httpx.TimeoutException("timeout")
        with pytest.raises(ExternalServiceError) as exc_info:
            client._raise_transport_error(action="test", exc=exc)
        assert exc_info.value.code == "MCP_TIMEOUT"

    def test_connect_error_raises_external_service_error(self) -> None:
        client = _make_client()
        exc = httpx.ConnectError("connect")
        with pytest.raises(ExternalServiceError) as exc_info:
            client._raise_transport_error(action="test", exc=exc)
        assert exc_info.value.code == "MCP_NETWORK_ERROR"

    def test_generic_exception_raises_transport_error(self) -> None:
        client = _make_client()
        exc = RuntimeError("unknown")
        with pytest.raises(ExternalServiceError) as exc_info:
            client._raise_transport_error(action="test", exc=exc)
        assert exc_info.value.code == "MCP_TRANSPORT_ERROR"

    def test_auth_http_error_raises_authentication(self) -> None:
        client = _make_client()
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 401
        resp.text = ""
        exc = httpx.HTTPStatusError("401", request=MagicMock(), response=resp)
        with pytest.raises(AuthenticationError):
            client._raise_transport_error(action="test", exc=exc)


# ===========================================================================
# Rate limit
# ===========================================================================


class TestAcquireRateLimit:
    def test_within_limit_passes(self) -> None:
        client = _make_client(rate_limit_requests=10, rate_limit_window_seconds=60)
        with patch("apps.enterprise_data.services.clients.mcp_tool_client.cache") as mock_cache:
            mock_cache.add.return_value = True
            mock_cache.incr.return_value = 1
            client._acquire_rate_limit(action="test")

    def test_over_limit_raises(self) -> None:
        client = _make_client(rate_limit_requests=5, rate_limit_window_seconds=60)
        with patch("apps.enterprise_data.services.clients.mcp_tool_client.cache") as mock_cache:
            mock_cache.add.return_value = False
            mock_cache.incr.return_value = 6
            with pytest.raises(ValidationException) as exc_info:
                client._acquire_rate_limit(action="test")
            assert exc_info.value.code == "MCP_RATE_LIMITED"

    def test_incr_value_error_in_else_branch(self) -> None:
        client = _make_client(rate_limit_requests=10, rate_limit_window_seconds=60)
        with patch("apps.enterprise_data.services.clients.mcp_tool_client.cache") as mock_cache:
            # add returns False → enters else branch; incr raises ValueError → handled
            mock_cache.add.return_value = False
            mock_cache.incr.side_effect = ValueError("key missing")
            client._acquire_rate_limit(action="test")
            mock_cache.set.assert_called_once()


# ===========================================================================
# Transport unhealthy cache
# ===========================================================================


class TestTransportUnhealthyCache:
    def test_cache_key_format(self) -> None:
        client = _make_client(base_url="https://api.example.com/mcp")
        key = client._transport_unhealthy_cache_key("streamable_http")
        assert "test_provider" in key
        assert "streamable_http" in key
        assert "enterprise_data:transport_unhealthy" in key

    def test_is_transport_unhealthy(self) -> None:
        client = _make_client()
        with patch("apps.enterprise_data.services.clients.mcp_tool_client.cache") as mock_cache:
            mock_cache.get.return_value = True
            assert client._is_transport_unhealthy("sse") is True
            mock_cache.get.return_value = None
            assert client._is_transport_unhealthy("sse") is False

    def test_clear_transport_unhealthy(self) -> None:
        client = _make_client()
        with patch("apps.enterprise_data.services.clients.mcp_tool_client.cache") as mock_cache:
            client._clear_transport_unhealthy("sse")
            mock_cache.delete.assert_called_once()

    def test_should_quarantine_only_streamable(self) -> None:
        client = _make_client()
        assert client._should_quarantine_transport(transport="streamable_http", exc=RuntimeError()) is True
        assert client._should_quarantine_transport(transport="sse", exc=RuntimeError()) is False


# ===========================================================================
# Call tool (integration-level with mocks)
# ===========================================================================


class TestCallTool:
    def test_success(self) -> None:
        client = _make_client()
        client._acquire_rate_limit = MagicMock()
        raw_result = {"payload": {"result": "ok"}, "raw": {"is_error": False, "structured_content": None, "content": []}}
        with patch.object(client, "_execute_with_api_key_failover", return_value=(raw_result, {"transport": "streamable_http", "attempt_count": 1, "api_key_pool_size": 1, "api_key_attempt_count": 1, "api_key_switched": False})):
            result = client.call_tool(tool_name="my_tool", arguments={"q": "test"})
        assert result["payload"] == {"result": "ok"}
        assert result["duration_ms"] >= 0

    def test_tool_error_raises(self) -> None:
        client = _make_client()
        client._acquire_rate_limit = MagicMock()
        raw_result = {"payload": {}, "raw": {"is_error": True, "structured_content": None, "content": []}}
        with patch.object(client, "_execute_with_api_key_failover", return_value=(raw_result, {})):
            with pytest.raises(ValidationException) as exc_info:
                client.call_tool(tool_name="bad_tool", arguments={})
            assert exc_info.value.code == "MCP_TOOL_ERROR"


# ===========================================================================
# List / Describe tools
# ===========================================================================


class TestListTools:
    def test_returns_names(self) -> None:
        client = _make_client()
        with patch.object(client, "describe_tools", return_value=[{"name": "t1"}, {"name": "t2"}, {"description": "no-name"}]):
            tools = client.list_tools()
        assert tools == ["t1", "t2"]


class TestDescribeTools:
    def test_delegates_to_async(self) -> None:
        client = _make_client()
        client._acquire_rate_limit = MagicMock()
        tools_data = [{"name": "x", "description": "d", "input_schema": {}}]
        with patch.object(client, "_execute_with_api_key_failover", return_value=(tools_data, {})):
            result = client.describe_tools()
        assert result == tools_data
