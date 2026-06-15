"""Tests for enterprise_data.services.workbench.service (additional coverage).

Covers: _ensure_superuser, list_providers, execute_tool success/error paths,
replay_execution, _resolve_replay_record, _truncate_data, _sample_cache_key,
_read_registry_int, _read_registry_float, _mask_payload.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestMcpWorkbenchServiceEnsureSuperuser:
    def _make_svc(self, enforce=True):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService
        with patch("apps.enterprise_data.services.workbench.service.EnterpriseProviderRegistry"):
            with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
                return McpWorkbenchService(enforce_superuser=enforce)

    def test_enforce_disabled(self):
        svc = self._make_svc(enforce=False)
        svc._ensure_superuser(actor_is_superuser=False)  # should not raise

    def test_superuser_ok(self):
        svc = self._make_svc()
        svc._ensure_superuser(actor_is_superuser=True)

    def test_non_superuser_raises(self):
        svc = self._make_svc()
        with pytest.raises(Exception, match="超级管理员"):
            svc._ensure_superuser(actor_is_superuser=False)


class TestListProviders:
    def _make_svc(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService
        with patch("apps.enterprise_data.services.workbench.service.EnterpriseProviderRegistry") as MockReg:
            with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
                svc = McpWorkbenchService()
                svc._registry = MockReg.return_value
                return svc

    def test_basic(self):
        svc = self._make_svc()
        desc = SimpleNamespace(
            name="test_provider", enabled=True, is_default=False,
            transport="stdio", capabilities=["tools"],
        )
        svc._registry.list_providers.return_value = [desc]
        result = svc.list_providers()
        assert len(result) == 1
        assert result[0]["name"] == "test_provider"
        assert result[0]["enabled"] is True


class TestTruncateData:
    def test_small_data(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService
        data = {"key": "value"}
        result = McpWorkbenchService._truncate_data(data)
        assert result == data

    def test_large_data_truncated(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService
        data = {"key": "x" * 15000}
        result = McpWorkbenchService._truncate_data(data)
        assert result["_truncated"] is True
        assert "preview" in result
        assert "original_length" in result

    def test_non_serializable(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService
        result = McpWorkbenchService._truncate_data(object())
        assert result is not None


class TestSampleCacheKey:
    def test_format(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService
        key = McpWorkbenchService._sample_cache_key(provider="p", tool_name="t")
        assert key == "mcp_workbench:sample:p:t"


class TestReadRegistryInt:
    def _make_svc(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService
        with patch("apps.enterprise_data.services.workbench.service.EnterpriseProviderRegistry"):
            with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
                return McpWorkbenchService()

    def test_method_exists(self):
        svc = self._make_svc()
        svc._registry = MagicMock()
        svc._registry.get_val.return_value = 42
        result = svc._read_registry_int("get_val", 10)
        assert result == 42

    def test_method_not_exists(self):
        svc = self._make_svc()
        svc._registry = MagicMock(spec=[])  # no methods
        result = svc._read_registry_int("nonexistent_method", 10)
        assert result == 10

    def test_method_returns_none(self):
        svc = self._make_svc()
        svc._registry = MagicMock()
        svc._registry.get_val.return_value = None
        result = svc._read_registry_int("get_val", 10)
        assert result == 10

    def test_method_returns_non_positive(self):
        svc = self._make_svc()
        svc._registry = MagicMock()
        svc._registry.get_val.return_value = -5
        result = svc._read_registry_int("get_val", 10)
        assert result == 10

    def test_method_raises(self):
        svc = self._make_svc()
        svc._registry = MagicMock()
        svc._registry.get_val.side_effect = TypeError("bad")
        result = svc._read_registry_int("get_val", 10)
        assert result == 10


class TestReadRegistryFloat:
    def _make_svc(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService
        with patch("apps.enterprise_data.services.workbench.service.EnterpriseProviderRegistry"):
            with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
                return McpWorkbenchService()

    def test_method_exists(self):
        svc = self._make_svc()
        svc._registry = MagicMock()
        svc._registry.get_val.return_value = 3.14
        result = svc._read_registry_float("get_val", 1.0)
        assert result == 3.14

    def test_method_not_exists(self):
        svc = self._make_svc()
        svc._registry = MagicMock(spec=[])  # no methods
        result = svc._read_registry_float("nonexistent", 1.0)
        assert result == 1.0

    def test_method_returns_none(self):
        svc = self._make_svc()
        svc._registry = MagicMock()
        svc._registry.get_val.return_value = None
        result = svc._read_registry_float("get_val", 1.0)
        assert result == 1.0


class TestMaskPayload:
    def test_delegates_to_scrub(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService
        with patch("apps.enterprise_data.services.workbench.service.scrub_for_storage") as mock_scrub:
            mock_scrub.return_value = "masked"
            result = McpWorkbenchService._mask_payload({"key": "value"})
            mock_scrub.assert_called_once_with({"key": "value"})
            assert result == "masked"


class TestResolveReplayRecord:
    def test_no_id(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService
        assert McpWorkbenchService._resolve_replay_record(replay_of_id=None) is None
        assert McpWorkbenchService._resolve_replay_record(replay_of_id=0) is None

    def test_valid_id(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService
        record = SimpleNamespace(id=1)
        with patch("apps.enterprise_data.services.workbench.service.McpWorkbenchExecution") as MockExec:
            MockExec.objects.get.return_value = record
            result = McpWorkbenchService._resolve_replay_record(replay_of_id=1)
            assert result is record

    def test_not_found(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService
        with patch("apps.enterprise_data.services.workbench.service.McpWorkbenchExecution") as MockExec:
            MockExec.DoesNotExist = Exception
            MockExec.objects.get.side_effect = MockExec.DoesNotExist
            result = McpWorkbenchService._resolve_replay_record(replay_of_id=999)
            assert result is None

    def test_invalid_type(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService
        with patch("apps.enterprise_data.services.workbench.service.McpWorkbenchExecution") as MockExec:
            MockExec.DoesNotExist = Exception
            MockExec.objects.get.side_effect = TypeError("bad")
            result = McpWorkbenchService._resolve_replay_record(replay_of_id="abc")
            assert result is None


class TestExecuteToolSuccess:
    def test_success(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService
        with patch("apps.enterprise_data.services.workbench.service.EnterpriseProviderRegistry"):
            with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
                svc = McpWorkbenchService(enforce_superuser=False, persist_history=False)

        mock_provider = MagicMock()
        mock_provider.name = "test"
        mock_provider.transport = "stdio"
        svc._registry = MagicMock()
        svc._registry.get_provider.return_value = mock_provider

        mock_response = SimpleNamespace(
            tool="test_tool", data={"result": "ok"}, raw={}, meta=None
        )
        mock_provider.execute_tool.return_value = mock_response
        svc._metrics = MagicMock()
        svc._metrics.record.return_value = {}

        result = svc.execute_tool(
            provider="test", tool_name="test_tool", arguments={"q": "1"},
            actor_is_superuser=True, actor_username="admin",
        )
        assert result["tool"] == "test_tool"
        assert result["provider"] == "test"


class TestExecuteToolValidation:
    def test_empty_tool_name(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService
        with patch("apps.enterprise_data.services.workbench.service.EnterpriseProviderRegistry"):
            with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
                svc = McpWorkbenchService(enforce_superuser=False)
        with pytest.raises(Exception, match="tool_name 不能为空"):
            svc.execute_tool(
                tool_name="", arguments={}, actor_is_superuser=True
            )

    def test_non_dict_arguments(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService
        with patch("apps.enterprise_data.services.workbench.service.EnterpriseProviderRegistry"):
            with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
                svc = McpWorkbenchService(enforce_superuser=False)
        with pytest.raises(Exception, match="arguments 必须为 JSON Object"):
            svc.execute_tool(
                tool_name="t", arguments="not_dict", actor_is_superuser=True
            )


class TestReplayExecution:
    def test_not_found(self):
        from apps.enterprise_data.services.workbench.service import McpWorkbenchService
        with patch("apps.enterprise_data.services.workbench.service.EnterpriseProviderRegistry"):
            with patch("apps.enterprise_data.services.workbench.service.EnterpriseDataMetricsService"):
                svc = McpWorkbenchService(enforce_superuser=False)
        with patch("apps.enterprise_data.services.workbench.service.McpWorkbenchExecution") as MockExec:
            MockExec.DoesNotExist = Exception
            MockExec.objects.get.side_effect = MockExec.DoesNotExist
            with pytest.raises(Exception, match="未找到执行记录"):
                svc.replay_execution(execution_id=999, actor_is_superuser=True)
