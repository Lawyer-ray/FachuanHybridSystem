"""GSXT 模块测试 - 邮箱服务、报告服务数据处理。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.automation.services.gsxt.gsxt_email_service import (
    GSXT_REPORT_FOLDER,
    GsxtEmailService,
    _decode_header_value,
)
from apps.automation.services.gsxt.gsxt_report_service import (
    GsxtReportError,
    GsxtReportService,
)


class TestDecodeHeaderValue:
    """测试邮件头解码。"""

    def test_decode_none(self) -> None:
        assert _decode_header_value(None) == ""

    def test_decode_empty(self) -> None:
        assert _decode_header_value("") == ""

    def test_decode_plain_ascii(self) -> None:
        result = _decode_header_value("test.pdf")
        assert result == "test.pdf"

    def test_decode_chinese_filename(self) -> None:
        """解码中文文件名。"""
        from email.header import Header

        encoded = str(Header("企业信用报告.pdf", "utf-8"))
        result = _decode_header_value(encoded)
        assert "企业信用报告" in result

    def test_decode_mixed_encoding(self) -> None:
        """混合编码解码。"""
        result = _decode_header_value("simple.txt")
        assert result == "simple.txt"


class TestGsxtEmailService:
    """测试 GsxtEmailService。"""

    def test_class_instantiation(self) -> None:
        service = GsxtEmailService()
        assert service is not None

    @patch("apps.automation.services.gsxt.gsxt_email_service._connect_163")
    def test_fetch_report_attachment_no_messages(self, mock_connect: MagicMock) -> None:
        """无邮件返回 None。"""
        mock_mail = MagicMock()
        mock_mail.select.return_value = ("OK", [b"0"])
        mock_mail.search.return_value = ("OK", [b""])
        mock_connect.return_value = mock_mail

        service = GsxtEmailService()
        result = service.fetch_report_attachment("user@163.com", "pass", "测试公司")
        assert result is None

    @patch("apps.automation.services.gsxt.gsxt_email_service._connect_163")
    def test_fetch_report_folder_not_exist_fallback(self, mock_connect: MagicMock) -> None:
        """专用文件夹不存在时回退到 INBOX。"""
        mock_mail = MagicMock()
        mock_mail.select.side_effect = [("NO", [b""]), ("OK", [b"0"])]
        mock_mail.search.return_value = ("OK", [b""])
        mock_connect.return_value = mock_mail

        service = GsxtEmailService()
        result = service.fetch_report_attachment("user@163.com", "pass", "测试公司")
        assert result is None

    @patch("apps.automation.services.gsxt.gsxt_email_service._connect_163")
    def test_fetch_report_connection_error(self, mock_connect: MagicMock) -> None:
        """连接错误返回 None。"""
        mock_connect.side_effect = Exception("连接失败")
        service = GsxtEmailService()
        result = service.fetch_report_attachment("user@163.com", "pass", "测试公司")
        assert result is None

    def test_gsxt_report_folder_constant(self) -> None:
        """验证专用文件夹常量。"""
        assert GSXT_REPORT_FOLDER == "&TwFOGk,hdShP4WBv-"


class TestGsxtReportError:
    """测试 GSXT 报告异常。"""

    def test_error_message(self) -> None:
        exc = GsxtReportError("报告申请失败")
        assert str(exc) == "报告申请失败"

    def test_error_is_exception(self) -> None:
        assert issubclass(GsxtReportError, Exception)


class TestGsxtReportService:
    """测试 GsxtReportService 门面类。"""

    def test_instantiation(self) -> None:
        service = GsxtReportService()
        assert service is not None

    def test_has_start_report_flow_method(self) -> None:
        service = GsxtReportService()
        assert hasattr(service, "start_report_flow")
        assert callable(service.start_report_flow)
