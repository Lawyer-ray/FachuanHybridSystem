"""Tests for apps/automation/usecases/court_sms/process_sms.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestProcessSmsUsecase:
    """ProcessSmsUsecase 单元测试。"""

    def test_execute_delegates_to_service(self) -> None:
        """execute 调用 court_sms_service.process_sms。"""
        from apps.automation.usecases.court_sms.process_sms import ProcessSmsUsecase

        mock_service = MagicMock()
        mock_service.process_sms.return_value = {"status": "ok"}
        uc = ProcessSmsUsecase(court_sms_service=mock_service)

        result = uc.execute(sms_id=42, process_options={"retry": True})

        mock_service.process_sms.assert_called_once_with(42, process_options={"retry": True})
        assert result == {"status": "ok"}

    def test_execute_no_options(self) -> None:
        """process_options=None 时也能正常调用。"""
        from apps.automation.usecases.court_sms.process_sms import ProcessSmsUsecase

        mock_service = MagicMock()
        uc = ProcessSmsUsecase(court_sms_service=mock_service)
        uc.execute(sms_id=1)

        mock_service.process_sms.assert_called_once_with(1, process_options=None)

    def test_frozen_dataclass(self) -> None:
        """ProcessSmsUsecase 是 frozen dataclass。"""
        from apps.automation.usecases.court_sms.process_sms import ProcessSmsUsecase

        uc = ProcessSmsUsecase(court_sms_service=MagicMock())
        with pytest.raises(AttributeError):
            uc.court_sms_service = MagicMock()  # type: ignore[misc]


class TestProcessSmsFromMatchingUsecase:
    """ProcessSmsFromMatchingUsecase 单元测试。"""

    def test_execute_delegates_to_process_from_matching(self) -> None:
        """execute 调用 _process_from_matching。"""
        from apps.automation.usecases.court_sms.process_sms import ProcessSmsFromMatchingUsecase

        mock_service = MagicMock()
        mock_service._process_from_matching.return_value = "matched"
        uc = ProcessSmsFromMatchingUsecase(court_sms_service=mock_service)

        result = uc.execute(sms_id=10)
        mock_service._process_from_matching.assert_called_once_with(10)
        assert result == "matched"


class TestProcessSmsFromRenamingUsecase:
    """ProcessSmsFromRenamingUsecase 单元测试。"""

    def test_execute_delegates_to_process_from_renaming(self) -> None:
        """execute 调用 _process_from_renaming。"""
        from apps.automation.usecases.court_sms.process_sms import ProcessSmsFromRenamingUsecase

        mock_service = MagicMock()
        mock_service._process_from_renaming.return_value = "renamed"
        uc = ProcessSmsFromRenamingUsecase(court_sms_service=mock_service)

        result = uc.execute(sms_id=20)
        mock_service._process_from_renaming.assert_called_once_with(20)
        assert result == "renamed"
