"""测试 core.infrastructure 子模块

覆盖: service_locator_base, throttling, monitoring, resource_monitor, cache,
      event_bus, subprocess_runner, logging, request_context, tracing
"""
from __future__ import annotations

import time
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.core.exceptions import ExternalServiceError, RateLimitError


# ============================================================
# service_locator_base.py
# ============================================================


class TestBaseServiceLocator:
    """测试 BaseServiceLocator"""

    def setup_method(self) -> None:
        from apps.core.infrastructure.service_locator_base import BaseServiceLocator

        self.SL = BaseServiceLocator
        self.SL.clear()

    def teardown_method(self) -> None:
        self.SL.clear()

    def test_register_and_get(self) -> None:
        self.SL.register("svc", "instance")
        assert self.SL.get("svc") == "instance"

    def test_get_missing_returns_none(self) -> None:
        assert self.SL.get("nonexistent") is None

    def test_get_or_create_existing(self) -> None:
        self.SL.register("svc", "existing")
        result = self.SL.get_or_create("svc", lambda: "new")
        assert result == "existing"

    def test_get_or_create_new(self) -> None:
        result = self.SL.get_or_create("svc", lambda: "created")
        assert result == "created"
        assert self.SL.get("svc") == "created"

    def test_clear_specific(self) -> None:
        self.SL.register("a", 1)
        self.SL.register("b", 2)
        self.SL.clear("a")
        assert self.SL.get("a") is None
        assert self.SL.get("b") == 2

    def test_clear_all(self) -> None:
        self.SL.register("a", 1)
        self.SL.register("b", 2)
        self.SL.clear()
        assert self.SL.get("a") is None
        assert self.SL.get("b") is None

    def test_scope_isolation(self) -> None:
        self.SL.register("global", "g")
        with self.SL.scope():
            assert self.SL.get("global") is None  # scope 隔离
            self.SL.register("scoped", "s")
            assert self.SL.get("scoped") == "s"
        # scope 结束后回归全局
        assert self.SL.get("global") == "g"
        assert self.SL.get("scoped") is None


# ============================================================
# throttling.py
# ============================================================


class TestRateLimiter:
    """测试 RateLimiter"""

    def _make_request(self, path: str = "/api/test", remote_addr: str = "127.0.0.1"):
        return SimpleNamespace(
            path=path,
            META={"REMOTE_ADDR": remote_addr, "HTTP_X_FORWARDED_FOR": None},
        )

    def test_is_allowed_within_limit(self) -> None:
        from apps.core.infrastructure.throttling import RateLimiter

        limiter = RateLimiter(requests=10, window=60)
        request = self._make_request()
        allowed, info = limiter.is_allowed(request)
        assert allowed is True
        assert info["limit"] == 10
        assert info["remaining"] >= 0

    def test_get_cache_key_default(self) -> None:
        from apps.core.infrastructure.throttling import RateLimiter

        limiter = RateLimiter(requests=10, window=60)
        request = self._make_request()
        key = limiter.get_cache_key(request)
        assert "ratelimit:" in key

    def test_get_cache_key_custom_func(self) -> None:
        from apps.core.infrastructure.throttling import RateLimiter

        limiter = RateLimiter(requests=10, window=60)
        request = self._make_request()
        key = limiter.get_cache_key(request, key_func=lambda r: "custom_key")
        assert "custom_key" not in key  # key 本身被 hash 了

    def test_get_client_ip_direct(self) -> None:
        from apps.core.infrastructure.throttling import RateLimiter

        limiter = RateLimiter()
        request = SimpleNamespace(
            META={"REMOTE_ADDR": "10.0.0.1", "HTTP_X_FORWARDED_FOR": None}
        )
        assert limiter.get_client_ip(request) == "10.0.0.1"

    def test_get_client_ip_unknown(self) -> None:
        from apps.core.infrastructure.throttling import RateLimiter

        limiter = RateLimiter()
        request = SimpleNamespace(META={})
        assert limiter.get_client_ip(request) == "unknown"


