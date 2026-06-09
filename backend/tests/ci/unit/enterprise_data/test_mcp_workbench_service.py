"""Tests for enterprise_data.services.workbench.service - McpWorkbenchService."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import PermissionDenied, ValidationException
from apps.enterprise_data.services.workbench.service import McpWorkbenchService


class TestMcpWorkbenchServiceInit:
    def test_default_init(self) -> None:
        svc = McpWorkbenchService(enforce_superuser=False)
        assert svc._enforce_superuser is False

    def test_enforce_superuser(self) -> None:
        svc = McpWorkbenchService(enforce_superuser=True)
        assert svc._enforce_superuser is True

    def test_custom_sample_ttl(self) -> None:
        svc = McpWorkbenchService(sample_ttl_seconds=120, enforce_superuser=False)
        assert svc._sample_ttl_seconds == 120

    def test_minimum_sample_ttl(self) -> None:
        svc = McpWorkbenchService(sample_ttl_seconds=10, enforce_superuser=False)
        assert svc._sample_ttl_seconds == 60  # minimum is 60


class TestEnsureSuperuser:
    def test_not_enforced(self) -> None:
        svc = McpWorkbenchService(enforce_superuser=False)
        svc._ensure_superuser(actor_is_superuser=False)  # Should not raise

    def test_enforced_with_superuser(self) -> None:
        svc = McpWorkbenchService(enforce_superuser=True)
        svc._ensure_superuser(actor_is_superuser=True)  # Should not raise

    def test_enforced_without_superuser(self) -> None:
        svc = McpWorkbenchService(enforce_superuser=True)
        with pytest.raises(PermissionDenied):
            svc._ensure_superuser(actor_is_superuser=False)


class TestMaskPayload:
    def test_mask_dict(self) -> None:
        svc = McpWorkbenchService(enforce_superuser=False)
        result = svc._mask_payload({"key": "value"})
        assert isinstance(result, dict)

    def test_mask_string(self) -> None:
        svc = McpWorkbenchService(enforce_superuser=False)
        result = svc._mask_payload("test string")
        assert isinstance(result, str)

    def test_mask_none(self) -> None:
        svc = McpWorkbenchService(enforce_superuser=False)
        result = svc._mask_payload(None)
        assert result is None


class TestListProviders:
    def test_list_providers(self) -> None:
        mock_registry = MagicMock()
        mock_descriptor = MagicMock()
        mock_descriptor.name = "test_provider"
        mock_descriptor.enabled = True
        mock_descriptor.is_default = False
        mock_descriptor.transport = "stdio"
        mock_descriptor.capabilities = ["search"]
        mock_registry.list_providers.return_value = [mock_descriptor]

        svc = McpWorkbenchService(registry=mock_registry, enforce_superuser=False)
        result = svc.list_providers()
        assert len(result) == 1
        assert result[0]["name"] == "test_provider"
        assert result[0]["enabled"] is True

    def test_list_providers_empty(self) -> None:
        mock_registry = MagicMock()
        mock_registry.list_providers.return_value = []

        svc = McpWorkbenchService(registry=mock_registry, enforce_superuser=False)
        result = svc.list_providers()
        assert result == []


class TestReadRegistryMethods:
    def test_read_registry_int_valid(self) -> None:
        mock_registry = MagicMock()
        mock_registry.get_metrics_window_seconds.return_value = 300
        svc = McpWorkbenchService(registry=mock_registry, enforce_superuser=False)
        result = svc._read_registry_int("get_metrics_window_seconds", 60)
        assert result == 300

    def test_read_registry_int_no_method(self) -> None:
        mock_registry = MagicMock(spec=[])  # No methods
        svc = McpWorkbenchService(registry=mock_registry, enforce_superuser=False)
        result = svc._read_registry_int("nonexistent", 60)
        assert result == 60

    def test_read_registry_int_invalid_value(self) -> None:
        mock_registry = MagicMock()
        mock_registry.get_metrics_window_seconds.return_value = "abc"
        svc = McpWorkbenchService(registry=mock_registry, enforce_superuser=False)
        result = svc._read_registry_int("get_metrics_window_seconds", 60)
        assert result == 60

    def test_read_registry_int_zero_returns_default(self) -> None:
        mock_registry = MagicMock()
        mock_registry.get_metrics_window_seconds.return_value = 0
        svc = McpWorkbenchService(registry=mock_registry, enforce_superuser=False)
        result = svc._read_registry_int("get_metrics_window_seconds", 60)
        assert result == 60

    def test_read_registry_float_valid(self) -> None:
        mock_registry = MagicMock()
        mock_registry.get_alert_success_rate.return_value = 0.95
        svc = McpWorkbenchService(registry=mock_registry, enforce_superuser=False)
        result = svc._read_registry_float("get_alert_success_rate", 0.8)
        assert result == 0.95

    def test_read_registry_float_no_method(self) -> None:
        mock_registry = MagicMock(spec=[])
        svc = McpWorkbenchService(registry=mock_registry, enforce_superuser=False)
        result = svc._read_registry_float("nonexistent", 0.8)
        assert result == 0.8

    def test_read_registry_float_invalid(self) -> None:
        mock_registry = MagicMock()
        mock_registry.get_alert_success_rate.return_value = "abc"
        svc = McpWorkbenchService(registry=mock_registry, enforce_superuser=False)
        result = svc._read_registry_float("get_alert_success_rate", 0.8)
        assert result == 0.8


class TestInvalidateDescribeCache:
    @patch("apps.enterprise_data.services.workbench.service.cache")
    def test_invalidate_cache(self, mock_cache: MagicMock) -> None:
        svc = McpWorkbenchService(enforce_superuser=False)
        svc._invalidate_describe_cache("test_provider")
        mock_cache.delete.assert_called_once_with("mcp_workbench:describe_tools_full:test_provider")


class TestExecuteTool:
    def test_empty_tool_name_raises(self) -> None:
        svc = McpWorkbenchService(enforce_superuser=False)
        with pytest.raises(ValidationException, match="tool_name 不能为空"):
            svc.execute_tool(tool_name="", arguments={}, actor_is_superuser=False)

    def test_whitespace_tool_name_raises(self) -> None:
        svc = McpWorkbenchService(enforce_superuser=False)
        with pytest.raises(ValidationException, match="tool_name 不能为空"):
            svc.execute_tool(tool_name="   ", arguments={}, actor_is_superuser=False)

    def test_non_dict_arguments_raises(self) -> None:
        svc = McpWorkbenchService(enforce_superuser=False)
        with pytest.raises(ValidationException, match="arguments 必须为 JSON Object"):
            svc.execute_tool(tool_name="test_tool", arguments="not a dict", actor_is_superuser=False)

    def test_superuser_required_raises(self) -> None:
        svc = McpWorkbenchService(enforce_superuser=True)
        with pytest.raises(PermissionDenied):
            svc.execute_tool(
                tool_name="test_tool",
                arguments={},
                actor_is_superuser=False,
            )


class TestListHistory:
    def test_superuser_required(self) -> None:
        svc = McpWorkbenchService(enforce_superuser=True)
        with pytest.raises(PermissionDenied):
            svc.list_history(actor_is_superuser=False)

    @pytest.mark.django_db
    def test_list_history_empty(self) -> None:
        svc = McpWorkbenchService(enforce_superuser=False)
        result = svc.list_history(actor_is_superuser=False)
        assert isinstance(result, list)


class TestReplayExecution:
    def test_superuser_required(self) -> None:
        svc = McpWorkbenchService(enforce_superuser=True)
        with pytest.raises(PermissionDenied):
            svc.replay_execution(execution_id=1, actor_is_superuser=False)

    @pytest.mark.django_db
    def test_replay_not_found(self) -> None:
        svc = McpWorkbenchService(enforce_superuser=False)
        with pytest.raises(ValidationException, match="未找到执行记录"):
            svc.replay_execution(execution_id=999999, actor_is_superuser=False)


class TestDescribeTools:
    def test_superuser_required(self) -> None:
        svc = McpWorkbenchService(enforce_superuser=True)
        with pytest.raises(PermissionDenied):
            svc.describe_tools(actor_is_superuser=False)

    @patch("apps.enterprise_data.services.workbench.service.cache")
    def test_cache_hit(self, mock_cache: MagicMock) -> None:
        cached = {"tools": [{"name": "test"}], "provider": "p", "transport": "stdio"}
        mock_cache.get.return_value = cached

        svc = McpWorkbenchService(enforce_superuser=False)
        result = svc.describe_tools(actor_is_superuser=False)
        assert result == cached
