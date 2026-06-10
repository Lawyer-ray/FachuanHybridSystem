"""
Tests for apps.enterprise_data.services — 企业数据服务
"""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# ProviderConfig / ProviderDescriptor / ProviderResponse 测试
# ============================================================


class TestEnterpriseDataTypes:
    """企业数据类型测试"""

    def test_provider_config(self) -> None:
        from apps.enterprise_data.services.types import ProviderConfig

        cfg = ProviderConfig(
            name="tianyancha",
            enabled=True,
            transport="streamable_http",
            base_url="https://mcp.tianyancha.com",
            sse_url="https://mcp.tianyancha.com/sse",
            api_key="test_key",
            timeout_seconds=30,
        )
        assert cfg.name == "tianyancha"
        assert cfg.enabled is True
        assert cfg.timeout_seconds == 30

    def test_provider_descriptor(self) -> None:
        from apps.enterprise_data.services.types import ProviderDescriptor

        desc = ProviderDescriptor(
            name="tianyancha",
            enabled=True,
            is_default=True,
            transport="streamable_http",
            capabilities=["search", "detail"],
        )
        assert desc.name == "tianyancha"
        assert desc.is_default is True

    def test_provider_response(self) -> None:
        from apps.enterprise_data.services.types import ProviderResponse

        resp = ProviderResponse(data={"name": "test"}, raw={}, tool="search")
        assert resp.data == {"name": "test"}
        assert resp.meta == {}

    def test_default_constants(self) -> None:
        from apps.enterprise_data.services.types import (
            DEFAULT_PROVIDER_NAME,
            DEFAULT_TIMEOUT_SECONDS,
            DEFAULT_CACHE_TTL_SECONDS,
        )
        assert DEFAULT_PROVIDER_NAME == "tianyancha"
        assert DEFAULT_TIMEOUT_SECONDS == 30
        assert DEFAULT_CACHE_TTL_SECONDS == 300


# ============================================================
# McpApiKeyPool 测试
# ============================================================


class TestMcpApiKeyPool:
    """API Key Pool 测试"""

    def test_size(self) -> None:
        from apps.enterprise_data.services.clients.api_key_pool import McpApiKeyPool

        pool = McpApiKeyPool(provider_name="test", api_keys=["key1", "key2", "key3"])
        assert pool.size == 3

    def test_size_dedup(self) -> None:
        from apps.enterprise_data.services.clients.api_key_pool import McpApiKeyPool

        pool = McpApiKeyPool(provider_name="test", api_keys=["key1", "key1", "key2"])
        assert pool.size == 2

    def test_size_empty(self) -> None:
        from apps.enterprise_data.services.clients.api_key_pool import McpApiKeyPool

        pool = McpApiKeyPool(provider_name="test", api_keys=[])
        assert pool.size == 0

    def test_fingerprint(self) -> None:
        from apps.enterprise_data.services.clients.api_key_pool import McpApiKeyPool

        pool = McpApiKeyPool(provider_name="test", api_keys=["key1"])
        fp = pool.fingerprint("test_key")
        expected = hashlib.sha256(b"test_key").hexdigest()[:16]
        assert fp == expected

    def test_fingerprint_empty(self) -> None:
        from apps.enterprise_data.services.clients.api_key_pool import McpApiKeyPool

        pool = McpApiKeyPool(provider_name="test", api_keys=[])
        assert pool.fingerprint("") == ""
        assert pool.fingerprint(None) == ""

    def test_ordered_keys_single(self) -> None:
        from apps.enterprise_data.services.clients.api_key_pool import McpApiKeyPool

        pool = McpApiKeyPool(provider_name="test", api_keys=["key1"])
        keys = pool.ordered_keys()
        assert keys == ["key1"]

    def test_normalize_api_keys_dedup(self) -> None:
        from apps.enterprise_data.services.clients.api_key_pool import McpApiKeyPool

        pool = McpApiKeyPool(provider_name="test", api_keys=["key1", "key1", "key2", ""])
        assert pool._api_keys == ("key1", "key2")

    def test_order_with_preferred(self) -> None:
        from apps.enterprise_data.services.clients.api_key_pool import McpApiKeyPool

        pool = McpApiKeyPool(provider_name="test", api_keys=["key1", "key2", "key3"])
        preferred_fp = pool.fingerprint("key2")
        result = pool._order_with_preferred(["key1", "key2", "key3"], preferred_fp)
        assert result[0] == "key2"

    def test_order_with_preferred_no_preferred(self) -> None:
        from apps.enterprise_data.services.clients.api_key_pool import McpApiKeyPool

        pool = McpApiKeyPool(provider_name="test", api_keys=["key1", "key2"])
        result = pool._order_with_preferred(["key1", "key2"], "")
        assert result == ["key1", "key2"]

    def test_order_with_preferred_single_key(self) -> None:
        from apps.enterprise_data.services.clients.api_key_pool import McpApiKeyPool

        pool = McpApiKeyPool(provider_name="test", api_keys=["key1"])
        result = pool._order_with_preferred(["key1"], "anything")
        assert result == ["key1"]


