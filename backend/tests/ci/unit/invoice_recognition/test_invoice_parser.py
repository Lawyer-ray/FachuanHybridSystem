"""发票识别模块测试。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.invoice_recognition.services.invoice_parser import InvoiceParser, ParsedInvoice
from apps.invoice_recognition.services.recognition_result import RecognitionResult


class TestParsedInvoice:
    """ParsedInvoice 数据类测试。"""

    def test_default_values(self) -> None:
        invoice = ParsedInvoice()
        assert invoice.invoice_code == ""
        assert invoice.invoice_number == ""
        assert invoice.invoice_date is None
        assert invoice.amount is None
        assert invoice.tax_amount is None
        assert invoice.total_amount is None
        assert invoice.buyer_name == ""
        assert invoice.seller_name == ""
        assert invoice.project_name == ""
        assert invoice.category == "other"

    def test_with_values(self) -> None:
        invoice = ParsedInvoice(
            invoice_code="123456789012",
            invoice_number="12345678",
            invoice_date=date(2025, 1, 1),
            amount=Decimal("1000.00"),
            tax_amount=Decimal("60.00"),
            total_amount=Decimal("1060.00"),
            buyer_name="购买方",
            seller_name="销售方",
            project_name="*咨询服务*",
            category="vat_special",
        )
        assert invoice.invoice_code == "123456789012"
        assert invoice.category == "vat_special"


class TestRecognitionResult:
    """RecognitionResult 数据类测试。"""

    def test_success_result(self) -> None:
        invoice = ParsedInvoice(invoice_code="123")
        result = RecognitionResult(filename="test.pdf", success=True, data=invoice)
        assert result.success is True
        assert result.data is not None
        assert result.error is None

    def test_failure_result(self) -> None:
        result = RecognitionResult(filename="test.pdf", success=False, error="识别失败")
        assert result.success is False
        assert result.data is None
        assert result.error == "识别失败"


class TestInvoiceParser:
    """InvoiceParser 测试。"""

    def setup_method(self) -> None:
        self.parser = InvoiceParser()

    def test_parse_full_invoice(self) -> None:
        """解析完整发票文本。"""
        text = (
            "发票代码：123456789012\n"
            "发票号码：12345678\n"
            "开票日期：2025年01月15日\n"
            "合 计 ¥1,000.00 ¥60.00\n"
            "（小写） ¥1,060.00\n"
            "购买方名称：某某科技有限公司\n"
            "销售方名称：某某服务有限公司\n"
            "*咨询服务*技术咨询费\n"
            "增值税专用发票"
        )
        result = self.parser.parse(text)
        assert result.invoice_code == "123456789012"
        assert result.invoice_number == "12345678"
        assert result.invoice_date == date(2025, 1, 15)
        assert result.amount == Decimal("1000.00")
        assert result.tax_amount == Decimal("60.00")
        assert result.total_amount == Decimal("1060.00")
        assert result.category == "vat_special"

    def test_parse_empty_text(self) -> None:
        """解析空文本。"""
        result = self.parser.parse("")
        assert result.invoice_code == ""
        assert result.invoice_number == ""
        assert result.invoice_date is None
        assert result.category == "other"

    def test_detect_category_vat_special(self) -> None:
        assert self.parser.detect_category("增值税专用发票") == "vat_special"

    def test_detect_category_vat_electronic(self) -> None:
        assert self.parser.detect_category("增值税电子普通发票") == "vat_electronic"

    def test_detect_category_vat_normal(self) -> None:
        assert self.parser.detect_category("增值税普通发票") == "vat_normal"

    def test_detect_category_vehicle_sales(self) -> None:
        assert self.parser.detect_category("机动车销售统一发票") == "vehicle_sales"

    def test_detect_category_train_ticket(self) -> None:
        assert self.parser.detect_category("铁路电子客票") == "train_ticket"

    def test_detect_category_taxi_receipt(self) -> None:
        assert self.parser.detect_category("出租车发票") == "taxi_receipt"

    def test_detect_category_quota_invoice(self) -> None:
        assert self.parser.detect_category("定额发票") == "quota_invoice"

    def test_detect_category_air_itinerary(self) -> None:
        assert self.parser.detect_category("航空运输电子客票") == "air_itinerary"

    def test_detect_category_toll_receipt(self) -> None:
        assert self.parser.detect_category("通行费发票") == "toll_receipt"

    def test_detect_category_other(self) -> None:
        assert self.parser.detect_category("普通收据") == "other"

    def test_extract_date_cn_format(self) -> None:
        """中文日期格式。"""
        result = self.parser._extract_date("开票日期：2025年01月15日")
        assert result == date(2025, 1, 15)

    def test_extract_date_iso_format(self) -> None:
        """ISO 日期格式。"""
        result = self.parser._extract_date("开票日期：2025-01-15")
        assert result == date(2025, 1, 15)

    def test_extract_date_invalid(self) -> None:
        """无效日期。"""
        result = self.parser._extract_date("无日期信息")
        assert result is None

    def test_extract_amount(self) -> None:
        result = self.parser._extract_amount("合 计 ¥1,234.56 ¥78.90")
        assert result == Decimal("1234.56")

    def test_extract_tax_amount(self) -> None:
        result = self.parser._extract_tax_amount("合 计 ¥1,234.56 ¥78.90")
        assert result == Decimal("78.90")

    def test_extract_total_amount(self) -> None:
        result = self.parser._extract_total_amount("（小写） ¥1,313.46")
        assert result == Decimal("1313.46")

    def test_extract_buyer_name(self) -> None:
        result = self.parser._extract_buyer_name("购买方名称：某某科技有限公司")
        assert result == "某某科技有限公司"

    def test_extract_buyer_name_short(self) -> None:
        result = self.parser._extract_buyer_name("购方名称：某某公司")
        assert result == "某某公司"

    def test_extract_seller_name(self) -> None:
        result = self.parser._extract_seller_name("销售方名称：某某服务有限公司")
        assert result == "某某服务有限公司"

    def test_extract_project_name(self) -> None:
        result = self.parser._extract_project_name("*咨询服务*技术咨询费")
        assert result == "技术咨询费"

    def test_format_to_text(self) -> None:
        """格式化输出。"""
        invoice = ParsedInvoice(
            invoice_code="123",
            invoice_number="456",
            invoice_date=date(2025, 1, 15),
            amount=Decimal("1000.00"),
            tax_amount=Decimal("60.00"),
            total_amount=Decimal("1060.00"),
            buyer_name="购买方",
            seller_name="销售方",
            category="vat_special",
        )
        text = self.parser.format_to_text(invoice)
        assert "发票代码:123" in text
        assert "发票号码:456" in text
        assert "2025年01月15日" in text
        assert "1000.00" in text
        assert "vat_special" in text

    def test_format_to_text_empty_date(self) -> None:
        """空日期格式化。"""
        invoice = ParsedInvoice()
        text = self.parser.format_to_text(invoice)
        assert "开票日期:" in text

    def test_format_to_text_none_amount(self) -> None:
        """None 金额格式化。"""
        invoice = ParsedInvoice()
        text = self.parser.format_to_text(invoice)
        assert "金额:" in text
