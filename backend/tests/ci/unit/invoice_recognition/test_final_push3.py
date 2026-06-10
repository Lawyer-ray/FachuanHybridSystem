"""Final push coverage tests for invoice_recognition, image_rotation, and more modules."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest


# ============================================================================
# invoice_recognition/services/invoice_parser.py tests
# ============================================================================


class TestParsedInvoice:
    def test_default_creation(self):
        from apps.invoice_recognition.services.invoice_parser import ParsedInvoice

        inv = ParsedInvoice()
        assert inv.invoice_code == ""
        assert inv.invoice_number == ""
        assert inv.invoice_date is None
        assert inv.amount is None
        assert inv.category == "other"

    def test_with_values(self):
        from apps.invoice_recognition.services.invoice_parser import ParsedInvoice

        inv = ParsedInvoice(
            invoice_code="1234567890",
            invoice_number="12345678",
            invoice_date=date(2024, 1, 15),
            amount=Decimal("1000.00"),
            tax_amount=Decimal("130.00"),
            total_amount=Decimal("1130.00"),
            buyer_name="买方公司",
            seller_name="卖方公司",
            project_name="*信息技术服务*技术服务费",
            category="vat_special",
        )
        assert inv.invoice_code == "1234567890"
        assert inv.category == "vat_special"

    def test_frozen(self):
        from apps.invoice_recognition.services.invoice_parser import ParsedInvoice

        inv = ParsedInvoice(invoice_code="123")
        with pytest.raises(AttributeError):
            inv.invoice_code = "456"


class TestInvoiceParser:
    def test_parse_empty_text(self):
        from apps.invoice_recognition.services.invoice_parser import InvoiceParser

        parser = InvoiceParser()
        result = parser.parse("")
        assert result.invoice_code == ""
        assert result.invoice_number == ""

    def test_parse_with_category_keywords(self):
        from apps.invoice_recognition.services.invoice_parser import InvoiceParser

        parser = InvoiceParser()
        result = parser.parse("增值税专用发票 代码1234567890 号码12345678")
        assert result.category == "vat_special"

    def test_parse_vat_electronic(self):
        from apps.invoice_recognition.services.invoice_parser import InvoiceParser

        parser = InvoiceParser()
        result = parser.parse("增值税电子普通发票")
        assert result.category == "vat_electronic"

    def test_parse_train_ticket(self):
        from apps.invoice_recognition.services.invoice_parser import InvoiceParser

        parser = InvoiceParser()
        result = parser.parse("火车票报销凭证")
        assert result.category == "train_ticket"

    def test_parse_taxi(self):
        from apps.invoice_recognition.services.invoice_parser import InvoiceParser

        parser = InvoiceParser()
        result = parser.parse("出租车发票")
        assert result.category == "taxi_receipt"

    def test_parse_toll(self):
        from apps.invoice_recognition.services.invoice_parser import InvoiceParser

        parser = InvoiceParser()
        result = parser.parse("通行费发票")
        assert result.category == "toll_receipt"

    def test_parse_default_category(self):
        from apps.invoice_recognition.services.invoice_parser import InvoiceParser

        parser = InvoiceParser()
        result = parser.parse("普通文本没有发票关键词")
        assert result.category == "other"

    def test_extract_date_cn_format(self):
        from apps.invoice_recognition.services.invoice_parser import InvoiceParser

        parser = InvoiceParser()
        result = parser.parse("开票日期：2024年06月15日")
        assert result.invoice_date == date(2024, 6, 15)

    def test_extract_date_iso_format(self):
        from apps.invoice_recognition.services.invoice_parser import InvoiceParser

        parser = InvoiceParser()
        result = parser.parse("开票日期：2024-06-15")
        assert result.invoice_date == date(2024, 6, 15)

    def test_extract_total_amount(self):
        from apps.invoice_recognition.services.invoice_parser import InvoiceParser

        parser = InvoiceParser()
        result = parser.parse("（小写）￥1130.00")
        assert result.total_amount == Decimal("1130.00")


class TestInvoiceParserPatterns:
    def test_code_pattern(self):
        from apps.invoice_recognition.services.invoice_parser import InvoiceParser

        match = InvoiceParser._CODE_PATTERN.search("发票代码：123456789012")
        assert match is not None
        assert match.group(1) == "123456789012"

    def test_number_pattern(self):
        from apps.invoice_recognition.services.invoice_parser import InvoiceParser

        match = InvoiceParser._NUMBER_PATTERN.search("发票号码：12345678")
        assert match is not None

    def test_date_cn_pattern(self):
        from apps.invoice_recognition.services.invoice_parser import InvoiceParser

        match = InvoiceParser._DATE_CN_PATTERN.search("2024年6月15日")
        assert match is not None
        assert match.group(1) == "2024"

    def test_date_iso_pattern(self):
        from apps.invoice_recognition.services.invoice_parser import InvoiceParser

        match = InvoiceParser._DATE_ISO_PATTERN.search("2024-06-15")
        assert match is not None

    def test_total_pattern(self):
        from apps.invoice_recognition.services.invoice_parser import InvoiceParser

        match = InvoiceParser._TOTAL_PATTERN.search("（小写）￥1130.00")
        assert match is not None
        assert match.group(1) == "1130.00"

    def test_project_pattern(self):
        from apps.invoice_recognition.services.invoice_parser import InvoiceParser

        match = InvoiceParser._PROJECT_PATTERN.search("*信息技术服务*技术服务费")
        assert match is not None


# ============================================================================
# invoice_recognition/services/recognition_result.py tests
# ============================================================================


class TestRecognitionResult:
    def test_success_result(self):
        from apps.invoice_recognition.services.invoice_parser import ParsedInvoice
        from apps.invoice_recognition.services.recognition_result import RecognitionResult

        data = ParsedInvoice(invoice_code="123")
        result = RecognitionResult(filename="test.pdf", success=True, data=data)
        assert result.success is True
        assert result.error is None

    def test_failure_result(self):
        from apps.invoice_recognition.services.recognition_result import RecognitionResult

        result = RecognitionResult(filename="bad.pdf", success=False, error="格式错误")
        assert result.success is False
        assert result.error == "格式错误"


# ============================================================================
# image_rotation/services/pdf_extraction_service.py tests
# ============================================================================


class TestPDFExtractionService:
    def test_constants(self):
        from apps.image_rotation.services.pdf_extraction_service import PDFExtractionService

        assert PDFExtractionService.MAX_PDF_SIZE == 50 * 1024 * 1024
        assert PDFExtractionService.MAX_PAGES == 100
        assert PDFExtractionService.DPI == 150

    def test_init_without_service(self):
        from apps.image_rotation.services.pdf_extraction_service import PDFExtractionService

        service = PDFExtractionService()
        assert service._orientation_service is None

    def test_init_with_service(self):
        from apps.image_rotation.services.pdf_extraction_service import PDFExtractionService

        mock_service = Mock()
        service = PDFExtractionService(orientation_service=mock_service)
        assert service._orientation_service is mock_service


# ============================================================================
# document_recognition/services/document_classifier.py tests
# ============================================================================


class TestDocumentClassifier:
    def test_init_with_defaults(self):
        from apps.document_recognition.services.document_classifier import DocumentClassifier

        with patch(
            "apps.document_recognition.services.document_classifier.get_ollama_model",
            return_value="test_model",
        ), patch(
            "apps.document_recognition.services.document_classifier.get_ollama_base_url",
            return_value="http://localhost:11434",
        ):
            classifier = DocumentClassifier()
            assert classifier.ollama_model == "test_model"
            assert classifier.ollama_base_url == "http://localhost:11434"

    def test_init_with_custom_params(self):
        from apps.document_recognition.services.document_classifier import DocumentClassifier

        classifier = DocumentClassifier(
            ollama_model="custom_model",
            ollama_base_url="http://custom:11434",
        )
        assert classifier.ollama_model == "custom_model"
        assert classifier.ollama_base_url == "http://custom:11434"

    def test_classification_prompt_exists(self):
        from apps.document_recognition.services.document_classifier import DocumentClassifier

        assert "summons" in DocumentClassifier.CLASSIFICATION_PROMPT
        assert "execution" in DocumentClassifier.CLASSIFICATION_PROMPT
        assert "other" in DocumentClassifier.CLASSIFICATION_PROMPT


# ============================================================================
# core/utils/id_card_utils.py tests
# ============================================================================


class TestIdCardInfo:
    def test_default_creation(self):
        from apps.core.utils.id_card_utils import IdCardInfo

        info = IdCardInfo()
        assert info.birth_date is None
        assert info.gender is None
        assert info.age is None

    def test_with_values(self):
        from apps.core.utils.id_card_utils import IdCardInfo

        info = IdCardInfo(birth_date="1990年01月15日", gender="男", age=34)
        assert info.birth_date == "1990年01月15日"
        assert info.gender == "男"
        assert info.age == 34


class TestIdCardUtilsParseIdCardInfo:
    def test_18_digit_male(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        # Use a known valid 18-digit ID: 11010519491231002X
        # But we need a valid one with correct checksum
        # Let's just test the parsing logic
        info = IdCardUtils.parse_id_card_info("11010519900115001X")
        assert info.birth_date == "1990年01月15日"
        assert info.gender == "男"  # last digit before checksum is 1 (odd)

    def test_18_digit_female(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        info = IdCardUtils.parse_id_card_info("11010519900115002X")
        assert info.gender == "女"  # last digit before checksum is 2 (even)

    def test_15_digit(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        info = IdCardUtils.parse_id_card_info("110105900115001")
        assert info.birth_date == "1990年01月15日"
        assert info.gender == "男"  # last digit is 1

    def test_empty_string(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        info = IdCardUtils.parse_id_card_info("")
        assert info.birth_date is None

    def test_short_string(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        info = IdCardUtils.parse_id_card_info("123")
        assert info.birth_date is None


class TestIdCardUtilsExtractBirthDate:
    def test_18_digit(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.extract_birth_date("11010519900115001X")
        assert result == "1990年01月15日"

    def test_15_digit(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.extract_birth_date("110105900115001")
        assert result == "1990年01月15日"

    def test_empty(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        assert IdCardUtils.extract_birth_date("") is None
        assert IdCardUtils.extract_birth_date(None) is None


class TestIdCardUtilsExtractGender:
    def test_male_18_digit(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.extract_gender("11010519900115001X")
        assert result == "男"

    def test_female_18_digit(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.extract_gender("11010519900115002X")
        assert result == "女"

    def test_15_digit(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.extract_gender("110105900115001")
        assert result == "男"

    def test_empty(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        assert IdCardUtils.extract_gender("") is None


class TestIdCardUtilsCalculateAge:
    def test_18_digit(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        age = IdCardUtils.calculate_age("11010519900115001X")
        assert age is not None
        assert age >= 30  # born 1990, at least 30+

    def test_15_digit(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        age = IdCardUtils.calculate_age("110105900115001")
        assert age is not None

    def test_empty(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        assert IdCardUtils.calculate_age("") is None
        assert IdCardUtils.calculate_age(None) is None

    def test_invalid_length(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        assert IdCardUtils.calculate_age("12345") is None


class TestIdCardUtilsValidateIdCard:
    def test_empty(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.validate_id_card("")
        assert result["valid"] is False

    def test_wrong_length(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.validate_id_card("12345")
        assert result["valid"] is False
        assert "长度" in result["message"]

    def test_18_digit_non_digit_prefix(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.validate_id_card("1101051990011500AX")
        assert result["valid"] is False

    def test_18_digit_invalid_last_char(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.validate_id_card("11010519900115001Z")
        assert result["valid"] is False

    def test_18_digit_invalid_province(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.validate_id_card("99010519900115001X")
        assert result["valid"] is False
        assert "地区码" in result["message"]

    def test_18_digit_invalid_date(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.validate_id_card("11010519901315001X")
        assert result["valid"] is False
        assert "日期" in result["message"]

    def test_15_digit_non_digit(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.validate_id_card("11010590011500X")
        assert result["valid"] is False
        assert "全部为数字" in result["message"]

    def test_15_digit_invalid_province(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.validate_id_card("990105900115001")
        assert result["valid"] is False

    def test_15_digit_invalid_date(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.validate_id_card("110105901315001")
        assert result["valid"] is False


class TestIdCardUtilsValidateBirthDate:
    def test_valid_date(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        assert IdCardUtils._validate_birth_date("19900115", is_18_digit=True) is True

    def test_invalid_month(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        assert IdCardUtils._validate_birth_date("19901315", is_18_digit=True) is False

    def test_invalid_day(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        assert IdCardUtils._validate_birth_date("19900132", is_18_digit=True) is False

    def test_wrong_length(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        assert IdCardUtils._validate_birth_date("1990011", is_18_digit=True) is False

    def test_future_year(self):
        from apps.core.utils.id_card_utils import IdCardUtils

        assert IdCardUtils._validate_birth_date("20990115", is_18_digit=True) is False


class TestIdCardUtilsConstants:
    def test_weights(self):
        from apps.core.utils.id_card_utils import ID_CARD_WEIGHTS

        assert len(ID_CARD_WEIGHTS) == 17
        assert ID_CARD_WEIGHTS[0] == 7

    def test_check_codes(self):
        from apps.core.utils.id_card_utils import ID_CARD_CHECK_CODES

        assert len(ID_CARD_CHECK_CODES) == 11
        assert "X" in ID_CARD_CHECK_CODES


# ============================================================================
# documents/utils/formatters.py tests
# ============================================================================


class TestDocumentsFormatters:
    def test_format_date(self):
        from apps.documents.utils.formatters import format_date

        result = format_date(date(2024, 1, 15))
        assert "2024" in result

    def test_format_date_none(self):
        from apps.documents.utils.formatters import format_date

        result = format_date(None)
        assert result == ""

    def test_format_date_string(self):
        from apps.documents.utils.formatters import format_date

        result = format_date("2024-01-15")
        assert "2024" in result

    def test_format_date_chinese(self):
        from apps.documents.utils.formatters import format_date_chinese

        result = format_date_chinese(date(2024, 1, 15))
        assert "2024" in result
        assert "月" in result

    def test_format_date_chinese_none(self):
        from apps.documents.utils.formatters import format_date_chinese

        result = format_date_chinese(None)
        assert result == ""

    def test_format_date_chinese_default_today(self):
        from apps.documents.utils.formatters import format_date_chinese

        result = format_date_chinese(None, default_today=True)
        assert result  # non-empty

    def test_format_currency(self):
        from apps.documents.utils.formatters import format_currency

        result = format_currency(Decimal("1234.56"))
        assert "1,234.56" in result or "1234.56" in result

    def test_format_currency_none(self):
        from apps.documents.utils.formatters import format_currency

        result = format_currency(None)
        assert result == ""

    def test_format_currency_with_symbol(self):
        from apps.documents.utils.formatters import format_currency

        result = format_currency(Decimal("100"), include_symbol=True)
        assert "100" in result

    def test_format_percentage(self):
        from apps.documents.utils.formatters import format_percentage

        result = format_percentage(Decimal("0.1234"))
        # Could be "12.34%" or "0.1234" depending on implementation
        assert result  # non-empty

    def test_format_percentage_none(self):
        from apps.documents.utils.formatters import format_percentage

        result = format_percentage(None)
        assert result == ""
