"""测试 GSXT 报告服务

覆盖: apps/automation/services/gsxt/gsxt_report_service.py
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.gsxt.gsxt_report_service import (
    GsxtReportError,
    GsxtReportService,
    start_report_flow,
)


class TestGsxtReportError:
    """测试异常类"""

    def test_is_exception(self) -> None:
        assert issubclass(GsxtReportError, Exception)

    def test_message_preserved(self) -> None:
        err = GsxtReportError("测试错误")
        assert str(err) == "测试错误"

    def test_can_be_caught_as_exception(self) -> None:
        with pytest.raises(Exception):
            raise GsxtReportError("test")

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(GsxtReportError, match="specific"):
            raise GsxtReportError("specific error")


class TestGsxtReportService:
    """测试 GsxtReportService 类"""

    def test_has_start_report_flow_method(self) -> None:
        svc = GsxtReportService()
        assert hasattr(svc, "start_report_flow")
        assert callable(svc.start_report_flow)

    @patch("apps.automation.services.gsxt.gsxt_report_service.start_report_flow")
    def test_class_method_delegates(self, mock_start: MagicMock) -> None:
        svc = GsxtReportService()
        svc.start_report_flow(42)
        mock_start.assert_called_once_with(42)


class TestConstants:
    """测试模块级常量"""

    def test_gsxt_search_url(self) -> None:
        from apps.automation.services.gsxt.gsxt_report_service import GSXT_SEARCH_URL

        assert "gsxt.gov.cn" in GSXT_SEARCH_URL

    def test_captcha_timeout(self) -> None:
        from apps.automation.services.gsxt.gsxt_report_service import CAPTCHA_TIMEOUT

        assert CAPTCHA_TIMEOUT > 0
        assert isinstance(CAPTCHA_TIMEOUT, int)
