"""
Tests for apps.invoice_recognition.services — 发票识别服务
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestRecognitionResult:
    """RecognitionResult 数据类测试"""

    def test_success_result(self) -> None:
        from apps.invoice_recognition.services.recognition_result import RecognitionResult

        result = RecognitionResult(filename="invoice.pdf", success=True)
        assert result.success is True
        assert result.data is None
        assert result.error is None

    def test_failure_result(self) -> None:
        from apps.invoice_recognition.services.recognition_result import RecognitionResult

        result = RecognitionResult(filename="bad.pdf", success=False, error="parse error")
        assert result.success is False
        assert result.error == "parse error"


class TestInvoiceRecognitionModules:
    """发票识别模块可导入性测试"""

    def test_invoice_parser_importable(self) -> None:
        from apps.invoice_recognition.services.invoice_parser import ParsedInvoice

        assert ParsedInvoice is not None

    def test_wiring_importable(self) -> None:
        from apps.invoice_recognition.services import wiring

        assert wiring is not None
