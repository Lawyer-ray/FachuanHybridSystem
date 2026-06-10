"""enterprise_data.services.workbench.service 补充覆盖测试。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, PropertyMock
from typing import Any

import pytest


class TestMcpWorkbenchServiceInit:
    def test_default_init(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        with patch("apps.enterprise_data.services.workbench.service.EnterpriseProviderRegistry"):
            with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
                svc = McpWorkbenchService()
                assert svc._persist_history is True
                assert svc._enforce_superuser is True

    def test_custom_params(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        registry = MagicMock()
        registry.get_metrics_window_seconds.return_value = 3600
        registry.get_alert_min_samples.return_value = 10
        registry.get_alert_success_rate_threshold.return_value = 0.95
        registry.get_alert_fallback_rate_threshold.return_value = 0.1
        registry.get_alert_avg_latency_ms_threshold.return_value = 5000

        svc = McpWorkbenchService(
            registry=registry,
            sample_ttl_seconds=120,
            persist_history=False,
            enforce_superuser=False,
        )
        assert svc._persist_history is False
        assert svc._enforce_superuser is False
        assert svc._sample_ttl_seconds == 120

    def test_sample_ttl_minimum(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        with patch("apps.enterprise_data.services.workbench.service.EnterpriseProviderRegistry"):
            with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
                svc = McpWorkbenchService(sample_ttl_seconds=10)
                assert svc._sample_ttl_seconds == 60  # minimum


class TestEnsureSuperuser:
    def test_enforce_disabled_passes(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        with patch("apps.enterprise_data.services.workbench.service.EnterpriseProviderRegistry"):
            with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
                svc = McpWorkbenchService(enforce_superuser=False)
                svc._ensure_superuser(actor_is_superuser=False)  # Should not raise

    def test_is_superuser_passes(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        with patch("apps.enterprise_data.services.workbench.service.EnterpriseProviderRegistry"):
            with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
                svc = McpWorkbenchService(enforce_superuser=True)
                svc._ensure_superuser(actor_is_superuser=True)

    def test_not_superuser_raises(self):
        from apps.core.exceptions import PermissionDenied
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        with patch("apps.enterprise_data.services.workbench.service.EnterpriseProviderRegistry"):
            with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
                svc = McpWorkbenchService(enforce_superuser=True)
                with pytest.raises(PermissionDenied):
                    svc._ensure_superuser(actor_is_superuser=False)


class TestReadRegistryHelpers:
    def test_read_registry_int_success(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        registry = MagicMock()
        registry.get_metrics_window_seconds.return_value = 3600
        registry.get_alert_min_samples.return_value = 10
        registry.get_alert_success_rate_threshold.return_value = 0.95
        registry.get_alert_fallback_rate_threshold.return_value = 0.1
        registry.get_alert_avg_latency_ms_threshold.return_value = 5000

        svc = McpWorkbenchService(registry=registry)
        assert svc._read_registry_int("get_metrics_window_seconds", 100) == 3600

    def test_read_registry_int_missing_method(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        registry = MagicMock(spec=[])  # No methods
        registry.get_metrics_window_seconds = None
        registry.get_alert_min_samples = None
        registry.get_alert_success_rate_threshold = None
        registry.get_alert_fallback_rate_threshold = None
        registry.get_alert_avg_latency_ms_threshold = None

        with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
            svc = McpWorkbenchService(registry=registry)
        assert svc._read_registry_int("nonexistent", 100) == 100

    def test_read_registry_int_invalid_value(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        registry = MagicMock()
        registry.get_metrics_window_seconds.return_value = "invalid"
        registry.get_alert_min_samples.return_value = 10
        registry.get_alert_success_rate_threshold.return_value = 0.95
        registry.get_alert_fallback_rate_threshold.return_value = 0.1
        registry.get_alert_avg_latency_ms_threshold.return_value = 5000

        svc = McpWorkbenchService(registry=registry)
        assert svc._read_registry_int("get_metrics_window_seconds", 100) == 100

    def test_read_registry_int_zero_returns_default(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        registry = MagicMock()
        registry.get_metrics_window_seconds.return_value = 0
        registry.get_alert_min_samples.return_value = 10
        registry.get_alert_success_rate_threshold.return_value = 0.95
        registry.get_alert_fallback_rate_threshold.return_value = 0.1
        registry.get_alert_avg_latency_ms_threshold.return_value = 5000

        svc = McpWorkbenchService(registry=registry)
        assert svc._read_registry_int("get_metrics_window_seconds", 100) == 100

    def test_read_registry_float_success(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        registry = MagicMock()
        registry.get_metrics_window_seconds.return_value = 3600
        registry.get_alert_min_samples.return_value = 10
        registry.get_alert_success_rate_threshold.return_value = 0.95
        registry.get_alert_fallback_rate_threshold.return_value = 0.1
        registry.get_alert_avg_latency_ms_threshold.return_value = 5000

        svc = McpWorkbenchService(registry=registry)
        assert svc._read_registry_float("get_alert_success_rate_threshold", 0.9) == 0.95

    def test_read_registry_float_invalid(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        registry = MagicMock()
        registry.get_metrics_window_seconds.return_value = 3600
        registry.get_alert_min_samples.return_value = 10
        registry.get_alert_success_rate_threshold.return_value = "invalid"
        registry.get_alert_fallback_rate_threshold.return_value = 0.1
        registry.get_alert_avg_latency_ms_threshold.return_value = 5000

        svc = McpWorkbenchService(registry=registry)
        assert svc._read_registry_float("get_alert_success_rate_threshold", 0.9) == 0.9

    def test_read_registry_float_missing_method(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        registry = MagicMock(spec=[])
        registry.get_metrics_window_seconds = None
        registry.get_alert_min_samples = None
        registry.get_alert_success_rate_threshold = None
        registry.get_alert_fallback_rate_threshold = None
        registry.get_alert_avg_latency_ms_threshold = None

        with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
            svc = McpWorkbenchService(registry=registry)
        assert svc._read_registry_float("nonexistent", 0.9) == 0.9


class TestTruncateData:
    def test_small_data_not_truncated(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        data = {"key": "value"}
        result = McpWorkbenchService._truncate_data(data)
        assert result == data

    def test_large_data_truncated(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        data = {"key": "x" * 20000}
        result = McpWorkbenchService._truncate_data(data)
        assert isinstance(result, dict)
        assert result.get("_truncated") is True
        assert "preview" in result
        assert "original_length" in result

    def test_non_serializable_returns_as_is(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        # Create an object that json.dumps can't handle but fallback works
        class BadObj:
            pass

        result = McpWorkbenchService._truncate_data(BadObj())
        # default=str in json.dumps handles it
        assert result is not None


class TestSampleCacheKey:
    def test_format(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        key = McpWorkbenchService._sample_cache_key(provider="qichacha", tool_name="search")
        assert key == "mcp_workbench:sample:qichacha:search"


class TestInvalidateDescribeCache:
    @patch("apps.enterprise_data.services.workbench.service.cache")
    def test_deletes_cache(self, mock_cache):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        McpWorkbenchService._invalidate_describe_cache("qichacha")
        mock_cache.delete.assert_called_once_with("mcp_workbench:describe_tools_full:qichacha")


class TestListProviders:
    def test_list_providers(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        registry = MagicMock()
        descriptor = MagicMock()
        descriptor.name = "qichacha"
        descriptor.enabled = True
        descriptor.is_default = True
        descriptor.transport = "mcp"
        descriptor.capabilities = ["search"]
        registry.list_providers.return_value = [descriptor]

        registry.get_metrics_window_seconds.return_value = 3600
        registry.get_alert_min_samples.return_value = 10
        registry.get_alert_success_rate_threshold.return_value = 0.95
        registry.get_alert_fallback_rate_threshold.return_value = 0.1
        registry.get_alert_avg_latency_ms_threshold.return_value = 5000

        svc = McpWorkbenchService(registry=registry, enforce_superuser=False)
        result = svc.list_providers()
        assert len(result) == 1
        assert result[0]["name"] == "qichacha"
        assert result[0]["enabled"] is True


class TestDescribeTools:
    @patch("apps.enterprise_data.services.workbench.service.cache")
    def test_returns_cached_full(self, mock_cache):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        cached_result = {"provider": "test", "transport": "mcp", "tools": []}
        mock_cache.get.return_value = cached_result

        with patch("apps.enterprise_data.services.workbench.service.EnterpriseProviderRegistry"):
            with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
                svc = McpWorkbenchService(enforce_superuser=False)
                result = svc.describe_tools(actor_is_superuser=True)
                assert result == cached_result


class TestMaskPayload:
    def test_mask_payload_delegates(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        with patch("apps.enterprise_data.services.workbench.service.scrub_for_storage") as mock_scrub:
            mock_scrub.return_value = {"masked": True}
            result = McpWorkbenchService._mask_payload({"secret": "data"})
            mock_scrub.assert_called_once_with({"secret": "data"})


class TestResolveReplayRecord:
    def test_none_returns_none(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        result = McpWorkbenchService._resolve_replay_record(replay_of_id=None)
        assert result is None

    def test_zero_returns_none(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        result = McpWorkbenchService._resolve_replay_record(replay_of_id=0)
        assert result is None


class TestCreateHistory:
    @patch("apps.enterprise_data.services.workbench.service.McpWorkbenchExecution")
    def test_persist_disabled(self, mock_model):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        with patch("apps.enterprise_data.services.workbench.service.EnterpriseProviderRegistry"):
            with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
                svc = McpWorkbenchService(persist_history=False)
                svc._create_history(
                    provider="test",
                    tool_name="search",
                    arguments={},
                    response_data={},
                    response_raw={},
                    response_meta={},
                    success=True,
                    error_code="",
                    error_message="",
                    duration_ms=100,
                    operator_username="admin",
                    replay_of=None,
                )
                mock_model.objects.create.assert_not_called()

    @patch("apps.enterprise_data.services.workbench.service.McpWorkbenchExecution")
    def test_persist_enabled(self, mock_model):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        with patch("apps.enterprise_data.services.workbench.service.EnterpriseProviderRegistry"):
            with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
                svc = McpWorkbenchService(persist_history=True)
                svc._create_history(
                    provider="test",
                    tool_name="search",
                    arguments={"q": "test"},
                    response_data={"results": []},
                    response_raw={},
                    response_meta={"transport": "mcp", "requested_transport": "stdio"},
                    success=True,
                    error_code="",
                    error_message="",
                    duration_ms=100,
                    operator_username="admin",
                    replay_of=None,
                )
                mock_model.objects.create.assert_called_once()


class TestExecuteTool:
    def test_empty_tool_name_raises(self):
        from apps.core.exceptions import ValidationException
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        with patch("apps.enterprise_data.services.workbench.service.EnterpriseProviderRegistry"):
            with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
                svc = McpWorkbenchService(enforce_superuser=False)
                with pytest.raises(ValidationException):
                    svc.execute_tool(
                        tool_name="",
                        arguments={},
                        actor_is_superuser=True,
                    )

    def test_non_dict_arguments_raises(self):
        from apps.core.exceptions import ValidationException
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService

        with patch("apps.enterprise_data.services.workbench.service.EnterpriseProviderRegistry"):
            with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
                svc = McpWorkbenchService(enforce_superuser=False)
                with pytest.raises(ValidationException):
                    svc.execute_tool(
                        tool_name="search",
                        arguments="not a dict",  # type: ignore[arg-type]
                        actor_is_superuser=True,
                    )
