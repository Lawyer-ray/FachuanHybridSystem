from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from apps.core.exceptions import AuthenticationError, ExternalServiceError, ValidationException
from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient


def _make_client(**overrides):

    defaults = dict(
        provider_name="test_provider",
        transport="streamable_http",
        base_url="http://example.com/api",
        sse_url="http://example.com/sse",
        api_key="test_key",
    )
    defaults.update(overrides)
    return McpToolClient(**defaults)


# ── __init__ ──────────────────────────────────────────────────────────────────


class TestMcpToolClientInit:

    def test_defaults_applied(self):
        client = _make_client(api_key="k1", api_keys=None)
        assert client._api_key == "k1"
        assert client._transport == "streamable_http"
        assert client._timeout_seconds >= 5

    def test_empty_api_keys_falls_back_to_api_key(self):
        client = _make_client(api_key="fallback", api_keys=[])
        assert client._api_key == "fallback"

    def test_api_keys_takes_priority(self):
        client = _make_client(api_key="ignored", api_keys=["real1", "real2"])
        assert client._api_key == "real1"

    def test_empty_api_key_and_empty_keys(self):
        client = _make_client(api_key="", api_keys=[])
        assert client._api_key == ""

    def test_transport_strips_and_lowercases(self):
        client = _make_client(transport="  SSE  ")
        assert client._transport == "sse"

    def test_empty_transport_defaults_to_streamable_http(self):
        client = _make_client(transport="")
        assert client._transport == "streamable_http"

    def test_timeout_clamped_minimum(self):
        client = _make_client(timeout_seconds=1)
        assert client._timeout_seconds == 5

    def test_retry_max_attempts_clamped(self):
        client = _make_client(retry_max_attempts=0)
        assert client._retry_max_attempts == 1
        client2 = _make_client(retry_max_attempts=100)
        assert client2._retry_max_attempts == 5

    def test_retry_backoff_clamped(self):
        client = _make_client(retry_backoff_seconds=-1)
        assert client._retry_backoff_seconds == 0.0
        client2 = _make_client(retry_backoff_seconds=999)
        assert client2._retry_backoff_seconds == 5.0

    def test_rate_limit_clamped_minimum(self):
        client = _make_client(rate_limit_requests=0)
        assert client._rate_limit_requests == 1


# ── _headers ──────────────────────────────────────────────────────────────────


class TestMcpToolClientHeaders:

    def test_streamable_http_lowercase_bearer(self):
        client = _make_client(transport="streamable_http")
        h = client._headers(transport="streamable_http", api_key="abc123")
        assert h == {"Authorization": "bearer abc123"}

    def test_sse_capitalized_bearer(self):
        client = _make_client(transport="sse")
        h = client._headers(transport="sse", api_key="abc123")
        assert h == {"Authorization": "Bearer abc123"}

    def test_api_key_from_instance_when_empty(self):
        client = _make_client(api_key="instance_key")
        h = client._headers(transport="sse", api_key="")
        assert "instance_key" in h["Authorization"]


# ── _transport_attempts ───────────────────────────────────────────────────────


class TestTransportAttempts:

    def test_sse_single_attempt(self):
        client = _make_client(transport="sse")
        attempts = client._transport_attempts()
        assert attempts == ["sse"]

    def test_streamable_http_with_sse_url_two_attempts(self):
        client = _make_client(transport="streamable_http", sse_url="http://sse.example.com")
        with patch.object(client, "_is_transport_unhealthy", return_value=False):
            attempts = client._transport_attempts()
            assert attempts == ["streamable_http", "sse"]

    def test_streamable_http_without_sse_url_single(self):
        client = _make_client(transport="streamable_http", sse_url="")
        attempts = client._transport_attempts()
        assert attempts == ["streamable_http"]

    def test_streamable_http_unhealthy_skips_to_sse(self):
        client = _make_client(transport="streamable_http", sse_url="http://sse.example.com")
        with patch.object(client, "_is_transport_unhealthy", return_value=True):
            attempts = client._transport_attempts()
            assert attempts == ["sse"]


# ── _transport_unhealthy_cache_key ────────────────────────────────────────────


class TestTransportUnhealthyCacheKey:

    def test_key_contains_provider_and_transport(self):
        client = _make_client(provider_name="tianyancha")
        key = client._transport_unhealthy_cache_key("streamable_http")
        assert "tianyancha" in key
        assert "streamable_http" in key
        assert key.startswith("enterprise_data:transport_unhealthy:")


