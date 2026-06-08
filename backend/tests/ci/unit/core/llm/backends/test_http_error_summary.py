"""Tests for core.llm.backends.http_error_summary and httpx_errors."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.core.llm.backends.http_error_summary import (
    _first_str,
    _truncate,
    summarize_http_error_response,
)
from apps.core.llm.backends.httpx_errors import HttpxErrorMixin
from apps.core.llm.exceptions import LLMNetworkError, LLMTimeoutError


class TestFirstStr:
    def test_found(self) -> None:
        assert _first_str({"a": "hello", "b": "world"}, ["a", "b"]) == "hello"

    def test_found_second(self) -> None:
        assert _first_str({"b": "world"}, ["a", "b"]) == "world"

    def test_not_found(self) -> None:
        assert _first_str({"a": "hello"}, ["x", "y"]) is None

    def test_empty_value_skipped(self) -> None:
        assert _first_str({"a": "  ", "b": "ok"}, ["a", "b"]) == "ok"

    def test_non_string_skipped(self) -> None:
        assert _first_str({"a": 123, "b": "ok"}, ["a", "b"]) == "ok"


class TestTruncate:
    def test_short_string(self) -> None:
        assert _truncate("hello", 10) == "hello"

    def test_exact_length(self) -> None:
        assert _truncate("hello", 5) == "hello"

    def test_long_string(self) -> None:
        result = _truncate("hello world", 5)
        assert result == "hello..."


class TestSummarizeHttpResponse:
    def test_basic(self) -> None:
        resp = MagicMock()
        resp.status_code = 400
        resp.headers = {}
        resp.json.return_value = {"error": "Bad request"}
        result = summarize_http_error_response(resp)
        assert result["status_code"] == 400

    def test_with_request_id(self) -> None:
        resp = MagicMock()
        resp.status_code = 500
        resp.headers = {"x-request-id": "abc-123"}
        resp.json.return_value = {"error": {"message": "Internal error"}}
        result = summarize_http_error_response(resp)
        assert result["upstream_request_id"] == "abc-123"

    def test_with_trace_id(self) -> None:
        resp = MagicMock()
        resp.status_code = 500
        resp.headers = {"x-trace-id": "trace-456"}
        resp.json.return_value = {}
        result = summarize_http_error_response(resp)
        assert result["upstream_request_id"] == "trace-456"

    def test_json_error_dict_with_code(self) -> None:
        resp = MagicMock()
        resp.status_code = 400
        resp.headers = {}
        resp.json.return_value = {"error": {"message": "Invalid input", "code": "VALIDATION_ERROR"}}
        result = summarize_http_error_response(resp)
        assert result["upstream_error_message"] == "Invalid input"
        assert result["upstream_error_code"] == "VALIDATION_ERROR"

    def test_json_error_string(self) -> None:
        resp = MagicMock()
        resp.status_code = 400
        resp.headers = {}
        resp.json.return_value = {"error": "Bad request"}
        result = summarize_http_error_response(resp)
        assert result["upstream_error_message"] == "Bad request"

    def test_json_message_at_top_level(self) -> None:
        resp = MagicMock()
        resp.status_code = 400
        resp.headers = {}
        resp.json.return_value = {"message": "Something went wrong"}
        result = summarize_http_error_response(resp)
        assert result["upstream_error_message"] == "Something went wrong"

    def test_json_parse_fallback_to_text(self) -> None:
        resp = MagicMock()
        resp.status_code = 500
        resp.headers = {}
        resp.json.side_effect = ValueError("Invalid JSON")
        resp.text = "Internal Server Error"
        result = summarize_http_error_response(resp)
        assert result["upstream_error_text"] == "Internal Server Error"

    def test_content_type_header(self) -> None:
        resp = MagicMock()
        resp.status_code = 400
        resp.headers = {"content-type": "application/json"}
        resp.json.return_value = {}
        result = summarize_http_error_response(resp)
        assert result["content_type"] == "application/json"

    def test_amazon_request_id(self) -> None:
        resp = MagicMock()
        resp.status_code = 500
        resp.headers = {"x-amzn-requestid": "aws-123"}
        resp.json.return_value = {}
        result = summarize_http_error_response(resp)
        assert result["upstream_request_id"] == "aws-123"

    def test_generic_request_id(self) -> None:
        resp = MagicMock()
        resp.status_code = 500
        resp.headers = {"request-id": "gen-123"}
        resp.json.return_value = {}
        result = summarize_http_error_response(resp)
        assert result["upstream_request_id"] == "gen-123"


class TestHttpxErrorMixin:
    def test_raise_connect_error(self) -> None:
        mixin = HttpxErrorMixin()
        error = MagicMock()
        error.__str__ = lambda self: "Connection refused"
        with pytest.raises(LLMNetworkError):
            mixin.raise_connect_error(
                backend_name="Test",
                base_url="http://localhost",
                error=error,
            )

    def test_raise_connect_error_custom_message(self) -> None:
        mixin = HttpxErrorMixin()
        error = MagicMock()
        with pytest.raises(LLMNetworkError, match="custom message"):
            mixin.raise_connect_error(
                backend_name="Test",
                base_url="http://localhost",
                error=error,
                message="custom message",
            )

    def test_raise_timeout_error(self) -> None:
        mixin = HttpxErrorMixin()
        error = MagicMock()
        with pytest.raises(LLMTimeoutError):
            mixin.raise_timeout_error(
                backend_name="Test",
                timeout=30.0,
                error=error,
            )

    def test_raise_timeout_error_custom_message(self) -> None:
        mixin = HttpxErrorMixin()
        error = MagicMock()
        with pytest.raises(LLMTimeoutError, match="custom timeout"):
            mixin.raise_timeout_error(
                backend_name="Test",
                timeout=30.0,
                error=error,
                message="custom timeout message",
            )
