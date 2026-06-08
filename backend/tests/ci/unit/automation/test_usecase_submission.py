"""Tests for apps/automation/usecases/court_sms/submission.py."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest


class TestSubmitSmsUsecase:
    """SubmitSmsUsecase 单元测试。"""

    def test_execute_delegates_to_submit_sms(self) -> None:
        """execute 调用 court_sms_service.submit_sms。"""
        from apps.automation.usecases.court_sms.submission import SubmitSmsUsecase

        mock_service = MagicMock()
        mock_service.submit_sms.return_value = {"submitted": True}
        uc = SubmitSmsUsecase(court_sms_service=mock_service)

        now = datetime(2026, 6, 7, 10, 30)
        result = uc.execute(content="短信内容", received_at=now)

        mock_service.submit_sms.assert_called_once_with(content="短信内容", received_at=now)
        assert result == {"submitted": True}

    def test_execute_without_received_at(self) -> None:
        """received_at=None 时也能正常调用。"""
        from apps.automation.usecases.court_sms.submission import SubmitSmsUsecase

        mock_service = MagicMock()
        uc = SubmitSmsUsecase(court_sms_service=mock_service)
        uc.execute(content="test")

        mock_service.submit_sms.assert_called_once_with(content="test", received_at=None)

    def test_frozen_dataclass(self) -> None:
        """SubmitSmsUsecase 是 frozen dataclass。"""
        from apps.automation.usecases.court_sms.submission import SubmitSmsUsecase

        uc = SubmitSmsUsecase(court_sms_service=MagicMock())
        with pytest.raises(AttributeError):
            uc.court_sms_service = MagicMock()  # type: ignore[misc]


class TestAssignCaseUsecase:
    """AssignCaseUsecase 单元测试。"""

    def test_execute_delegates_to_assign_case(self) -> None:
        """execute 调用 court_sms_service.assign_case。"""
        from apps.automation.usecases.court_sms.submission import AssignCaseUsecase

        mock_service = MagicMock()
        mock_service.assign_case.return_value = {"assigned": True}
        uc = AssignCaseUsecase(court_sms_service=mock_service)

        result = uc.execute(sms_id=10, case_id=20)
        mock_service.assign_case.assert_called_once_with(sms_id=10, case_id=20)
        assert result == {"assigned": True}

    def test_frozen_dataclass(self) -> None:
        """AssignCaseUsecase 是 frozen dataclass。"""
        from apps.automation.usecases.court_sms.submission import AssignCaseUsecase

        uc = AssignCaseUsecase(court_sms_service=MagicMock())
        with pytest.raises(AttributeError):
            uc.court_sms_service = MagicMock()  # type: ignore[misc]

    def test_propagates_service_exception(self) -> None:
        """service.assign_case 抛异常时向外传播。"""
        from apps.automation.usecases.court_sms.submission import AssignCaseUsecase

        mock_service = MagicMock()
        mock_service.assign_case.side_effect = ValueError("case not found")
        uc = AssignCaseUsecase(court_sms_service=mock_service)

        with pytest.raises(ValueError, match="case not found"):
            uc.execute(sms_id=1, case_id=999)