# ── _should_quarantine_transport ──────────────────────────────────────────────


class TestShouldQuarantineTransport:

    def test_quarantine_streamable_http(self):
        client = _make_client()
        assert client._should_quarantine_transport(transport="streamable_http", exc=Exception("x")) is True

    def test_no_quarantine_sse(self):
        client = _make_client()
        assert client._should_quarantine_transport(transport="sse", exc=Exception("x")) is False


# ── _serialize_content_item ──────────────────────────────────────────────────


class TestSerializeContentItem:

    def test_model_dump_object(self):
        item = MagicMock()
        item.model_dump.return_value = {"type": "text", "value": "hello"}
        result = McpToolClient._serialize_content_item(item)
        item.model_dump.assert_called_once()
        assert result == {"type": "text", "value": "hello"}

    def test_plain_value(self):
        result = McpToolClient._serialize_content_item(42)
        assert result == {"value": "42"}

    def test_plain_string(self):
        result = McpToolClient._serialize_content_item("hello")
        assert result == {"value": "hello"}


# ── _extract_payload ──────────────────────────────────────────────────────────


class TestExtractPayload:

    def test_structured_content_priority(self):
        client = _make_client()
        result = MagicMock()
        result.structuredContent = {"key": "value"}
        result.content = []
        assert client._extract_payload(result) == {"key": "value"}

    def test_single_json_text_item(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient

        client = _make_client()
        text_item = MagicMock()
        text_item.type = "text"
        text_item.text = '{"foo": "bar"}'
        result = MagicMock()
        result.structuredContent = None
        result.content = [text_item]
        assert client._extract_payload(result) == {"foo": "bar"}

    def test_multiple_json_text_items(self):
        client = _make_client()
        items = []
        for val in ["1", "2"]:
            item = MagicMock()
            item.type = "text"
            item.text = val
            items.append(item)
        result = MagicMock()
        result.structuredContent = None
        result.content = items
        assert client._extract_payload(result) == [1, 2]

    def test_single_plain_text(self):
        client = _make_client()
        item = MagicMock()
        item.type = "text"
        item.text = "not json"
        result = MagicMock()
        result.structuredContent = None
        result.content = [item]
        assert client._extract_payload(result) == "not json"

    def test_multiple_plain_text(self):
        client = _make_client()
        items = []
        for val in ["a", "b"]:
            item = MagicMock()
            item.type = "text"
            item.text = val
            items.append(item)
        result = MagicMock()
        result.structuredContent = None
        result.content = items
        assert client._extract_payload(result) == ["a", "b"]

    def test_empty_text_skipped(self):
        client = _make_client()
        item = MagicMock()
        item.type = "text"
        item.text = ""
        item.model_dump.return_value = {"type": "image"}
        result = MagicMock()
        result.structuredContent = None
        result.content = [item]
        out = client._extract_payload(result)
        assert isinstance(out, list)

    def test_non_text_item_fallback(self):
        client = _make_client()
        item = MagicMock()
        item.type = "image"
        item.text = None
        item.model_dump.return_value = {"type": "image", "url": "http://img.png"}
        result = MagicMock()
        result.structuredContent = None
        result.content = [item]
        out = client._extract_payload(result)
        assert isinstance(out, list)


# ── _try_parse_json ──────────────────────────────────────────────────────────


class TestTryParseJson:

    def test_valid_json(self):
        assert McpToolClient._try_parse_json('{"a": 1}') == {"a": 1}

    def test_invalid_json_returns_none(self):
        assert McpToolClient._try_parse_json("not json") is None

    def test_empty_string_returns_none(self):
        assert McpToolClient._try_parse_json("") is None

    def test_integer_string(self):
        assert McpToolClient._try_parse_json("42") == 42


# ── _contains_auth_token ─────────────────────────────────────────────────────


class TestContainsAuthToken:

    def test_detects_auth_error(self):
        assert McpToolClient._contains_auth_token("Authentication failed") is True

    def test_detects_unauthorized(self):
        assert McpToolClient._contains_auth_token("unauthorized access") is True

    def test_detects_invalid_api_key(self):
        assert McpToolClient._contains_auth_token("invalid api key") is True

    def test_detects_token(self):
        assert McpToolClient._contains_auth_token("token expired") is True

    def test_no_auth_keyword(self):
        assert McpToolClient._contains_auth_token("something else") is False

    def test_empty_string(self):
        assert McpToolClient._contains_auth_token("") is False

    def test_none_input(self):
        assert McpToolClient._contains_auth_token(None) is False  # type: ignore[arg-type]


# ── _flatten_error_payload_text ──────────────────────────────────────────────


class TestFlattenErrorPayloadText:

    def test_simple_dict(self):
        result = McpToolClient._flatten_error_payload_text({"error": "bad"})
        assert "error" in result
        assert "bad" in result

    def test_nested_dict(self):
        result = McpToolClient._flatten_error_payload_text({"a": {"b": "c"}})
        assert "a" in result
        assert "b" in result
        assert "c" in result

    def test_list_values(self):
        result = McpToolClient._flatten_error_payload_text([1, "two", True])
        assert "1" in result
        assert "two" in result
        assert "true" in result

    def test_none_input(self):
        assert McpToolClient._flatten_error_payload_text(None) == ""

    def test_scalar_input(self):
        assert "hello" in McpToolClient._flatten_error_payload_text("hello")

    def test_empty_dict(self):
        assert McpToolClient._flatten_error_payload_text({}) == ""


# ── _is_auth_like_http_error ─────────────────────────────────────────────────


class TestIsAuthLikeHttpError:

    def test_401_is_auth(self):
        response = MagicMock()
        response.status_code = 401
        response.text = ""
        response.json.side_effect = ValueError
        error = httpx.HTTPStatusError("auth", request=MagicMock(), response=response)
        assert McpToolClient._is_auth_like_http_error(error) is True

    def test_403_is_auth(self):
        response = MagicMock()
        response.status_code = 403
        response.text = ""
        response.json.side_effect = ValueError
        error = httpx.HTTPStatusError("forbidden", request=MagicMock(), response=response)
        assert McpToolClient._is_auth_like_http_error(error) is True

    def test_text_contains_auth_token(self):
        response = MagicMock()
        response.status_code = 400
        response.text = "invalid api key provided"
        response.json.side_effect = ValueError
        error = httpx.HTTPStatusError("bad", request=MagicMock(), response=response)
        assert McpToolClient._is_auth_like_http_error(error) is True

    def test_json_body_contains_auth_token(self):
        response = MagicMock()
        response.status_code = 400
        response.text = ""
        response.json.return_value = {"error": {"message": "unauthorized"}}
        error = httpx.HTTPStatusError("bad", request=MagicMock(), response=response)
        assert McpToolClient._is_auth_like_http_error(error) is True

    def test_not_auth(self):
        response = MagicMock()
        response.status_code = 500
        response.text = "server error"
        response.json.side_effect = ValueError
        error = httpx.HTTPStatusError("err", request=MagicMock(), response=response)
        assert McpToolClient._is_auth_like_http_error(error) is False

    def test_json_body_no_auth(self):
        response = MagicMock()
        response.status_code = 400
        response.text = "bad request"
        response.json.return_value = {"error": "bad format"}
        error = httpx.HTTPStatusError("bad", request=MagicMock(), response=response)
        assert McpToolClient._is_auth_like_http_error(error) is False

    def test_no_response_attr(self):
        response = MagicMock()
        response.status_code = 400
        response.text = "ok"
        response.json.side_effect = ValueError
        error = httpx.HTTPStatusError("x", request=MagicMock(), response=response)
        assert McpToolClient._is_auth_like_http_error(error) is False


# ── _collect_related_exceptions ──────────────────────────────────────────────


class TestCollectRelatedExceptions:

    def test_single_exception(self):
        exc = ValueError("test")
        result = McpToolClient._collect_related_exceptions(exc)
        assert exc in result
        assert len(result) == 1

    def test_cause_chain(self):
        cause = ValueError("cause")
        wrapper = RuntimeError("wrapper")
        wrapper.__cause__ = cause
        result = McpToolClient._collect_related_exceptions(wrapper)
        assert cause in result
        assert wrapper in result

    def test_context_chain(self):
        ctx = ValueError("ctx")
        wrapper = RuntimeError("wrapper")
        wrapper.__context__ = ctx
        result = McpToolClient._collect_related_exceptions(wrapper)
        assert ctx in result
        assert wrapper in result

    def test_no_duplicates(self):
        exc = ValueError("test")
        exc.__cause__ = exc
        result = McpToolClient._collect_related_exceptions(exc)
        assert result.count(exc) == 1


# ── _execute_with_api_key_failover ──────────────────────────────────────────


class TestExecuteWithApiKeyFailover:

    def test_no_api_keys_raises(self):
        client = _make_client(api_key="", api_keys=[])
        with pytest.raises(ExternalServiceError, match="API Key 未配置"):
            client._execute_with_api_key_failover(
                action="test",
                operation=lambda key, transport: "ok",
            )

    def test_success_on_first_key(self):
        client = _make_client(api_key="good_key")
        with patch.object(client._api_key_pool, "ordered_keys", return_value=["good_key"]):
            with patch.object(client, "_is_transport_unhealthy", return_value=False):
                result, meta = client._execute_with_api_key_failover(
                    action="test",
                    operation=lambda key, transport: "result_value",
                )
                assert result == "result_value"

    def test_auth_error_switches_key(self):
        client = _make_client(api_key="bad", api_keys=["bad", "good"], transport="sse", sse_url="")
        call_count = {"n": 0}

        def op(key, transport):
            call_count["n"] += 1
            if key == "bad":
                raise AuthenticationError("auth fail")
            return "success"

        with patch.object(client._api_key_pool, "ordered_keys", return_value=["bad", "good"]):
            result, meta = client._execute_with_api_key_failover(
                action="test",
                operation=op,
            )
            assert result == "success"
            assert meta["api_key_switched"] is True
            assert call_count["n"] == 2

    def test_last_error_raises_after_all_keys_exhausted(self):
        client = _make_client(api_key="bad", transport="sse", sse_url="")
        with patch.object(client._api_key_pool, "ordered_keys", return_value=["bad"]):
            with pytest.raises((ExternalServiceError, AuthenticationError)):
                client._execute_with_api_key_failover(
                    action="test",
                    operation=lambda k, t: (_ for _ in ()).throw(
                        ExternalServiceError("transport fail", code="ERR")
                    ),
                )


# ── _run_transport_attempts ──────────────────────────────────────────────────


class TestRunTransportAttempts:

    def test_success_first_attempt(self):
        client = _make_client(transport="sse")
        result, transport, count, err = client._run_transport_attempts(
            action="test",
            operation=lambda k, t: "ok",
            api_key="key",
        )
        assert result == "ok"
        assert transport == "sse"
        assert count == 1
        assert err is None

    def test_retry_on_timeout(self):
        client = _make_client(transport="sse", retry_max_attempts=2, retry_backoff_seconds=0)
        call_count = {"n": 0}

        def op(k, t):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise httpx.TimeoutException("timeout")
            return "ok"

        with patch.object(client, "_should_retry", return_value=True):
            result, transport, count, err = client._run_transport_attempts(
                action="test",
                operation=op,
                api_key="key",
            )
            assert result == "ok"
            assert count == 2

    def test_fallback_to_sse(self):
        client = _make_client(transport="streamable_http", sse_url="http://sse")
        call_count = {"n": 0}

        def op(k, t):
            call_count["n"] += 1
            if t == "streamable_http":
                raise ValueError("streamable failed")
            return "sse_result"

        with patch.object(client, "_should_retry", return_value=False):
            with patch.object(client, "_mark_transport_unhealthy"):
                result, transport, count, err = client._run_transport_attempts(
                    action="test",
                    operation=op,
                    api_key="key",
                )
                assert result == "sse_result"
                assert transport == "sse"

    def test_all_attempts_fail_returns_error(self):
        client = _make_client(transport="sse", retry_max_attempts=1)
        with patch.object(client, "_should_retry", return_value=False):
            result, transport, count, err = client._run_transport_attempts(
                action="test",
                operation=lambda k, t: (_ for _ in ()).throw(ValueError("fail")),
                api_key="key",
            )
            assert result is None
            assert isinstance(err, ValueError)


# ── list_tools / describe_tools ──────────────────────────────────────────────


class TestListToolsAndDescribe:

    def test_list_tools_returns_names(self):
        client = _make_client()
        with patch.object(client, "describe_tools", return_value=[{"name": "tool_a"}, {"name": "tool_b"}, {"name": ""}]):
            assert client.list_tools() == ["tool_a", "tool_b"]

    def test_list_tools_empty(self):
        client = _make_client()
        with patch.object(client, "describe_tools", return_value=[]):
            assert client.list_tools() == []


# ── _describe_tools_async ────────────────────────────────────────────────────


class _FakeAsyncContextManager:
    """Fake async context manager for mocking _open_session."""
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


class TestDescribeToolsAsync:

    @pytest.mark.asyncio
    async def test_extracts_tools_with_input_schema(self):
        client = _make_client()
        tool_obj = SimpleNamespace(
            name="tool1",
            description="desc",
            inputSchema={"type": "object"},
            input_schema=None,
        )
        list_result = SimpleNamespace(tools=[tool_obj])

        mock_session = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=list_result)

        with patch.object(client, "_open_session", return_value=_FakeAsyncContextManager(mock_session)):
            result = await client._describe_tools_async(transport="sse", api_key="key")
            assert len(result) == 1
            assert result[0]["name"] == "tool1"
            assert result[0]["input_schema"] == {"type": "object"}

    @pytest.mark.asyncio
    async def test_skips_empty_name(self):
        client = _make_client()
        tool_obj = SimpleNamespace(name="", description="desc", inputSchema=None, input_schema=None)
        list_result = SimpleNamespace(tools=[tool_obj])
        mock_session = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=list_result)

        with patch.object(client, "_open_session", return_value=_FakeAsyncContextManager(mock_session)):
            result = await client._describe_tools_async(transport="sse", api_key="key")
            assert result == []

    @pytest.mark.asyncio
    async def test_fallback_to_input_schema_attr(self):
        client = _make_client()
        tool_obj = SimpleNamespace(name="t", description="d", inputSchema=None)
        tool_obj.input_schema = {"type": "string"}
        list_result = SimpleNamespace(tools=[tool_obj])
        mock_session = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=list_result)

        with patch.object(client, "_open_session", return_value=_FakeAsyncContextManager(mock_session)):
            result = await client._describe_tools_async(transport="sse", api_key="key")
            assert result[0]["input_schema"] == {"type": "string"}


