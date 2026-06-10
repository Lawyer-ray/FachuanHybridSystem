"""Batch 6 coverage tests for invoice_recognition module."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest


class TestInvoiceParser:
    def _make_parser(self):
        from apps.invoice_recognition.services.invoice_parser import InvoiceParser

        return InvoiceParser()

    def test_parse_empty_text(self):
        parser = self._make_parser()
        result = parser.parse("")
        assert result.invoice_code == ""
        assert result.invoice_number == ""

    def test_detect_category_vat_special(self):
        parser = self._make_parser()
        assert parser.detect_category("增值税专用发票") == "vat_special"

    def test_detect_category_vat_electronic(self):
        parser = self._make_parser()
        assert parser.detect_category("增值税电子普通发票") == "vat_electronic"

    def test_detect_category_vat_normal(self):
        parser = self._make_parser()
        assert parser.detect_category("增值税普通发票") == "vat_normal"

    def test_detect_category_vehicle_sales(self):
        parser = self._make_parser()
        assert parser.detect_category("机动车销售统一发票") == "vehicle_sales"

    def test_detect_category_train_ticket(self):
        parser = self._make_parser()
        assert parser.detect_category("火车票") == "train_ticket"

    def test_detect_category_taxi(self):
        parser = self._make_parser()
        assert parser.detect_category("出租车发票") == "taxi_receipt"

    def test_detect_category_quota_invoice(self):
        parser = self._make_parser()
        assert parser.detect_category("定额发票") == "quota_invoice"

    def test_detect_category_air_itinerary(self):
        parser = self._make_parser()
        assert parser.detect_category("航空运输电子客票") == "air_itinerary"

    def test_detect_category_toll(self):
        parser = self._make_parser()
        assert parser.detect_category("过路费") == "toll_receipt"

    def test_detect_category_other(self):
        parser = self._make_parser()
        assert parser.detect_category("普通收据") == "other"

    def test_parse_date_cn_format(self):
        parser = self._make_parser()
        result = parser._extract_date("开票日期：2023年08月15日")
        assert result == date(2023, 8, 15)

    def test_parse_date_iso_format(self):
        parser = self._make_parser()
        result = parser._extract_date("开票日期：2023-08-15")
        assert result == date(2023, 8, 15)

    def test_parse_date_none(self):
        parser = self._make_parser()
        assert parser._extract_date("没有日期") is None

    def test_parse_decimal(self):
        parser = self._make_parser()
        assert parser._parse_decimal("1,234.56") == Decimal("1234.56")
        assert parser._parse_decimal("invalid") is None

    def test_extract_buyer_name(self):
        parser = self._make_parser()
        result = parser._extract_buyer_name("购买方名称：北京科技有限公司")
        assert "北京科技" in result

    def test_extract_seller_name(self):
        parser = self._make_parser()
        result = parser._extract_seller_name("销售方名称：上海贸易有限公司")
        assert "上海贸易" in result

    def test_extract_project_name(self):
        parser = self._make_parser()
        result = parser._extract_project_name("*信息技术服务*技术开发费")
        assert "技术开发费" in result

    def test_format_to_text(self):
        from apps.invoice_recognition.services.invoice_parser import ParsedInvoice

        parser = self._make_parser()
        invoice = ParsedInvoice(
            invoice_code="011002100111",
            invoice_number="12345678",
            invoice_date=date(2023, 8, 15),
            amount=Decimal("1000.00"),
            tax_amount=Decimal("60.00"),
            total_amount=Decimal("1060.00"),
            buyer_name="北京科技",
            seller_name="上海贸易",
            category="vat_special",
        )
        text = parser.format_to_text(invoice)
        assert "011002100111" in text
        assert "12345678" in text
        assert "2023年" in text
        assert "北京科技" in text

    def test_format_to_text_no_date(self):
        from apps.invoice_recognition.services.invoice_parser import ParsedInvoice

        parser = self._make_parser()
        invoice = ParsedInvoice()
        text = parser.format_to_text(invoice)
        assert "开票日期:" in text

    def test_extract_amount_pattern(self):
        parser = self._make_parser()
        result = parser._extract_amount("合计 ¥1,234.56 ¥60.00")
        assert result == Decimal("1234.56")

    def test_extract_tax_amount(self):
        parser = self._make_parser()
        result = parser._extract_tax_amount("合计 ¥1,234.56 ¥60.00")
        assert result == Decimal("60.00")

    def test_extract_total_amount(self):
        parser = self._make_parser()
        result = parser._extract_total_amount("（小写）¥1060.00")
        assert result == Decimal("1060.00")


class TestParsedInvoice:
    def test_default_values(self):
        from apps.invoice_recognition.services.invoice_parser import ParsedInvoice

        inv = ParsedInvoice()
        assert inv.invoice_code == ""
        assert inv.invoice_number == ""
        assert inv.invoice_date is None
        assert inv.amount is None
        assert inv.category == "other"
