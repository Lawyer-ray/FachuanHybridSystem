"""GsxtReportService 测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from apps.automation.services.gsxt.gsxt_report_service import (
    GsxtReportError,
    GsxtReportService,
)


class TestGsxtReportError:
    """GsxtReportError 异常测试。"""

    def test_creation(self) -> None:
        e = GsxtReportError("报告失败")
        assert str(e) == "报告失败"


class TestGsxtReportService:
    """GsxtReportService 测试。"""

    def test_start_report_flow(self) -> None:
        svc = GsxtReportService()
        with patch("apps.automation.services.gsxt.gsxt_report_service.start_report_flow") as mock_start:
            svc.start_report_flow(42)
            mock_start.assert_called_once_with(42)

    @patch("apps.automation.services.gsxt.gsxt_report_service.threading.Thread")
    def test_start_report_flow_function(self, mock_thread_cls: MagicMock) -> None:
        from apps.automation.services.gsxt.gsxt_report_service import start_report_flow
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        start_report_flow(42)
        mock_thread_cls.assert_called_once()
        mock_thread.start.assert_called_once()
