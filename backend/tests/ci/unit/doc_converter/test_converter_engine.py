"""文档转换引擎测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from pathlib import Path

from apps.doc_converter.services.engine import batch_convert, convert_single


class TestConvertSingle:
    """convert_single 测试。"""

    @patch("apps.doc_converter.services.engine.find_libreoffice")
    def test_no_libreoffice(self, mock_find) -> None:
        """未找到 LibreOffice 抛出异常。"""
        mock_find.return_value = None
        try:
            convert_single("/path/to/file.doc", "/tmp/output")
            assert False, "应抛出 RuntimeError"
        except RuntimeError as e:
            assert "LibreOffice" in str(e)


class TestBatchConvert:
    """batch_convert 测试。"""

    @patch("apps.doc_converter.services.engine.find_libreoffice")
    def test_empty_input(self, mock_find) -> None:
        """空输入返回空字典。"""
        result = batch_convert([], "/tmp/output")
        assert result == {}

    @patch("apps.doc_converter.services.engine.find_libreoffice")
    def test_no_libreoffice(self, mock_find) -> None:
        """未找到 LibreOffice 抛出异常。"""
        mock_find.return_value = None
        try:
            batch_convert(["/path/to/file.doc"], "/tmp/output")
            assert False, "应抛出 RuntimeError"
        except RuntimeError as e:
            assert "LibreOffice" in str(e)
