"""Tests for invoice_recognition services: invoice_parser."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.invoice_recognition.services.invoice_parser import InvoiceParser, ParsedInvoice


# ---------------------------------------------------------------------------
# InvoiceParser
# ---------------------------------------------------------------------------


class TestInvoiceParserCategory:
    """Tests for InvoiceParser.detect_category."""

    def _svc(self) -> InvoiceParser:
        return InvoiceParser()

    def test_vat_special(self) -> None:
        assert self._svc().detect_category("增值税专用发票") == "vat_special"

    def test_vat_electronic(self) -> None:
        assert self._svc().detect_category("增值税电子普通发票") == "vat_electronic"

    def test_electronic_plain(self) -> None:
        assert self._svc().detect_category("电子普通发票") == "vat_electronic"

    def test_vat_normal(self) -> None:
        assert self._svc().detect_category("增值税普通发票") == "vat_normal"

    def test_vehicle_sales(self) -> None:
        assert self._svc().detect_category("机动车销售统一发票") == "vehicle_sales"

    def test_train_ticket(self) -> None:
        assert self._svc().detect_category("铁路电子客票") == "train_ticket"

    def test火车票(self) -> None:
        assert self._svc().detect_category("火车票") == "train_ticket"

    def test_taxi(self) -> None:
        assert self._svc().detect_category("出租车发票") == "taxi_receipt"

    def test_taxi_short(self) -> None:
        assert self._svc().detect_category("出租车") == "taxi_receipt"

    def test_quota_invoice(self) -> None:
        assert self._svc().detect_category("定额发票") == "quota_invoice"

    def test_air_itinerary(self) -> None:
        assert self._svc().detect_category("航空运输电子客票") == "air_itinerary"

    def test_air_ticket(self) -> None:
        assert self._svc().detect_category("飞机行程单") == "air_itinerary"

    def test_toll(self) -> None:
        assert self._svc().detect_category("过路费") == "toll_receipt"

    def test通行费(self) -> None:
        assert self._svc().detect_category("通行费") == "toll_receipt"

    def test_other(self) -> None:
        assert self._svc().detect_category("random text") == "other"


class TestInvoiceParserExtractCode:
    def test_found(self) -> None:
        p = InvoiceParser()
        assert p._extract_invoice_code("发票代码：1100231050") == "1100231050"

    def test_not_found(self) -> None:
        p = InvoiceParser()
        assert p._extract_invoice_code("no code here") == ""


class TestInvoiceParserExtractNumber:
    def test_8digit(self) -> None:
        p = InvoiceParser()
        assert p._extract_invoice_number("发票号码：12345678") == "12345678"

    def test_20digit(self) -> None:
        p = InvoiceParser()
        assert p._extract_invoice_number("No. 12345678901234567890") == "12345678901234567890"


class TestInvoiceParserExtractDate:
    def test_cn_format(self) -> None:
        p = InvoiceParser()
        assert p._extract_date("开票日期：2024年03月15日") == date(2024, 3, 15)

    def test_iso_format(self) -> None:
        p = InvoiceParser()
        assert p._extract_date("date: 2024-03-15") == date(2024, 3, 15)

    def test_no_date(self) -> None:
        p = InvoiceParser()
        assert p._extract_date("no date") is None

    def test_invalid_cn_date(self) -> None:
        p = InvoiceParser()
        assert p._extract_date("2024年13月40日") is None

    def test_invalid_iso_date(self) -> None:
        p = InvoiceParser()
        assert p._extract_date("2024-13-40") is None


class TestInvoiceParserExtractAmount:
    def test_found(self) -> None:
        p = InvoiceParser()
        text = "合 计 ¥1,000.00 ¥60.00"
        assert p._extract_amount(text) == Decimal("1000.00")

    def test_not_found(self) -> None:
        p = InvoiceParser()
        assert p._extract_amount("no amount") is None


class TestInvoiceParserExtractTaxAmount:
    def test_found(self) -> None:
        p = InvoiceParser()
        text = "合 计 ¥1,000.00 ¥60.00"
        assert p._extract_tax_amount(text) == Decimal("60.00")


class TestInvoiceParserExtractTotalAmount:
    def test_found(self) -> None:
        p = InvoiceParser()
        text = "(小写) ¥1,060.00"
        assert p._extract_total_amount(text) == Decimal("1060.00")


class TestInvoiceParserExtractBuyerName:
    def test_full_pattern(self) -> None:
        p = InvoiceParser()
        assert p._extract_buyer_name("购买方名称：北京科技有限公司") == "北京科技有限公司"

    def test_short_pattern(self) -> None:
        p = InvoiceParser()
        assert p._extract_buyer_name("购方名称：上海贸易有限公司") == "上海贸易有限公司"

    def test_name_only(self) -> None:
        p = InvoiceParser()
        assert p._extract_buyer_name("名称：深圳公司") == "深圳公司"

    def test_not_found(self) -> None:
        p = InvoiceParser()
        assert p._extract_buyer_name("no buyer") == ""


class TestInvoiceParserExtractSellerName:
    def test_full_pattern(self) -> None:
        p = InvoiceParser()
        assert p._extract_seller_name("销售方名称：广州有限公司") == "广州有限公司"

    def test_short_pattern(self) -> None:
        p = InvoiceParser()
        assert p._extract_seller_name("销方名称：南京有限公司") == "南京有限公司"

    def test_not_found(self) -> None:
        p = InvoiceParser()
        assert p._extract_seller_name("no seller") == ""


class TestInvoiceParserExtractProjectName:
    def test_found(self) -> None:
        p = InvoiceParser()
        assert p._extract_project_name("*服务费*信息技术服务") == "信息技术服务"

    def test_not_found(self) -> None:
        p = InvoiceParser()
        assert p._extract_project_name("no project") == ""


class TestInvoiceParserParseFull:
    def test_parse_complete_invoice(self) -> None:
        p = InvoiceParser()
        text = (
            "增值税电子普通发票\n"
            "发票代码：1100231050\n"
            "发票号码：00123456\n"
            "开票日期：2024年03月15日\n"
            "购买方名称：北京科技有限公司\n"
            "销售方名称：上海贸易有限公司\n"
            "*服务费*信息技术服务\n"
            "合 计 ¥1,000.00 ¥60.00\n"
            "(小写) ¥1,060.00\n"
        )
        inv = p.parse(text)
        assert inv.invoice_code == "1100231050"
        assert inv.invoice_number == "00123456"
        assert inv.invoice_date == date(2024, 3, 15)
        assert inv.buyer_name == "北京科技有限公司"
        assert inv.seller_name == "上海贸易有限公司"
        assert inv.project_name == "信息技术服务"
        assert inv.category == "vat_electronic"
        assert inv.amount == Decimal("1000.00")
        assert inv.tax_amount == Decimal("60.00")
        assert inv.total_amount == Decimal("1060.00")

    def test_parse_empty_text(self) -> None:
        p = InvoiceParser()
        inv = p.parse("")
        assert inv.invoice_code == ""
        assert inv.category == "other"


class TestInvoiceParserFormatToText:
    def test_with_all_fields(self) -> None:
        p = InvoiceParser()
        inv = ParsedInvoice(
            invoice_code="1234567890",
            invoice_number="12345678",
            invoice_date=date(2024, 1, 1),
            amount=Decimal("100.00"),
            tax_amount=Decimal("6.00"),
            total_amount=Decimal("106.00"),
            buyer_name="buyer",
            seller_name="seller",
            category="vat_special",
        )
        text = p.format_to_text(inv)
        assert "发票代码:1234567890" in text
        assert "发票号码:12345678" in text
        assert "开票日期:2024年01月01日" in text
        assert "金额:100.00" in text
        assert "税额:6.00" in text
        assert "价税合计:106.00" in text
        assert "购买方名称:buyer" in text
        assert "销售方名称:seller" in text
        assert "发票类目:vat_special" in text

    def test_with_no_amounts(self) -> None:
        p = InvoiceParser()
        inv = ParsedInvoice()
        text = p.format_to_text(inv)
        assert "开票日期:" in text
        assert "金额:" in text
        assert "税额:" in text
        assert "价税合计:" in text
