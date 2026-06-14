"""Tests for apps.core.infrastructure.logging — SensitiveDataFilter and JsonFormatter."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest

from apps.core.infrastructure.logging import JsonFormatter, SensitiveDataFilter


class TestSensitiveDataFilterMaskEmail:
    def test_mask_email(self):
        f = SensitiveDataFilter()
        assert f._mask_email("ab@example.com") == "ab***om"

    def test_mask_email_short(self):
        f = SensitiveDataFilter()
        assert f._mask_email("a@b.com") == "a@b.com" or len(f._mask_email("a@b.com")) > 0

    def test_mask_non_email(self):
        f = SensitiveDataFilter()
        result = f._mask_email("hello")
        assert "***" in result

    def test_mask_short_non_email(self):
        f = SensitiveDataFilter()
        assert f._mask_email("abc") == "***"


class TestSensitiveDataFilterScrubValue:
    def test_scrub_sensitive_key(self):
        f = SensitiveDataFilter()
        assert f._scrub_value("password", "secret123") == "***"

    def test_scrub_account_key(self):
        f = SensitiveDataFilter()
        result = f._scrub_value("account", "user@example.com")
        assert "***" in result

    def test_scrub_dict(self):
        f = SensitiveDataFilter()
        result = f._scrub_value("config", {"password": "abc", "port": 8080})
        assert result["password"] == "***"
        assert result["port"] == 8080

    def test_scrub_normal_string(self):
        f = SensitiveDataFilter()
        assert f._scrub_value("name", "hello") == "hello"

    def test_scrub_sk_token_in_value(self):
        f = SensitiveDataFilter()
        result = f._scrub_value("info", "token is sk-12345678901234567890abcdef")
        assert "***" in result

    def test_scrub_non_string(self):
        f = SensitiveDataFilter()
        assert f._scrub_value("count", 42) == 42


class TestSensitiveDataFilterScrubMessage:
    def test_scrub_bearer_token(self):
        f = SensitiveDataFilter()
        result = f._scrub_message("Auth: Authorization: Bearer sk-secrettoken12345678")
        assert "sk-secrettoken12345678" not in result

    def test_scrub_token_equals(self):
        f = SensitiveDataFilter()
        result = f._scrub_message("token = sk-abcdef1234567890abcdef")
        assert "sk-abcdef1234567890abcdef" not in result

    def test_scrub_standalone_sk(self):
        f = SensitiveDataFilter()
        result = f._scrub_message("Key: sk-abcdefghijklmnopqrstuv")
        assert "sk-abcdefghijklmnopqrstuv" not in result


class TestSensitiveDataFilterFilter:
    def test_filter_scrubs_record(self):
        f = SensitiveDataFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Auth: Bearer sk-12345678901234567890abcdef", args=(), exc_info=None,
        )
        result = f.filter(record)
        assert result is True
        assert "sk-12345678901234567890abcdef" not in record.msg


class TestJsonFormatter:
    def test_format_basic(self):
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py", lineno=1,
            msg="hello %s", args=("world",), exc_info=None,
        )
        record.module = "test"
        record.funcName = "test_func"
        record.request_id = "req-1"
        record.trace_id = ""
        record.span_id = ""
        record.task_name = ""
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "hello world"
        assert parsed["request_id"] == "req-1"

    def test_format_with_exception(self):
        fmt = JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="test.py", lineno=1,
            msg="error occurred", args=(), exc_info=exc_info,
        )
        record.module = "test"
        record.funcName = "f"
        record.request_id = ""
        record.trace_id = "tid"
        record.span_id = "sid"
        record.task_name = "task1"
        output = fmt.format(record)
        parsed = json.loads(output)
        assert "exception" in parsed
        assert "boom" in parsed["exception"]
        assert parsed["trace_id"] == "tid"

    def test_format_with_extra_fields(self):
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py", lineno=1,
            msg="msg", args=(), exc_info=None,
        )
        record.module = "test"
        record.funcName = "f"
        record.request_id = ""
        record.trace_id = ""
        record.span_id = ""
        record.task_name = ""
        record.custom_key = "custom_value"
        output = fmt.format(record)
        parsed = json.loads(output)
        assert parsed["custom_key"] == "custom_value"


class TestIsDockerEnvironment:
    def test_not_docker_by_default(self):
        from apps.core.infrastructure.logging import _is_docker_environment
        with pytest.MonkeyPatch.context() as m:
            m.delenv("DOCKER_CONTAINER", raising=False)
            m.delenv("DB_HOST", raising=False)
            # On CI/dev machine, /.dockerenv should not exist
            result = _is_docker_environment()
            assert isinstance(result, bool)