class TestRateLimitDecorator:
    """测试 rate_limit 装饰器"""

    @patch("apps.core.infrastructure.throttling.cache")
    def test_decorated_function_passes(self, mock_cache: MagicMock) -> None:
        from apps.core.infrastructure.throttling import rate_limit

        mock_cache.add.return_value = True  # 第一次请求

        @rate_limit(requests=10, window=60)
        def my_view(request):  # type: ignore[no-untyped-def]
            return "ok"

        request = SimpleNamespace(
            path="/test", META={"REMOTE_ADDR": "1.2.3.4", "HTTP_X_FORWARDED_FOR": None}
        )
        result = my_view(request)
        assert result == "ok"

    def test_rate_limit_preserves_annotations(self) -> None:
        from apps.core.infrastructure.throttling import rate_limit

        @rate_limit(requests=10, window=60)
        def my_view(request: SimpleNamespace) -> str:
            return "ok"

        assert hasattr(my_view, "__annotations__")


class TestGetRateLimitConfig:
    """测试 get_rate_limit_config"""

    @patch("django.conf.settings")
    def test_uses_fallback(self, mock_settings: MagicMock) -> None:
        from apps.core.infrastructure.throttling import get_rate_limit_config

        mock_settings.RATE_LIMIT = None
        requests, window = get_rate_limit_config("DEFAULT", fallback_requests=50, fallback_window=30)
        assert requests == 50
        assert window == 30


# ============================================================
# monitoring.py
# ============================================================


class TestPerformanceMonitor:
    """测试 PerformanceMonitor"""

    def test_slow_api_threshold(self) -> None:
        from apps.core.infrastructure.monitoring import PerformanceMonitor

        assert PerformanceMonitor.SLOW_API_THRESHOLD_MS == 1000
        assert PerformanceMonitor.SLOW_QUERY_THRESHOLD_MS == 100
        assert PerformanceMonitor.MAX_QUERY_COUNT == 10

    @patch("apps.core.infrastructure.monitoring.settings")
    def test_should_collect_queries_debug(self, mock_settings: MagicMock) -> None:
        from apps.core.infrastructure.monitoring import PerformanceMonitor

        mock_settings.DEBUG = True
        assert PerformanceMonitor._should_collect_queries() is True

    @patch("apps.core.infrastructure.monitoring.settings")
    def test_should_collect_queries_disabled(self, mock_settings: MagicMock) -> None:
        from apps.core.infrastructure.monitoring import PerformanceMonitor

        mock_settings.DEBUG = False
        with patch.dict("os.environ", {"DJANGO_DB_QUERY_METRICS": ""}):
            assert PerformanceMonitor._should_collect_queries() is False

    def test_check_performance_issues_fast(self) -> None:
        from apps.core.infrastructure.monitoring import PerformanceMonitor

        # 不应该抛异常
        PerformanceMonitor._check_performance_issues("test", duration_ms=100, query_count=5)


# ============================================================
# resource_monitor.py
# ============================================================


class TestResourceMonitor:
    """测试 ResourceMonitor"""

    def test_load_thresholds(self) -> None:
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        assert monitor.thresholds.memory_warning == 80.0
        assert monitor.thresholds.memory_critical == 90.0
        assert monitor.thresholds.disk_warning == 85.0

    def test_get_bool_env(self) -> None:
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        assert monitor._get_bool_env("SOME_MISSING_KEY", True) is True
        assert monitor._get_bool_env("SOME_MISSING_KEY", False) is False

    @patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", False)
    def test_no_psutil(self) -> None:
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        assert monitor.monitoring_enabled is False
        assert monitor.get_current_usage() is None

    @patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", True)
    def test_record_restart(self) -> None:
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        monitor.record_restart()
        assert monitor._last_restart_time is not None

    @patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", True)
    def test_should_trigger_restart_disabled(self) -> None:
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        monitor.auto_restart_enabled = False
        should, reason = monitor.should_trigger_restart()
        assert should is False
        assert "disabled" in reason.lower()

    @patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", True)
    def test_check_resource_health_no_psutil(self) -> None:
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        monitor.monitoring_enabled = False
        with patch.object(monitor, "get_current_usage", return_value=None):
            result = monitor.check_resource_health()
            assert result["status"] == "unknown"

    @patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", True)
    def test_check_resource_health_healthy(self) -> None:
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=20.0,
            memory_percent=50.0,
            memory_used_mb=4000,
            memory_total_mb=8000,
            disk_percent=40.0,
            disk_used_gb=200,
            disk_total_gb=500,
            timestamp=MagicMock(isoformat=MagicMock(return_value="2025-01-01")),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.check_resource_health()
            assert result["status"] == "healthy"

    @patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", True)
    def test_check_resource_health_memory_critical(self) -> None:
        from apps.core.infrastructure.resource_monitor import ResourceMonitor, ResourceUsage

        monitor = ResourceMonitor()
        usage = ResourceUsage(
            cpu_percent=20.0,
            memory_percent=95.0,
            memory_used_mb=7600,
            memory_total_mb=8000,
            disk_percent=40.0,
            disk_used_gb=200,
            disk_total_gb=500,
            timestamp=MagicMock(isoformat=MagicMock(return_value="2025-01-01")),
        )
        with patch.object(monitor, "get_current_usage", return_value=usage):
            result = monitor.check_resource_health()
            assert result["status"] == "critical"

    @patch("apps.core.infrastructure.resource_monitor.PSUTIL_AVAILABLE", True)
    def test_get_resource_recommendations_unavailable(self) -> None:
        from apps.core.infrastructure.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        with patch.object(monitor, "get_current_usage", return_value=None):
            result = monitor.get_resource_recommendations()
            assert "message" in result


