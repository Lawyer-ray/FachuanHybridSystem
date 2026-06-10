"""Tests for http_error_summary and httpx_errors - targeting uncovered branches."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from apps.core.llm.backends.http_error_summary import summarize_http_error_response, _first_str, _truncate
from apps.core.llm.backends.httpx_errors import HttpxErrorMixin
from apps.core.llm.exceptions import LLMNetworkError, LLMTimeoutError


class TestFirstStr:
    """Test _first_str helper."""

    def test_finds_first_matching_key(self):
        assert _first_str({"message": "err", "detail": "det"}, ["message", "detail"]) == "err"

    def test_skips_missing_keys(self):
        assert _first_str({"detail": "det"}, ["message", "detail"]) == "det"

    def test_skips_empty_values(self):
        assert _first_str({"message": "", "detail": "det"}, ["message", "detail"]) == "det"

    def test_skips_non_string_values(self):
        assert _first_str({"message": 123, "detail": "det"}, ["message", "detail"]) == "det"

    def test_no_match(self):
        assert _first_str({"foo": "bar"}, ["message", "detail"]) is None


class TestTruncate:
    """Test _truncate helper."""

    def test_short_string(self):
        assert _truncate("hello", 10) == "hello"

    def test_long_string(self):
        result = _truncate("a" * 100, 10)
        assert result == "a" * 10 + "..."

    def test_exact_length(self):
        assert _truncate("hello", 5) == "hello"


class TestSummarizeHttpErrorResponse:
    """Test summarize_http_error_response."""

    def test_basic_error(self):
        resp = MagicMock()
        resp.status_code = 500
        resp.headers = {}
        resp.json.return_value = {"error": {"message": "Internal Server Error", "code": "ERR_500"}}

        result = summarize_http_error_response(resp)
        assert result["status_code"] == 500
        assert result["upstream_error_message"] == "Internal Server Error"
        assert result["upstream_error_code"] == "ERR_500"

    def test_error_as_string(self):
        resp = MagicMock()
        resp.status_code = 400
        resp.headers = {}
        resp.json.return_value = {"error": "Bad Request"}

        result = summarize_http_error_response(resp)
        assert result["upstream_error_message"] == "Bad Request"

    def test_top_level_message(self):
        resp = MagicMock()
        resp.status_code = 400
        resp.headers = {}
        resp.json.return_value = {"message": "Something went wrong"}

        result = summarize_http_error_response(resp)
        assert result["upstream_error_message"] == "Something went wrong"

    def test_top_level_detail(self):
        resp = MagicMock()
        resp.status_code = 400
        resp.headers = {}
        resp.json.return_value = {"detail": "Not found"}

        result = summarize_http_error_response(resp)
        assert result["upstream_error_message"] == "Not found"

    def test_request_id_headers(self):
        resp = MagicMock()
        resp.status_code = 500
        resp.headers = {"x-request-id": "req-123"}
        resp.json.return_value = {"error": "err"}

        result = summarize_http_error_response(resp)
        assert result["upstream_request_id"] == "req-123"

    def test_x_trace_id(self):
        resp = MagicMock()
        resp.status_code = 500
        resp.headers = {"x-trace-id": "trace-456"}
        resp.json.return_value = {"error": "err"}

        result = summarize_http_error_response(resp)
        assert result["upstream_request_id"] == "trace-456"

    def test_content_type_header(self):
        resp = MagicMock()
        resp.status_code = 500
        resp.headers = {"content-type": "application/json"}
        resp.json.return_value = {"error": "err"}

        result = summarize_http_error_response(resp)
        assert result["content_type"] == "application/json"

    def test_json_decode_fallback_to_text(self):
        resp = MagicMock()
        resp.status_code = 500
        resp.headers = {}
        resp.json.side_effect = ValueError("invalid json")
        resp.text = "Server Error"

        result = summarize_http_error_response(resp)
        assert result["upstream_error_text"] == "Server Error"

    def test_json_decode_empty_text(self):
        resp = MagicMock()
        resp.status_code = 500
        resp.headers = {}
        resp.json.side_effect = ValueError("invalid json")
        resp.text = ""

        result = summarize_http_error_response(resp)
        assert "upstream_error_text" not in result

    def test_error_dict_with_detail_key(self):
        resp = MagicMock()
        resp.status_code = 400
        resp.headers = {}
        resp.json.return_value = {"error": {"detail": "Invalid input"}}

        result = summarize_http_error_response(resp)
        assert result["upstream_error_message"] == "Invalid input"

    def test_error_dict_with_type_key(self):
        resp = MagicMock()
        resp.status_code = 400
        resp.headers = {}
        resp.json.return_value = {"error": {"type": "validation_error", "message": "Bad"}}

        result = summarize_http_error_response(resp)
        assert result["upstream_error_code"] == "validation_error"


class TestHttpxErrorMixin:
    """Test HttpxErrorMixin."""

    def test_raise_connect_error(self):
        mixin = HttpxErrorMixin()
        error = httpx.ConnectError("Connection refused")

        with pytest.raises(LLMNetworkError) as exc_info:
            mixin.raise_connect_error(
                backend_name="Ollama",
                base_url="http://test:11434",
                error=error,
            )
        assert "Ollama" in str(exc_info.value)

    def test_raise_connect_error_with_custom_message(self):
        mixin = HttpxErrorMixin()
        error = httpx.ConnectError("Connection refused")

        with pytest.raises(LLMNetworkError) as exc_info:
            mixin.raise_connect_error(
                backend_name="Ollama",
                base_url="http://test:11434",
                error=error,
                message="Custom message",
            )
        assert "Custom message" in str(exc_info.value)

    def test_raise_timeout_error(self):
        mixin = HttpxErrorMixin()
        error = httpx.TimeoutException("Timeout")

        with pytest.raises(LLMTimeoutError) as exc_info:
            mixin.raise_timeout_error(
                backend_name="Ollama",
                timeout=30.0,
                error=error,
            )
        assert exc_info.value.timeout_seconds == 30.0

    def test_raise_timeout_error_with_custom_message(self):
        mixin = HttpxErrorMixin()
        error = httpx.TimeoutException("Timeout")

        with pytest.raises(LLMTimeoutError) as exc_info:
            mixin.raise_timeout_error(
                backend_name="Ollama",
                timeout=60.0,
                error=error,
                message="Custom timeout",
            )
        assert "Custom timeout" in str(exc_info.value)

    def test_raise_connect_error_with_custom_errors(self):
        mixin = HttpxErrorMixin()
        error = httpx.ConnectError("refused")
        custom_errors = {"detail": "custom", "base_url": "http://test"}

        with pytest.raises(LLMNetworkError) as exc_info:
            mixin.raise_connect_error(
                backend_name="Ollama",
                base_url="http://test",
                error=error,
                errors=custom_errors,
            )
        assert exc_info.value.errors == custom_errors

    def test_raise_timeout_error_with_custom_errors(self):
        mixin = HttpxErrorMixin()
        error = httpx.TimeoutException("timeout")
        custom_errors = {"detail": "custom timeout"}

        with pytest.raises(LLMTimeoutError) as exc_info:
            mixin.raise_timeout_error(
                backend_name="Ollama",
                timeout=30.0,
                error=error,
                errors=custom_errors,
            )
        assert exc_info.value.errors == custom_errors
