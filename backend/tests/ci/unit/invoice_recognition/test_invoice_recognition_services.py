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

# ---------------------------------------------------------------------------
# InvoiceParser extended tests
# ---------------------------------------------------------------------------

class TestInvoiceParserExtended:
    def _make_parser(self):
        from apps.invoice_recognition.services.invoice_parser import InvoiceParser
        return InvoiceParser()

    def test_detect_category_vat_special(self):
        parser = self._make_parser()
        assert parser.detect_category("增值税专用发票") == "vat_special"

    def test_detect_category_vat_electronic(self):
        parser = self._make_parser()
        assert parser.detect_category("增值税电子普通发票") == "vat_electronic"

    def test_detect_category_train(self):
        parser = self._make_parser()
        assert parser.detect_category("铁路电子客票") == "train_ticket"

    def test_detect_category_taxi(self):
        parser = self._make_parser()
        assert parser.detect_category("出租车发票") == "taxi_receipt"

    def test_detect_category_other(self):
        parser = self._make_parser()
        assert parser.detect_category("random text") == "other"

    def test_parse_basic_text(self):
        parser = self._make_parser()
        text = "发票代码：1234567890 发票号码：12345678"
        result = parser.parse(text)
        assert result.invoice_code == "1234567890"

    def test_parse_date_chinese(self):
        parser = self._make_parser()
        text = "开票日期：2026年01月15日"
        result = parser.parse(text)
        assert result.invoice_date is not None
        assert result.invoice_date.year == 2026

    def test_parse_date_iso(self):
        parser = self._make_parser()
        text = "开票日期：2026-01-15"
        result = parser.parse(text)
        assert result.invoice_date is not None

    def test_parse_amount(self):
        parser = self._make_parser()
        text = "合计 ¥1000.00 ¥60.00"
        result = parser.parse(text)
        assert result.amount is not None

    def test_parse_total_amount(self):
        parser = self._make_parser()
        text = "（小写）¥1060.00"
        result = parser.parse(text)
        assert result.total_amount is not None

    def test_parse_buyer_name(self):
        parser = self._make_parser()
        text = "购买方名称：某科技有限公司"
        result = parser.parse(text)
        assert "某科技有限公司" in result.buyer_name

    def test_parse_seller_name(self):
        parser = self._make_parser()
        text = "销售方名称：某供应商有限公司"
        result = parser.parse(text)
        assert "某供应商有限公司" in result.seller_name

    def test_parse_empty_text(self):
        parser = self._make_parser()
        result = parser.parse("")
        assert result.invoice_code == ""
        assert result.invoice_number == ""

    def test_format_to_text(self):
        from apps.invoice_recognition.services.invoice_parser import ParsedInvoice
        from datetime import date
        from decimal import Decimal
        parser = self._make_parser()
        parsed = ParsedInvoice(
            invoice_code="1234567890",
            invoice_number="12345678",
            invoice_date=date(2026, 1, 15),
            amount=Decimal("1000.00"),
            tax_amount=Decimal("60.00"),
            total_amount=Decimal("1060.00"),
            buyer_name="买方",
            seller_name="卖方",
            category="vat_special",
        )
        text = parser.format_to_text(parsed)
        assert "1234567890" in text
        assert "买方" in text

    def test_parse_project_name(self):
        parser = self._make_parser()
        text = "*信息技术服务*软件开发"
        result = parser.parse(text)
        assert "软件开发" in result.project_name