# ============================================================
# EnterpriseDataMetricsService 测试
# ============================================================


class TestEnterpriseDataMetricsService:
    """指标服务测试"""

    def _make_service(self, **kwargs):
        from apps.enterprise_data.services.metrics_service import EnterpriseDataMetricsService

        return EnterpriseDataMetricsService(**kwargs)

    def test_bucket_key_format(self) -> None:
        from apps.enterprise_data.services.metrics_service import EnterpriseDataMetricsService

        key = EnterpriseDataMetricsService._bucket_key(provider="tianyancha", capability="search")
        assert "tianyancha" in key
        assert "search" in key

    def test_new_bucket(self) -> None:
        svc = self._make_service()
        bucket = svc._new_bucket(1000)
        assert bucket["window_start"] == 1000
        assert bucket["total"] == 0
        assert bucket["success"] == 0

    def test_snapshot_from_bucket_empty(self) -> None:
        svc = self._make_service()
        snapshot = svc._snapshot_from_bucket({"total": 0, "success": 0, "failure": 0, "fallback": 0, "duration_sum_ms": 0, "window_start": 0, "window_end": 0})
        assert snapshot["total"] == 0
        assert snapshot["success_rate"] == 1.0
        assert snapshot["fallback_rate"] == 0.0

    def test_snapshot_from_bucket_with_data(self) -> None:
        svc = self._make_service()
        snapshot = svc._snapshot_from_bucket(
            {"total": 10, "success": 8, "failure": 2, "fallback": 1, "duration_sum_ms": 5000, "window_start": 0, "window_end": 100}
        )
        assert snapshot["total"] == 10
        assert snapshot["success_rate"] == 0.8
        assert snapshot["fallback_rate"] == 0.1
        assert snapshot["avg_duration_ms"] == 500

    def test_defaults(self) -> None:
        svc = self._make_service()
        assert svc._window_seconds >= 60
        assert svc._alert_min_samples >= 1


# ============================================================
# EnterpriseProviderRegistry 测试
# ============================================================


class TestEnterpriseProviderRegistry:
    """Provider Registry 测试"""

    def test_get_cache_ttl_seconds(self) -> None:
        from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry

        registry = EnterpriseProviderRegistry(config_service=MagicMock())
        assert registry.get_cache_ttl_seconds() == 300

    def test_get_default_provider_name(self) -> None:
        from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry

        registry = EnterpriseProviderRegistry(config_service=MagicMock())
        assert registry.get_default_provider_name() == "tianyancha"

    def test_get_tianyancha_transport_default(self) -> None:
        from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry

        mock_config = MagicMock()
        mock_config.get_value.return_value = "streamable_http"
        registry = EnterpriseProviderRegistry(config_service=mock_config)
        assert registry.get_tianyancha_transport() == "streamable_http"

    def test_get_tianyancha_transport_sse(self) -> None:
        from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry

        mock_config = MagicMock()
        mock_config.get_value.return_value = "sse"
        registry = EnterpriseProviderRegistry(config_service=mock_config)
        assert registry.get_tianyancha_transport() == "sse"

    def test_get_tianyancha_transport_invalid_fallback(self) -> None:
        from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry

        mock_config = MagicMock()
        mock_config.get_value.return_value = "invalid"
        registry = EnterpriseProviderRegistry(config_service=mock_config)
        assert registry.get_tianyancha_transport() == "streamable_http"

    def test_get_rate_limit_defaults(self) -> None:
        from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry

        registry = EnterpriseProviderRegistry(config_service=MagicMock())
        assert registry.get_rate_limit_requests() == 60
        assert registry.get_rate_limit_window_seconds() == 60
        assert registry.get_retry_max_attempts() == 2
        assert registry.get_retry_backoff_seconds() == 0.25

    def test_split_secret_values_empty(self) -> None:
        from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry

        assert EnterpriseProviderRegistry._split_secret_values("") == ()

    def test_split_secret_values_single(self) -> None:
        from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry

        result = EnterpriseProviderRegistry._split_secret_values("key1")
        assert result == ("key1",)

    def test_split_secret_values_multiple(self) -> None:
        from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry

        result = EnterpriseProviderRegistry._split_secret_values("key1\nkey2\nkey3")
        assert len(result) == 3

    def test_split_secret_values_dedup(self) -> None:
        from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry

        result = EnterpriseProviderRegistry._split_secret_values("key1\nkey1\nkey2")
        assert len(result) == 2

    def test_split_secret_values_comma_separated(self) -> None:
        from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry

        result = EnterpriseProviderRegistry._split_secret_values("key1,key2")
        assert len(result) == 2

    def test_get_provider_unsupported_raises(self) -> None:
        from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry
        from apps.core.exceptions import ValidationException

        mock_config = MagicMock()
        mock_config.get_value.return_value = "streamable_http"
        registry = EnterpriseProviderRegistry(config_service=mock_config)
        with pytest.raises(ValidationException, match="不支持的企业数据提供商"):
            registry.get_provider("nonexistent")

    def test_get_alert_thresholds(self) -> None:
        from apps.enterprise_data.services.provider_registry import EnterpriseProviderRegistry

        registry = EnterpriseProviderRegistry(config_service=MagicMock())
        assert registry.get_alert_success_rate_threshold() == 0.9
        assert registry.get_alert_fallback_rate_threshold() == 0.35
        assert registry.get_alert_avg_latency_ms_threshold() == 3000


