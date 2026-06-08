"""SMS 仓库和提交服务测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.automation.services.sms.court_sms_repository import CourtSMSRepository


class TestCourtSMSRepository:
    """CourtSMSRepository 测试。"""

    def setup_method(self) -> None:
        self.repo = CourtSMSRepository()

    @patch("apps.automation.services.sms.court_sms_repository.CourtSMS")
    def test_get_by_id_found(self, mock_model) -> None:
        """找到短信记录。"""
        mock_sms = MagicMock()
        mock_model.objects.filter.return_value.first.return_value = mock_sms
        result = self.repo.get_by_id(sms_id=1)
        assert result == mock_sms

    @patch("apps.automation.services.sms.court_sms_repository.CourtSMS")
    def test_get_by_id_not_found(self, mock_model) -> None:
        """未找到短信记录抛出异常。"""
        mock_model.objects.filter.return_value.first.return_value = None
        from apps.core.exceptions import NotFoundError
        try:
            self.repo.get_by_id(sms_id=999)
            raise AssertionError("应抛出 NotFoundError")
        except NotFoundError:
            pass

    @patch("apps.automation.services.sms.court_sms_repository.CourtSMS")
    def test_get_by_id_or_none_found(self, mock_model) -> None:
        """找到短信记录。"""
        mock_sms = MagicMock()
        mock_model.objects.filter.return_value.first.return_value = mock_sms
        result = self.repo.get_by_id_or_none(sms_id=1)
        assert result == mock_sms

    @patch("apps.automation.services.sms.court_sms_repository.CourtSMS")
    def test_get_by_id_or_none_not_found(self, mock_model) -> None:
        """未找到返回 None。"""
        mock_model.objects.filter.return_value.first.return_value = None
        result = self.repo.get_by_id_or_none(sms_id=999)
        assert result is None

    def test_reset_retry_fields(self) -> None:
        """重置重试字段。"""
        sms = MagicMock()
        self.repo.reset_retry_fields(sms=sms)
        assert sms.scraper_task is None
        assert sms.case is None
        assert sms.case_log is None
        assert sms.notification_results is None

    def test_set_error(self) -> None:
        """设置错误信息。"""
        sms = MagicMock()
        self.repo.set_error(sms=sms, message="测试错误")
        assert sms.error_message == "测试错误"
        sms.save.assert_called_once()

    def test_clear_error(self) -> None:
        """清除错误信息。"""
        sms = MagicMock()
        self.repo.clear_error(sms=sms)
        assert sms.error_message is None
        sms.save.assert_called_once()

    def test_set_status(self) -> None:
        """设置状态。"""
        sms = MagicMock()
        self.repo.set_status(sms=sms, status="failed", error_message="错误")
        assert sms.status == "failed"
        assert sms.error_message == "错误"
        sms.save.assert_called_once()
