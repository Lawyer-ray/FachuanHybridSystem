"""Extended tests for invoice_recognition services - invoice_parser."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.invoice_recognition.services.invoice_parser import InvoiceParser, ParsedInvoice


class TestInvoiceParser:
    def setup_method(self):
        self.parser = InvoiceParser()

    def test_parse_empty(self):
        result = self.parser.parse("")
        assert result.invoice_code == ""
        assert result.invoice_number == ""
        assert result.invoice_date is None
        assert result.amount is None
        assert result.category == "other"

    def test_detect_category_vat_special(self):
        assert self.parser.detect_category("增值税专用发票") == "vat_special"

    def test_detect_category_vat_electronic(self):
        assert self.parser.detect_category("增值税电子普通发票") == "vat_electronic"

    def test_detect_category_vat_normal(self):
        assert self.parser.detect_category("增值税普通发票") == "vat_normal"

    def test_detect_category_vehicle(self):
        assert self.parser.detect_category("机动车销售统一发票") == "vehicle_sales"

    def test_detect_category_train(self):
        assert self.parser.detect_category("铁路电子客票") == "train_ticket"

    def test_detect_category_taxi(self):
        assert self.parser.detect_category("出租车发票") == "taxi_receipt"

    def test_detect_category_quota(self):
        assert self.parser.detect_category("定额发票") == "quota_invoice"

    def test_detect_category_air(self):
        assert self.parser.detect_category("航空运输电子客票") == "air_itinerary"

    def test_detect_category_toll(self):
        assert self.parser.detect_category("过路费发票") == "toll_receipt"

    def test_detect_category_other(self):
        assert self.parser.detect_category("普通文本") == "other"

    def test_parse_date_cn(self):
        result = self.parser._extract_date("开票日期：2024年01月15日")
        assert result == date(2024, 1, 15)

    def test_parse_date_iso(self):
        result = self.parser._extract_date("开票日期：2024-01-15")
        assert result == date(2024, 1, 15)

    def test_parse_date_invalid(self):
        result = self.parser._extract_date("无日期信息")
        assert result is None

    def test_parse_date_invalid_cn(self):
        result = self.parser._extract_date("2024年13月32日")
        assert result is None

    def test_extract_amount(self):
        result = self.parser._extract_amount("合计 ¥1,234.56 ¥100.00")
        assert result == Decimal("1234.56")

    def test_extract_amount_none(self):
        result = self.parser._extract_amount("无金额")
        assert result is None

    def test_extract_total_amount(self):
        result = self.parser._extract_total_amount("（小写）¥1,234.56")
        assert result == Decimal("1234.56")

    def test_extract_total_amount_none(self):
        result = self.parser._extract_total_amount("无金额")
        assert result is None

    def test_extract_buyer_name(self):
        result = self.parser._extract_buyer_name("购买方名称：测试公司")
        assert result == "测试公司"

    def test_extract_buyer_name_short(self):
        result = self.parser._extract_buyer_name("购方名称：测试公司")
        assert result == "测试公司"

    def test_extract_buyer_name_none(self):
        result = self.parser._extract_buyer_name("无购买方")
        assert result == ""

    def test_extract_seller_name(self):
        result = self.parser._extract_seller_name("销售方名称：供应商公司")
        assert result == "供应商公司"

    def test_extract_seller_name_short(self):
        result = self.parser._extract_seller_name("销方名称：供应商公司")
        assert result == "供应商公司"

    def test_extract_seller_name_none(self):
        result = self.parser._extract_seller_name("无销售方")
        assert result == ""

    def test_extract_project_name(self):
        result = self.parser._extract_project_name("*信息技术服务*软件开发服务费")
        assert result == "软件开发服务费"

    def test_extract_project_name_none(self):
        result = self.parser._extract_project_name("无项目名称")
        assert result == ""

    def test_extract_invoice_code(self):
        result = self.parser._extract_invoice_code("发票代码：123456789012")
        assert result == "123456789012"

    def test_extract_invoice_code_none(self):
        result = self.parser._extract_invoice_code("无代码")
        assert result == ""

    def test_extract_invoice_number(self):
        result = self.parser._extract_invoice_number("发票号码：12345678")
        assert result == "12345678"

    def test_extract_invoice_number_none(self):
        result = self.parser._extract_invoice_number("无号码")
        assert result == ""

    def test_format_to_text(self):
        parsed = ParsedInvoice(
            invoice_code="123456",
            invoice_number="789012",
            invoice_date=date(2024, 1, 15),
            amount=Decimal("1000.00"),
            tax_amount=Decimal("60.00"),
            total_amount=Decimal("1060.00"),
            buyer_name="买方",
            seller_name="卖方",
            category="vat_special",
        )
        text = self.parser.format_to_text(parsed)
        assert "发票代码:123456" in text
        assert "发票号码:789012" in text
        assert "2024年" in text
        assert "买方" in text
        assert "卖方" in text
        assert "vat_special" in text

    def test_format_to_text_no_date(self):
        parsed = ParsedInvoice(
            invoice_code="123456",
            invoice_number="789012",
            invoice_date=None,
            amount=None,
            tax_amount=None,
            total_amount=None,
            buyer_name="买方",
            seller_name="卖方",
            category="other",
        )
        text = self.parser.format_to_text(parsed)
        assert "开票日期:" in text
        assert "金额:" in text

    def test_parse_decimal_with_commas(self):
        result = self.parser._parse_decimal("1,234.56")
        assert result == Decimal("1234.56")

    def test_parse_decimal_invalid(self):
        result = self.parser._parse_decimal("abc")
        assert result is None


class TestParsedInvoice:
    def test_defaults(self):
        invoice = ParsedInvoice()
        assert invoice.invoice_code == ""
        assert invoice.invoice_number == ""
        assert invoice.invoice_date is None
        assert invoice.amount is None
        assert invoice.category == "other"

    def test_frozen(self):
        invoice = ParsedInvoice(invoice_code="123")
        with pytest.raises(AttributeError):
            invoice.invoice_code = "456"  # type: ignore[misc]
