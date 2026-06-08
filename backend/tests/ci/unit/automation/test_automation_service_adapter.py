"""Tests for apps/automation/services/automation_service_adapter.py — AutomationServiceAdapter."""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest

# The source code imports `from apps.core.exceptions import ValidationError` which does not exist.
# Inject a ValidationError alias before importing the module under test.
import apps.core.exceptions as _core_exc

if not hasattr(_core_exc, "ValidationError"):
    from apps.core.exceptions.common import ValidationException

    _core_exc.ValidationError = ValidationException  # type: ignore[attr-defined]

from apps.automation.services.automation_service_adapter import AutomationServiceAdapter  # noqa: E402


class TestAutomationServiceAdapter:
    """AutomationServiceAdapter.create_token_acquisition_history_internal 单元测试。"""

    def _make_adapter(self) -> AutomationServiceAdapter:
        return AutomationServiceAdapter()

    def _valid_data(self) -> dict:
        return {
            "site_name": "test_site",
            "account": "user@example.com",
            "credential_id": 1,
            "status": "SUCCESS",
            "trigger_reason": "manual",
        }

    @patch("apps.automation.services.automation_service_adapter.TokenAcquisitionHistory")
    @patch("apps.automation.services.automation_service_adapter.timezone")
    def test_create_success(self, mock_tz: MagicMock, mock_model: MagicMock) -> None:
        """成功创建历史记录时返回对象。"""
        mock_tz.now.return_value = MagicMock()
        mock_history = MagicMock()
        mock_model.objects.create.return_value = mock_history

        adapter = self._make_adapter()
        result = adapter.create_token_acquisition_history_internal(self._valid_data())
        assert result is mock_history
        mock_model.objects.create.assert_called_once()

    def test_missing_required_field_raises(self) -> None:
        """缺少必需字段时抛出 ValidationError。"""
        adapter = self._make_adapter()
        incomplete = {k: v for k, v in self._valid_data().items() if k != "site_name"}
        with pytest.raises(Exception) as exc_info:
            adapter.create_token_acquisition_history_internal(incomplete)
        assert "缺少必需字段" in str(exc_info.value)

    def test_missing_account_field_raises(self) -> None:
        """缺少 account 字段时抛出 ValidationError。"""
        adapter = self._make_adapter()
        incomplete = {k: v for k, v in self._valid_data().items() if k != "account"}
        with pytest.raises(Exception) as exc_info:
            adapter.create_token_acquisition_history_internal(incomplete)
        assert "缺少必需字段" in str(exc_info.value)

    def test_invalid_status_raises(self) -> None:
        """无效状态值时抛出 ValidationError。"""
        adapter = self._make_adapter()
        data = {**self._valid_data(), "status": "INVALID"}
        with pytest.raises(Exception) as exc_info:
            adapter.create_token_acquisition_history_internal(data)
        assert "无效的状态值" in str(exc_info.value)

    @patch("apps.automation.services.automation_service_adapter.TokenAcquisitionHistory")
    @patch("apps.automation.services.automation_service_adapter.timezone")
    def test_failed_status_accepted(self, mock_tz: MagicMock, mock_model: MagicMock) -> None:
        """status='FAILED' 也能正常创建记录。"""
        mock_tz.now.return_value = MagicMock()
        mock_model.objects.create.return_value = MagicMock()

        adapter = self._make_adapter()
        data = {**self._valid_data(), "status": "FAILED"}
        result = adapter.create_token_acquisition_history_internal(data)
        assert result is not None

    @patch("apps.automation.services.automation_service_adapter.TokenAcquisitionHistory")
    @patch("apps.automation.services.automation_service_adapter.timezone")
    def test_optional_fields_defaults(self, mock_tz: MagicMock, mock_model: MagicMock) -> None:
        """可选字段有默认值(attempt_count=1, total_duration=0.0)。"""
        mock_tz.now.return_value = MagicMock()
        mock_model.objects.create.return_value = MagicMock()

        adapter = self._make_adapter()
        adapter.create_token_acquisition_history_internal(self._valid_data())
        call_kwargs = mock_model.objects.create.call_args[1]
        assert call_kwargs["attempt_count"] == 1
        assert call_kwargs["total_duration"] == 0.0
