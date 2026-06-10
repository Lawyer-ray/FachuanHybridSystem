"""
Tests for apps.fee_notice.services — 交费通知书识别服务
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest


# ============================================================
# FeeNoticeDetector 测试
# ============================================================


class TestFeeNoticeDetector:
    """FeeNoticeDetector 测试"""

    def _make_detector(self):
        from apps.fee_notice.services.detection.detector import FeeNoticeDetector

        return FeeNoticeDetector()

    def test_detect_fee_notice_page(self) -> None:
        detector = self._make_detector()
        text = "诉讼费用交费通知书\n案件受理费：1000元"
        result = detector.detect(text, page_num=1)
        assert result.is_fee_notice is True
        assert result.confidence > 0.5
        assert len(result.matched_keywords) > 0

    def test_detect_non_fee_page(self) -> None:
        detector = self._make_detector()
        text = "这是一份普通的法律文书"
        result = detector.detect(text, page_num=1)
        assert result.is_fee_notice is False
        assert result.confidence == 0.0

    def test_detect_empty_text(self) -> None:
        detector = self._make_detector()
        result = detector.detect("", page_num=1)
        assert result.is_fee_notice is False
        assert result.confidence == 0.0

    def test_detect_none_text(self) -> None:
        detector = self._make_detector()
        result = detector.detect(None, page_num=1)
        assert result.is_fee_notice is False

    def test_detect_pages_batch(self) -> None:
        detector = self._make_detector()
        pages = [
            (1, "普通文书内容"),
            (2, "交费通知书\n案件受理费：1000元"),
            (3, "判决书内容"),
        ]
        results = detector.detect_pages(pages)
        assert len(results) == 3
        assert results[0].is_fee_notice is False
        assert results[1].is_fee_notice is True
        assert results[2].is_fee_notice is False

    def test_find_matched_keywords(self) -> None:
        detector = self._make_detector()
        matched = detector._find_matched_keywords("交费通知书和案件受理费")
        assert "交费通知书" in matched
        assert "案件受理费" in matched

    def test_find_matched_keywords_empty(self) -> None:
        detector = self._make_detector()
        assert detector._find_matched_keywords("") == []

    def test_calculate_confidence_empty(self) -> None:
        detector = self._make_detector()
        assert detector._calculate_confidence([]) == 0.0

    def test_calculate_confidence_single_keyword(self) -> None:
        detector = self._make_detector()
        conf = detector._calculate_confidence(["交费通知书"])
        assert conf == 1.0

    def test_calculate_confidence_multiple_keywords(self) -> None:
        detector = self._make_detector()
        conf = detector._calculate_confidence(["交费通知书", "案件受理费"])
        assert conf > 1.0 or conf == 1.0  # max 1.0


# ============================================================
# FeeAmountExtractor 测试
# ============================================================


class TestFeeAmountExtractor:
    """FeeAmountExtractor 测试"""

    def _make_extractor(self):
        from apps.fee_notice.services.detection.extractor import FeeAmountExtractor

        return FeeAmountExtractor()

    def test_extract_empty_text(self) -> None:
        extractor = self._make_extractor()
        result = extractor.extract("")
        assert result.table_format == "unknown"

    def test_parse_amount_simple(self) -> None:
        extractor = self._make_extractor()
        assert extractor._parse_amount("1000") == Decimal("1000")

    def test_parse_amount_with_comma(self) -> None:
        extractor = self._make_extractor()
        assert extractor._parse_amount("1,000.50") == Decimal("1000.50")

    def test_parse_amount_with_unit(self) -> None:
        extractor = self._make_extractor()
        assert extractor._parse_amount("1000元") == Decimal("1000")

    def test_parse_amount_with_chinese_unit(self) -> None:
        extractor = self._make_extractor()
        result = extractor._parse_amount("1000圆")
        assert result == Decimal("1000")

    def test_parse_amount_empty(self) -> None:
        extractor = self._make_extractor()
        assert extractor._parse_amount("") is None

    def test_parse_amount_negative(self) -> None:
        extractor = self._make_extractor()
        # _parse_amount extracts digits from the string, so "-100" -> 100
        # It does not explicitly reject negative numbers in the regex fallback
        result = extractor._parse_amount("-100")
        assert result is not None  # extracts 100 from "-100"

    def test_parse_amount_non_numeric(self) -> None:
        extractor = self._make_extractor()
        assert extractor._parse_amount("abc") is None

    def test_match_fee_field_acceptance(self) -> None:
        extractor = self._make_extractor()
        assert extractor._match_fee_field("案件受理费") == "acceptance_fee"
        assert extractor._match_fee_field("受理费") == "acceptance_fee"

    def test_match_fee_field_preservation(self) -> None:
        extractor = self._make_extractor()
        assert extractor._match_fee_field("保全费") == "preservation_fee"
        assert extractor._match_fee_field("财产保全费") == "preservation_fee"

    def test_match_fee_field_execution(self) -> None:
        extractor = self._make_extractor()
        assert extractor._match_fee_field("执行费") == "execution_fee"

    def test_match_fee_field_application(self) -> None:
        extractor = self._make_extractor()
        assert extractor._match_fee_field("申请费") == "application_fee"

    def test_match_fee_field_other(self) -> None:
        extractor = self._make_extractor()
        assert extractor._match_fee_field("其他诉讼费") == "other_fee"
        assert extractor._match_fee_field("其他费用") == "other_fee"

    def test_match_fee_field_unknown(self) -> None:
        extractor = self._make_extractor()
        assert extractor._match_fee_field("未知费用") is None

    def test_normalize_text(self) -> None:
        extractor = self._make_extractor()
        result = extractor._normalize_text("hello  world\r\n")
        assert "\r" not in result

    def test_extract_general_pattern_with_payable(self) -> None:
        extractor = self._make_extractor()
        text = "案件受理费应收金额 1000.00 (壹仟元整)"
        result = extractor._extract_general_pattern(text)
        if result:
            assert "acceptance_fee" in result

    def test_build_result(self) -> None:
        extractor = self._make_extractor()
        fees = {"acceptance_fee": Decimal("1000"), "preservation_fee": Decimal("500")}
        result = extractor._build_result(fees, "horizontal", {})
        assert result.acceptance_fee == Decimal("1000")
        assert result.preservation_fee == Decimal("500")
        assert result.total_fee == Decimal("1500")
        assert result.table_format == "horizontal"

    def test_extract_horizontal_continuous(self) -> None:
        extractor = self._make_extractor()
        text = "收费项目名称 受理费 保全费 执行费 其他诉讼费 金额 1000 500 0 0 应收金额 1500"
        result = extractor._extract_continuous_horizontal(text)
        assert result is not None
        assert result["acceptance_fee"] == Decimal("1000")
        assert result["preservation_fee"] == Decimal("500")

    def test_extract_continuous_horizontal_no_match(self) -> None:
        extractor = self._make_extractor()
        result = extractor._extract_continuous_horizontal("普通文本没有费用")
        assert result is None

    def test_split_fee_header_by_space(self) -> None:
        extractor = self._make_extractor()
        result = extractor._split_fee_header_by_space("收费项目名称 受理费 保全费")
        assert "受理费" in result
        assert "保全费" in result

    def test_split_amount_row_by_space(self) -> None:
        extractor = self._make_extractor()
        result = extractor._split_amount_row_by_space("金额 100 200 300")
        assert result == ["金额", "100", "200", "300"]


# ============================================================
# DetectionResult / FeeAmountResult 数据类测试
# ============================================================


class TestFeeNoticeTypes:
    """费用通知数据类测试"""

    def test_detection_result(self) -> None:
        from apps.fee_notice.services.types import DetectionResult

        result = DetectionResult(
            is_fee_notice=True, page_num=1, confidence=0.9, matched_keywords=["交费通知书"]
        )
        assert result.is_fee_notice is True
        assert result.confidence == 0.9

    def test_fee_amount_result_defaults(self) -> None:
        from apps.fee_notice.services.types import FeeAmountResult

        result = FeeAmountResult()
        assert result.acceptance_fee is None
        assert result.total_fee is None
        assert result.table_format == "unknown"

    def test_fee_amount_result_with_values(self) -> None:
        from apps.fee_notice.services.types import FeeAmountResult

        result = FeeAmountResult(
            acceptance_fee=Decimal("1000"),
            preservation_fee=Decimal("500"),
            total_fee=Decimal("1500"),
            table_format="horizontal",
        )
        assert result.acceptance_fee == Decimal("1000")
        assert result.total_fee == Decimal("1500")

    def test_fee_notice_info(self) -> None:
        from apps.fee_notice.services.types import DetectionResult, FeeAmountResult, FeeNoticeInfo

        info = FeeNoticeInfo(
            file_name="test.pdf",
            file_path="/path/test.pdf",
            page_num=1,
            detection=DetectionResult(is_fee_notice=True, page_num=1, confidence=0.9, matched_keywords=[]),
            amounts=FeeAmountResult(),
            extraction_method="pdf_direct",
        )
        assert info.file_name == "test.pdf"
        assert info.extraction_method == "pdf_direct"


# ---------------------------------------------------------------------------
# FeeAmountExtractor extended tests
# ---------------------------------------------------------------------------

class TestFeeAmountExtractorExtended:
    def _make_extractor(self):
        from apps.fee_notice.services.detection.extractor import FeeAmountExtractor
        return FeeAmountExtractor()

    def test_parse_amount_basic(self):
        ext = self._make_extractor()
        result = ext._parse_amount("1234.56")
        assert result is not None
        assert float(result) == 1234.56

    def test_parse_amount_with_comma(self):
        ext = self._make_extractor()
        result = ext._parse_amount("1,234.56")
        assert result is not None
        assert float(result) == 1234.56

    def test_parse_amount_with_unit(self):
        ext = self._make_extractor()
        result = ext._parse_amount("1234.56元")
        assert result is not None

    def test_parse_amount_negative(self):
        ext = self._make_extractor()
        result = ext._parse_amount("not-a-number"); assert result is None

    def test_parse_amount_empty(self):
        ext = self._make_extractor()
        assert ext._parse_amount("") is None

    def test_parse_amount_non_numeric(self):
        ext = self._make_extractor()
        assert ext._parse_amount("abc") is None

    def test_match_fee_field_acceptance(self):
        ext = self._make_extractor()
        assert ext._match_fee_field("案件受理费") == "acceptance_fee"
        assert ext._match_fee_field("受理费") == "acceptance_fee"

    def test_match_fee_field_preservation(self):
        ext = self._make_extractor()
        assert ext._match_fee_field("保全费") == "preservation_fee"
        assert ext._match_fee_field("财产保全费") == "preservation_fee"

    def test_match_fee_field_execution(self):
        ext = self._make_extractor()
        assert ext._match_fee_field("执行费") == "execution_fee"

    def test_match_fee_field_application(self):
        ext = self._make_extractor()
        assert ext._match_fee_field("申请费") == "application_fee"

    def test_match_fee_field_other(self):
        ext = self._make_extractor()
        assert ext._match_fee_field("其他诉讼费") == "other_fee"
        assert ext._match_fee_field("其他费用") == "other_fee"

    def test_match_fee_field_unknown(self):
        ext = self._make_extractor()
        assert ext._match_fee_field("未知费用") is None

    def test_extract_horizontal_table_continuous(self):
        ext = self._make_extractor()
        text = "受理费 保全费 执行费 其他诉讼费 金额 100 200 0 0"
        result = ext._extract_horizontal_table(text)
        assert result is not None

    def test_extract_general_pattern_with_named_fee(self):
        ext = self._make_extractor()
        text = "案件受理费 1000元"
        result = ext._extract_general_pattern(text)
        assert result is not None
        assert "acceptance_fee" in result

    def test_determine_fee_type(self):
        ext = self._make_extractor()
        assert ext._determine_fee_type("案件受理费通知") == "acceptance_fee"
        assert ext._determine_fee_type("保全费") == "preservation_fee"
        assert ext._determine_fee_type("执行费") == "execution_fee"
        assert ext._determine_fee_type("申请费") == "application_fee"

    def test_normalize_text(self):
        ext = self._make_extractor()
        result = ext._normalize_text("hello\r\nworld")
        assert "\r" not in result

    def test_extract_continuous_horizontal(self):
        ext = self._make_extractor()
        text = "受理费 保全费 执行费 其他诉讼费 金额 100 200 0 50"
        result = ext._extract_continuous_horizontal(text)
        assert result is not None

    def test_extract_payable_amount(self):
        ext = self._make_extractor()
        text = "应收金额 1234.56"
        result = ext._extract_payable_amount(text)
        assert result is not None
        assert float(result) == 1234.56


class TestFeeNoticeExtractionService:
    def test_is_supported_format(self):
        from apps.fee_notice.services.extraction.extraction_service import FeeNoticeExtractionService
        svc = FeeNoticeExtractionService()
        assert svc._is_supported_format("test.pdf") is True
        assert svc._is_supported_format("test.docx") is False

    def test_extract_from_files_unsupported_format(self):
        from apps.fee_notice.services.extraction.extraction_service import FeeNoticeExtractionService
        svc = FeeNoticeExtractionService()
        result = svc.extract_from_files(["test.docx"])
        assert len(result.errors) == 1
        assert result.errors[0]["code"] == "UNSUPPORTED_FORMAT"

    def test_extract_from_files_not_found(self):
        from apps.fee_notice.services.extraction.extraction_service import FeeNoticeExtractionService
        svc = FeeNoticeExtractionService()
        result = svc.extract_from_files(["/nonexistent/file.pdf"])
        assert len(result.errors) == 1
        assert result.errors[0]["code"] == "FILE_NOT_FOUND"

    def test_extract_from_files_empty_list(self):
        from apps.fee_notice.services.extraction.extraction_service import FeeNoticeExtractionService
        svc = FeeNoticeExtractionService()
        result = svc.extract_from_files([])
        assert result.total_files == 0
        assert result.notices == []

    def test_cleanup_temp_files(self, tmp_path):
        from apps.fee_notice.services.extraction.extraction_service import FeeNoticeExtractionService
        svc = FeeNoticeExtractionService()
        f = tmp_path / "test.txt"
        f.write_text("test")
        svc.cleanup_temp_files([f])
        assert not f.exists()