# ── _call_tool_async ─────────────────────────────────────────────────────────


class TestCallToolAsync:

    @pytest.mark.asyncio
    async def test_returns_payload_and_raw(self):
        client = _make_client()
        text_item = MagicMock()
        text_item.type = "text"
        text_item.text = '{"result": "ok"}'
        text_item.model_dump.return_value = {"type": "text", "text": '{"result": "ok"}'}

        tool_result = MagicMock()
        tool_result.isError = False
        tool_result.structuredContent = None
        tool_result.content = [text_item]

        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=tool_result)

        with patch.object(client, "_open_session", return_value=_FakeAsyncContextManager(mock_session)):
            result = await client._call_tool_async(
                transport="sse", tool_name="test_tool", arguments={"a": 1}, api_key="key"
            )
            assert result["payload"] == {"result": "ok"}
            assert result["raw"]["is_error"] is False


# ── call_tool ─────────────────────────────────────────────────────────────────


class TestCallTool:

    def test_call_tool_success(self):
        client = _make_client()
        fake_result = {
            "payload": {"data": 1},
            "raw": {"is_error": False, "structured_content": None, "content": []},
        }
        with patch.object(client, "_acquire_rate_limit"):
            with patch.object(
                client, "_execute_with_api_key_failover", return_value=(fake_result, {"transport": "sse"})
            ):
                result = client.call_tool(tool_name="tool1", arguments={"x": 1})
                assert result["payload"] == {"data": 1}
                assert "duration_ms" in result
                assert result["transport"] == "sse"
                assert result["fallback_used"] is True

    def test_call_tool_is_error_raises(self):
        client = _make_client()
        fake_result = {
            "payload": {"err": True},
            "raw": {"is_error": True, "structured_content": None, "content": []},
        }
        with patch.object(client, "_acquire_rate_limit"):
            with patch.object(
                client, "_execute_with_api_key_failover", return_value=(fake_result, {"transport": "sse"})
            ):
                with pytest.raises(ValidationException, match="工具调用返回错误"):
                    client.call_tool(tool_name="tool1", arguments={})

    def test_call_tool_no_fallback(self):
        client = _make_client(transport="sse")
        fake_result = {
            "payload": {},
            "raw": {"is_error": False, "structured_content": None, "content": []},
        }
        with patch.object(client, "_acquire_rate_limit"):
            with patch.object(
                client, "_execute_with_api_key_failover", return_value=(fake_result, {"transport": "sse"})
            ):
                result = client.call_tool(tool_name="t", arguments={})
                assert result["fallback_used"] is False


# ── list_tools (via describe_tools) ──────────────────────────────────────────


class TestListToolsIntegration:

    def test_list_tools_filters_empty_names(self):
        client = _make_client()
        with patch.object(client, "describe_tools", return_value=[{"name": "a"}, {"name": ""}, {"name": "b"}]):
            result = client.list_tools()
            assert result == ["a", "b"]
