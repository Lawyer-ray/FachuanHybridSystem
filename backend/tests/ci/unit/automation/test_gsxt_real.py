"""GSXT login and report service tests with mocked external dependencies."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from apps.automation.services.gsxt.gsxt_login_service import (
    GsxtLoginError,
    GsxtLoginService,
    start_login_gsxt,
)
from apps.automation.services.gsxt.gsxt_report_service import (
    GsxtReportError,
    GsxtReportService,
    start_report_flow,
)


class TestGsxtLoginService:
    """GsxtLoginService tests."""

    def test_gsxt_login_service_class(self):
        svc = GsxtLoginService()
        assert hasattr(svc, "start_login")

    @patch("apps.automation.services.gsxt.gsxt_login_service._try_reverse_login")
    @patch("apps.automation.services.gsxt.gsxt_login_service.threading.Thread")
    def test_start_login_gsxt_playwright_fallback(self, mock_thread, mock_reverse):
        mock_reverse.return_value = False
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance

        credential = MagicMock()
        credential.account = "test"
        credential.password = "pass"

        start_login_gsxt(credential, task_id=1)
        mock_thread_instance.start.assert_called_once()

    @patch("apps.automation.services.gsxt.gsxt_login_service._try_reverse_login")
    def test_start_login_gsxt_reverse_success(self, mock_reverse):
        mock_reverse.return_value = True
        credential = MagicMock()
        start_login_gsxt(credential, task_id=1)
        mock_reverse.assert_called_once_with(credential, 1)


class TestGsxtReportService:
    """GsxtReportService tests."""

    def test_gsxt_report_service_class(self):
        svc = GsxtReportService()
        assert hasattr(svc, "start_report_flow")

    @patch("apps.automation.services.gsxt.gsxt_report_service.threading.Thread")
    def test_start_report_flow(self, mock_thread):
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance
        start_report_flow(task_id=1)
        mock_thread_instance.start.assert_called_once()


class TestGsxtExceptions:
    def test_login_error(self):
        exc = GsxtLoginError("login failed")
        assert str(exc) == "login failed"

    def test_report_error(self):
        exc = GsxtReportError("report failed")
        assert str(exc) == "report failed"