# ============================================================
# McpToolClient 补充测试
# ============================================================

class TestMcpToolClientExtended:
    def test_headers_streamable_http_lowercase_bearer(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(
            provider_name="test", transport="streamable_http",
            base_url="https://api.example.com", sse_url="", api_key="mykey"
        )
        headers = client._headers(transport="streamable_http", api_key="mykey")
        assert headers["Authorization"] == "bearer mykey"

    def test_headers_sse_capital_bearer(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(
            provider_name="test", transport="sse", base_url="", sse_url="", api_key="mykey"
        )
        headers = client._headers(transport="sse", api_key="mykey")
        assert headers["Authorization"] == "Bearer mykey"

    def test_transport_attempts_primary_only(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(
            provider_name="test", transport="streamable_http",
            base_url="https://api.example.com", sse_url="", api_key="k"
        )
        attempts = client._transport_attempts()
        assert attempts == ["streamable_http"]

    def test_transport_attempts_with_sse_fallback(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(
            provider_name="test", transport="streamable_http",
            base_url="https://api.example.com", sse_url="https://api.example.com/sse", api_key="k"
        )
        attempts = client._transport_attempts()
        assert "streamable_http" in attempts
        assert "sse" in attempts

    def test_should_retry_timeout(self):
        import httpx
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(provider_name="t", transport="sse", base_url="", sse_url="", api_key="k")
        assert client._should_retry(httpx.TimeoutException("t")) is True

    def test_should_retry_connect_error(self):
        import httpx
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(provider_name="t", transport="sse", base_url="", sse_url="", api_key="k")
        assert client._should_retry(httpx.ConnectError("c")) is True

    def test_should_retry_500(self):
        import httpx
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(provider_name="t", transport="sse", base_url="", sse_url="", api_key="k")
        resp = MagicMock(); resp.status_code = 500
        exc = httpx.HTTPStatusError("s", request=MagicMock(), response=resp)
        assert client._should_retry(exc) is True

    def test_should_not_retry_429(self):
        import httpx
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(provider_name="t", transport="sse", base_url="", sse_url="", api_key="k")
        resp = MagicMock(); resp.status_code = 429
        exc = httpx.HTTPStatusError("r", request=MagicMock(), response=resp)
        assert client._should_retry(exc) is False

    def test_should_switch_api_key_auth_error(self):
        from apps.core.exceptions import AuthenticationError
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(provider_name="t", transport="sse", base_url="", sse_url="", api_key="k")
        assert client._should_switch_api_key(AuthenticationError("auth")) is True

    def test_extract_payload_structured(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(provider_name="t", transport="sse", base_url="", sse_url="", api_key="k")
        result = MagicMock(); result.structuredContent = {"a": 1}; result.content = []
        assert client._extract_payload(result) == {"a": 1}

    def test_extract_payload_single_text_json(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        client = McpToolClient(provider_name="t", transport="sse", base_url="", sse_url="", api_key="k")
        result = MagicMock(); result.structuredContent = None
        item = MagicMock(); item.type = "text"; item.text = '{"a": 1}'
        result.content = [item]
        assert client._extract_payload(result) == {"a": 1}

    def test_try_parse_json_valid(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        assert McpToolClient._try_parse_json('{"a": 1}') == {"a": 1}

    def test_try_parse_json_invalid(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        assert McpToolClient._try_parse_json("not json") is None

    def test_contains_auth_token(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        assert McpToolClient._contains_auth_token("unauthorized") is True
        assert McpToolClient._contains_auth_token("timeout") is False

    def test_flatten_error_payload(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        result = McpToolClient._flatten_error_payload_text({"error": "unauthorized", "code": 401})
        assert "unauthorized" in result

    def test_collect_related_exceptions(self):
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        exc = ValueError("test")
        collected = McpToolClient._collect_related_exceptions(exc)
        assert collected[0] is exc

    def test_is_auth_like_http_error_401(self):
        import httpx
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        resp = MagicMock(); resp.status_code = 401; resp.text = ""; resp.json.side_effect = Exception()
        exc = httpx.HTTPStatusError("u", request=MagicMock(), response=resp)
        assert McpToolClient._is_auth_like_http_error(exc) is True

    def test_is_auth_like_http_error_500(self):
        import httpx
        from apps.enterprise_data.services.clients.mcp_tool_client import McpToolClient
        resp = MagicMock(); resp.status_code = 500; resp.text = "err"; resp.json.side_effect = Exception()
        exc = httpx.HTTPStatusError("s", request=MagicMock(), response=resp)
        assert McpToolClient._is_auth_like_http_error(exc) is False