# ============================================================
# cache.py (CacheKeys, CacheTimeout, etc.)
# ============================================================


class TestCacheKeys:
    """测试 CacheKeys"""

    def test_user_org_access(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys

        assert CacheKeys.user_org_access(42) == "user:org_access:42"

    def test_user_teams(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys

        assert CacheKeys.user_teams(7) == "user:teams:7"

    def test_case_access_grants(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys

        assert CacheKeys.case_access_grants(10) == "case:access_grants:10"

    def test_court_token(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys

        key = CacheKeys.court_token("wenshu.court.gov.cn", "user@example.com")
        assert "court_token:" in key
        assert "wenshu.court.gov.cn" in key  # site_name 被 normalize

    def test_system_config(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys

        assert CacheKeys.system_config("my_key") == "system_config:my_key"

    def test_prompt_template(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys

        assert CacheKeys.prompt_template("my_prompt") == "prompt_template:my_prompt"

    def test_documents_matching_contract_templates(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys

        key = CacheKeys.documents_matching_contract_templates(case_type="civil", version=3)
        assert "civil" in key
        assert "3" in key

    def test_documents_matching_version_document_templates(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys

        key = CacheKeys.documents_matching_version_document_templates()
        assert "document_templates" in key

    def test_automation_court_sms_recovery_scheduled(self) -> None:
        from apps.core.infrastructure.cache import CacheKeys

        key = CacheKeys.automation_court_sms_recovery_scheduled()
        assert "court_sms_recovery" in key


class TestCacheTimeout:
    """测试 CacheTimeout"""

    def test_short_default(self) -> None:
        from apps.core.infrastructure.cache import CacheTimeout

        assert CacheTimeout.SHORT == 60

    def test_medium_default(self) -> None:
        from apps.core.infrastructure.cache import CacheTimeout

        assert CacheTimeout.MEDIUM == 300

    def test_long_default(self) -> None:
        from apps.core.infrastructure.cache import CacheTimeout

        assert CacheTimeout.LONG == 3600

    def test_day_default(self) -> None:
        from apps.core.infrastructure.cache import CacheTimeout

        assert CacheTimeout.DAY == 86400

    def test_get_short(self) -> None:
        from apps.core.infrastructure.cache import CacheTimeout

        assert CacheTimeout.get_short() == 60

    def test_get_medium(self) -> None:
        from apps.core.infrastructure.cache import CacheTimeout

        assert CacheTimeout.get_medium() == 300


class TestNormalizeKeyComponent:
    """测试 _normalize_key_component"""

    def test_simple_ascii(self) -> None:
        from apps.core.infrastructure.cache import _normalize_key_component

        assert _normalize_key_component("hello-world") == "hello-world"

    def test_empty_string(self) -> None:
        from apps.core.infrastructure.cache import _normalize_key_component

        assert _normalize_key_component("") == "empty"

    def test_special_chars(self) -> None:
        from apps.core.infrastructure.cache import _normalize_key_component

        result = _normalize_key_component("hello world!")
        assert "!" not in result

    def test_long_value(self) -> None:
        from apps.core.infrastructure.cache import _normalize_key_component

        result = _normalize_key_component("a" * 100, max_len=32)
        # truncated string (32 chars) + "-" + hash (32 chars) = 65
        assert len(result) <= 66


# ============================================================
# event_bus.py
# ============================================================


class TestEventBus:
    """测试 EventBus"""

    def test_subscribe_and_publish(self) -> None:
        from apps.core.infrastructure.event_bus import EventBus

        received: list[dict] = []

        def handler(payload: dict) -> None:
            received.append(payload)

        EventBus.subscribe("test.event", handler)
        EventBus.publish("test.event", {"key": "value"})
        assert len(received) == 1
        assert received[0]["key"] == "value"

    def test_publish_no_payload(self) -> None:
        from apps.core.infrastructure.event_bus import EventBus

        received: list[dict] = []

        def handler(payload: dict) -> None:
            received.append(payload)

        EventBus.subscribe("test.empty", handler)
        EventBus.publish("test.empty")
        assert received == [{}]

    def test_publish_no_subscribers(self) -> None:
        from apps.core.infrastructure.event_bus import EventBus

        # 不应该抛异常
        EventBus.publish("no.subscribers", {"data": 1})


# ============================================================
# subprocess_runner.py
# ============================================================


class TestSubprocessRunner:
    """测试 SubprocessRunner"""

    def test_truncate_short_string(self) -> None:
        from apps.core.infrastructure.subprocess_runner import SubprocessRunner

        runner = SubprocessRunner(max_output_chars=100)
        assert runner._truncate("short") == "short"

    def test_truncate_long_string(self) -> None:
        from apps.core.infrastructure.subprocess_runner import SubprocessRunner

        runner = SubprocessRunner(max_output_chars=10)
        result = runner._truncate("a" * 20)
        # 10 chars + "...(truncated)" = 24 chars
        assert len(result) == 24
        assert result.startswith("aaaaaaaaaa")
        assert "truncated" in result

    def test_truncate_empty(self) -> None:
        from apps.core.infrastructure.subprocess_runner import SubprocessRunner

        runner = SubprocessRunner()
        assert runner._truncate("") == ""

    def test_truncate_zero_max(self) -> None:
        from apps.core.infrastructure.subprocess_runner import SubprocessRunner

        runner = SubprocessRunner(max_output_chars=0)
        assert runner._truncate("anything") == ""

    def test_validate_args_empty_list(self) -> None:
        from apps.core.infrastructure.subprocess_runner import SubprocessRunner

        runner = SubprocessRunner()
        with pytest.raises(ExternalServiceError):
            runner._validate_args([])

    def test_validate_args_not_list(self) -> None:
        from apps.core.infrastructure.subprocess_runner import SubprocessRunner

        runner = SubprocessRunner()
        with pytest.raises(ExternalServiceError):
            runner._validate_args("not-a-list")  # type: ignore[arg-type]

    def test_validate_args_whitelist_pass(self) -> None:
        from apps.core.infrastructure.subprocess_runner import SubprocessRunner

        runner = SubprocessRunner(allowed_programs={"echo", "ls"})
        runner._validate_args(["echo", "hello"])  # 不抛异常

    def test_validate_args_whitelist_fail(self) -> None:
        from apps.core.infrastructure.subprocess_runner import SubprocessRunner

        runner = SubprocessRunner(allowed_programs={"echo"})
        with pytest.raises(ExternalServiceError, match="不允许"):
            runner._validate_args(["rm", "-rf", "/"])

    def test_run_success(self) -> None:
        from apps.core.infrastructure.subprocess_runner import SubprocessRunner

        runner = SubprocessRunner()
        result = runner.run(args=["echo", "hello"], text=True)
        assert "hello" in result.stdout
        assert result.returncode == 0

    def test_run_with_allowed_programs(self) -> None:
        from apps.core.infrastructure.subprocess_runner import SubprocessRunner

        runner = SubprocessRunner(allowed_programs={"echo"})
        result = runner.run(args=["echo", "test"])
        assert "test" in result.stdout

    def test_popen_rejects_shell(self) -> None:
        from apps.core.infrastructure.subprocess_runner import SubprocessRunner

        runner = SubprocessRunner()
        with pytest.raises(ExternalServiceError, match="不安全"):
            runner.popen(args=["echo"], shell=True)  # noqa: S604


# ============================================================
# logging.py - SensitiveDataFilter
# ============================================================


class TestSensitiveDataFilter:
    """测试 SensitiveDataFilter"""

    def test_scrub_message_api_key(self) -> None:
        from apps.core.infrastructure.logging import SensitiveDataFilter

        f = SensitiveDataFilter()
        result = f._scrub_message("Authorization: Bearer abcdefghijklmnopqr")  # allowlist secret
        assert "abcdefghijklmnopqr" not in result

    def test_scrub_value_sensitive_key(self) -> None:
        from apps.core.infrastructure.logging import SensitiveDataFilter

        f = SensitiveDataFilter()
        assert f._scrub_value("token", "secret_value") == "***"
        assert f._scrub_value("password", "mypassword") == "***"

    def test_scrub_value_safe_key(self) -> None:
        from apps.core.infrastructure.logging import SensitiveDataFilter

        f = SensitiveDataFilter()
        assert f._scrub_value("name", "john") == "john"

    def test_scrub_value_email(self) -> None:
        from apps.core.infrastructure.logging import SensitiveDataFilter

        f = SensitiveDataFilter()
        result = f._scrub_value("email", "user@example.com")
        assert "***" in result
        assert "user@example.com" not in result

    def test_scrub_value_dict(self) -> None:
        from apps.core.infrastructure.logging import SensitiveDataFilter

        f = SensitiveDataFilter()
        result = f._scrub_value("data", {"token": "secret", "name": "ok"})
        assert result["token"] == "***"
        assert result["name"] == "ok"

    def test_scrub_value_sk_key_in_value(self) -> None:
        from apps.core.infrastructure.logging import SensitiveDataFilter

        f = SensitiveDataFilter()
        result = f._scrub_value("msg", "Using key sk-abcdefghijklmnopqrstuvwxyz")
        assert "sk-" not in result

    def test_mask_email(self) -> None:
        from apps.core.infrastructure.logging import SensitiveDataFilter

        f = SensitiveDataFilter()
        assert "***" in f._mask_email("user@example.com")
        assert f._mask_email("ab") == "***"


class TestJsonFormatter:
    """测试 JsonFormatter"""

    def test_format_basic_record(self) -> None:
        import json
        import logging

        from apps.core.infrastructure.logging import JsonFormatter

        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=10, msg="Hello %s", args=("world",), exc_info=None
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "Hello world"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test"


# ============================================================
# request_context.py
# ============================================================


class TestRequestContext:
    """测试 request_context 模块"""

    def test_generate_request_id(self) -> None:
        from apps.core.infrastructure.request_context import generate_request_id

        rid = generate_request_id()
        assert len(rid) == 8

    def test_set_and_get_request_context(self) -> None:
        from apps.core.infrastructure.request_context import (
            clear_request_context,
            get_request_id,
            get_trace_ids,
            set_request_context,
        )

        set_request_context(request_id="abc123", trace_id="tr1", span_id="sp1")
        assert get_request_id(fallback_generate=False) == "abc123"
        assert get_trace_ids() == ("tr1", "sp1")
        clear_request_context()

    def test_get_request_id_auto_generate(self) -> None:
        from apps.core.infrastructure.request_context import (
            clear_request_context,
            get_request_id,
        )

        clear_request_context()
        rid = get_request_id(fallback_generate=True)
        assert rid is not None
        assert len(rid) == 8

    def test_get_request_id_no_generate(self) -> None:
        from apps.core.infrastructure.request_context import (
            clear_request_context,
            get_request_id,
        )

        clear_request_context()
        assert get_request_id(fallback_generate=False) is None

    def test_clear_request_context(self) -> None:
        from apps.core.infrastructure.request_context import (
            clear_request_context,
            get_request_id,
            set_request_context,
        )

        set_request_context(request_id="test123")
        clear_request_context()
        assert get_request_id(fallback_generate=False) is None


# ============================================================
# tracing.py
# ============================================================


class TestTracing:
    """测试 tracing 模块"""

    def test_get_current_trace_ids_no_opentelemetry(self) -> None:
        from apps.core.infrastructure.tracing import get_current_trace_ids

        with patch.dict("sys.modules", {"opentelemetry": None}):
            trace_id, span_id = get_current_trace_ids()
            assert trace_id is None
            assert span_id is None


# ============================================================
# logging.py - RequestContextFilter
# ============================================================


class TestRequestContextFilter:
    """测试 RequestContextFilter"""

    def test_filter_injects_request_id(self) -> None:
        import logging

        from apps.core.infrastructure.logging import RequestContextFilter

        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="t.py",
            lineno=1, msg="test", args=(), exc_info=None
        )

        with patch("apps.core.infrastructure.request_context.get_request_id", return_value="rid123"), \
             patch("apps.core.infrastructure.request_context.get_trace_ids", return_value=("tid", "sid")), \
             patch("apps.core.infrastructure.request_context.get_task_name", return_value="task1"):
            result = RequestContextFilter().filter(record)
            assert result is True
            assert record.request_id == "rid123"
            assert record.trace_id == "tid"
            assert record.span_id == "sid"
            assert record.task_name == "task1"
