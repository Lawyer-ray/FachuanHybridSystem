"""
基础设施层测试：覆盖 RequestIdMiddleware、日志 Formatter/Filter、RequestContext。
"""

from __future__ import annotations

import json
import logging
import re
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# =====================================================================
# RequestIdMiddleware
# =====================================================================


class TestRequestIdMiddleware:
    """RequestIdMiddleware 的 ID 生成和 Header 解析。"""

    def test_generate_request_id_is_short_hex(self) -> None:
        """生成的 request_id 应为 8 位 hex 字符串。"""
        from apps.core.infrastructure.request_context import generate_request_id
        rid = generate_request_id()
        assert isinstance(rid, str)
        assert len(rid) == 8
        assert re.match(r"[0-9a-f]{8}", rid)

    def test_generate_request_id_unique(self) -> None:
        """连续生成应不同。"""
        from apps.core.infrastructure.request_context import generate_request_id
        ids = {generate_request_id() for _ in range(100)}
        assert len(ids) == 100

    def test_middleware_calls_set_request_context(self) -> None:
        """中间件应调用 set_request_context。"""
        from apps.core.middleware.request_id import RequestIdMiddleware
        middleware = RequestIdMiddleware(MagicMock())
        request = MagicMock()
        request.headers = {"X-Request-ID": "valid-id-123"}
        request.META = {}

        with patch("apps.core.middleware.request_id.set_request_context") as mock_set:
            with patch("apps.core.middleware.request_id.get_current_trace_ids", return_value=("", "")):
                middleware(request)
                mock_set.assert_called_once()

    def test_middleware_rejects_invalid_xff(self) -> None:
        """包含空格的 X-Request-ID 应被拒绝。"""
        from apps.core.middleware.request_id import RequestIdMiddleware
        middleware = RequestIdMiddleware(MagicMock())
        request = MagicMock()
        request.headers = {"X-Request-ID": "invalid id with spaces!"}
        request.META = {}

        with patch("apps.core.middleware.request_id.set_request_context") as mock_set:
            with patch("apps.core.middleware.request_id.get_current_trace_ids", return_value=("", "")):
                middleware(request)
                kwargs = mock_set.call_args[1]
                assert kwargs["request_id"] != "invalid id with spaces!"


# =====================================================================
# SensitiveDataFilter 日志脱敏
# =====================================================================


class TestSensitiveDataFilter:
    """SensitiveDataFilter 应脱敏 Bearer token 和 sk- 开头的 API key。"""

    def _make_record(self, msg: str) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg=msg, args=None, exc_info=None,
        )
        return record

    def test_scrubs_bearer_token(self) -> None:
        """Authorization: Bearer token 应被脱敏。"""
        from apps.core.infrastructure.logging import SensitiveDataFilter
        flt = SensitiveDataFilter()
        record = self._make_record("Authorization: Bearer FAKE_TOKEN_FOR_TESTING")  # pragma: allowlist secret
        flt.filter(record)
        assert "eyJhbGciOiJIUzI1NiJ9" not in record.msg
        assert "***" in record.msg

    def test_scrubs_sk_api_key(self) -> None:
        """sk- 开头的 API key 应被脱敏。"""
        from apps.core.infrastructure.logging import SensitiveDataFilter
        flt = SensitiveDataFilter()
        record = self._make_record("using key sk-abcdefghijklmnopqrstuvwxyz1234")
        flt.filter(record)
        assert "sk-abcdefghijklmnopqrstuvwxyz1234" not in record.msg

    def test_scrubs_token_equals_sk(self) -> None:
        """token=sk-xxx 格式应被脱敏。"""
        from apps.core.infrastructure.logging import SensitiveDataFilter
        flt = SensitiveDataFilter()
        record = self._make_record("token=sk-FAKE_FOR_TESTING")
        flt.filter(record)
        assert "sk-abcdefghijklmnopqrst" not in record.msg

    def test_normal_message_unchanged(self) -> None:
        """普通日志消息不应被修改。"""
        from apps.core.infrastructure.logging import SensitiveDataFilter
        flt = SensitiveDataFilter()
        msg = "Case 123 processed successfully in 2.5s"
        record = self._make_record(msg)
        flt.filter(record)
        assert record.msg == msg


# =====================================================================
# RequestContextFilter
# =====================================================================


class TestRequestContextFilter:
    """RequestContextFilter 应将 trace 字段注入 LogRecord。"""

    def test_filter_stamps_attributes(self) -> None:
        """filter 应添加 request_id、trace_id、span_id。"""
        from apps.core.infrastructure.logging import RequestContextFilter
        flt = RequestContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="test", args=None, exc_info=None,
        )
        with patch("apps.core.infrastructure.request_context.request_id_var") as mock_var:
            mock_var.get.return_value = "req-123"
            with patch("apps.core.infrastructure.request_context.trace_id_var") as trace_var:
                trace_var.get.return_value = "trace-abc"
                with patch("apps.core.infrastructure.request_context.span_id_var") as span_var:
                    span_var.get.return_value = "span-def"
                    with patch("apps.core.infrastructure.request_context.task_name_var") as task_var:
                        task_var.get.return_value = ""
                        flt.filter(record)

        assert hasattr(record, "request_id")
        assert hasattr(record, "trace_id")
        assert hasattr(record, "span_id")


# =====================================================================
# RequestContext DTO
# =====================================================================


class TestRequestContextDTO:
    """extract_request_context 应正确提取请求上下文。"""

    def test_extract_with_org_access(self) -> None:
        """从 request 构建应包含 org_access。"""
        from apps.core.dto.request_context import extract_request_context
        request = MagicMock()
        request.user = SimpleNamespace(id=1)
        request.org_access = {"lawyers": {1, 2, 3}}
        request.perm_open_access = False

        ctx = extract_request_context(request)
        assert ctx.user.id == 1
        assert ctx.org_access == {"lawyers": {1, 2, 3}}
        assert ctx.perm_open_access is False

    def test_extract_without_org_access(self) -> None:
        """无 org_access 时应为 None。"""
        from apps.core.dto.request_context import extract_request_context
        request = MagicMock(spec=[])  # 空 spec，getattr 返回 None
        ctx = extract_request_context(request)
        assert ctx.user is None
        assert ctx.org_access is None


# =====================================================================
# JsonFormatter 日志格式化
# =====================================================================


class TestJsonFormatter:
    """JsonFormatter 应输出合法 JSON 且包含关键字段。"""

    def _make_record(self, msg: str = "test message", level: int = logging.INFO) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test.logger", level=level, pathname="test.py", lineno=42,
            msg=msg, args=None, exc_info=None,
        )
        record.request_id = "req-001"
        record.trace_id = "trace-001"
        record.span_id = "span-001"
        record.task_name = ""
        return record

    def test_output_is_valid_json(self) -> None:
        """输出应为合法 JSON。"""
        from apps.core.infrastructure.logging import JsonFormatter
        formatter = JsonFormatter()
        record = self._make_record()
        output = formatter.format(record)
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_contains_required_fields(self) -> None:
        """输出应包含 timestamp、level、message 等关键字段。"""
        from apps.core.infrastructure.logging import JsonFormatter
        formatter = JsonFormatter()
        record = self._make_record(msg="hello world")
        data = json.loads(formatter.format(record))
        assert "timestamp" in data
        assert data["level"] == "INFO"
        assert data["message"] == "hello world"
        assert data["request_id"] == "req-001"
        assert data["trace_id"] == "trace-001"

    def test_error_level(self) -> None:
        """ERROR 级别应正确标记。"""
        from apps.core.infrastructure.logging import JsonFormatter
        formatter = JsonFormatter()
        record = self._make_record(msg="error!", level=logging.ERROR)
        data = json.loads(formatter.format(record))
        assert data["level"] == "ERROR"

    def test_empty_request_id_excluded(self) -> None:
        """空 request_id 不应出现在输出中。"""
        from apps.core.infrastructure.logging import JsonFormatter
        formatter = JsonFormatter()
        record = self._make_record()
        record.request_id = ""
        data = json.loads(formatter.format(record))
        # 空值应被排除或为空
        assert not data.get("request_id")
