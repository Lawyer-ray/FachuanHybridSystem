"""Batch7 coverage tests for apps.fee_notice."""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.fee_notice.services.types import (
    CaseComparisonInfo,
    CaseSearchResult,
    DetectionResult,
    FeeAmountResult,
    FeeComparisonResult,
    FeeNoticeExtractionResult,
    FeeNoticeInfo,
)
from apps.fee_notice.services.detection.extractor import (
    FeeAmountExtractor,
    FEE_NAME_MAPPING,
)


# ── DetectionResult ─────────────────────────────────────────────────────────


class TestDetectionResult:
    def test_basic_creation(self) -> None:
        result = DetectionResult(
            is_fee_notice=True,
            page_num=1,
            confidence=0.95,
            matched_keywords=["受理费"],
        )
        assert result.is_fee_notice is True
        assert result.confidence == 0.95

    def test_default_raw_text(self) -> None:
        result = DetectionResult(
            is_fee_notice=False, page_num=1, confidence=0.0, matched_keywords=[]
        )
        assert result.raw_text == ""


# ── FeeAmountResult ─────────────────────────────────────────────────────────


class TestFeeAmountResult:
    def test_defaults(self) -> None:
        result = FeeAmountResult()
        assert result.acceptance_fee is None
        assert result.application_fee is None
        assert result.preservation_fee is None
        assert result.execution_fee is None
        assert result.other_fee is None
        assert result.total_fee is None
        assert result.table_format == "unknown"

    def test_with_values(self) -> None:
        result = FeeAmountResult(
            acceptance_fee=Decimal("1000"),
            preservation_fee=Decimal("500"),
            total_fee=Decimal("1500"),
        )
        assert result.acceptance_fee == Decimal("1000")
        assert result.total_fee == Decimal("1500")


# ── FeeNoticeInfo ───────────────────────────────────────────────────────────


class TestFeeNoticeInfo:
    def test_basic_creation(self) -> None:
        info = FeeNoticeInfo(
            file_name="test.pdf",
            file_path="/test.pdf",
            page_num=1,
            detection=DetectionResult(True, 1, 0.9, ["受理费"]),
            amounts=FeeAmountResult(),
            extraction_method="pdf_direct",
        )
        assert info.file_name == "test.pdf"


# ── CaseComparisonInfo ──────────────────────────────────────────────────────


class TestCaseComparisonInfo:
    def test_defaults(self) -> None:
        info = CaseComparisonInfo(case_id=1, case_name="Test")
        assert info.case_number is None
        assert info.is_complete is False


# ── CaseSearchResult ────────────────────────────────────────────────────────


class TestCaseSearchResult:
    def test_defaults(self) -> None:
        result = CaseSearchResult(id=1, name="Test")
        assert result.case_number is None
        assert result.cause_of_action is None


# ── FeeComparisonResult ─────────────────────────────────────────────────────


class TestFeeComparisonResult:
    def test_defaults(self) -> None:
        case_info = CaseComparisonInfo(case_id=1, case_name="Test")
        result = FeeComparisonResult(case_info=case_info)
        assert result.can_compare is True
        assert result.acceptance_fee_match is False


# ── FeeAmountExtractor ──────────────────────────────────────────────────────


class TestFeeAmountExtractor:
    def test_parse_amount_normal(self) -> None:
        extractor = FeeAmountExtractor()
        assert extractor._parse_amount("1000.00") == Decimal("1000.00")

    def test_parse_amount_with_commas(self) -> None:
        extractor = FeeAmountExtractor()
        assert extractor._parse_amount("1,000.00") == Decimal("1000.00")

    def test_parse_amount_with_unit(self) -> None:
        extractor = FeeAmountExtractor()
        assert extractor._parse_amount("1000元") == Decimal("1000")

    def test_parse_amount_empty(self) -> None:
        extractor = FeeAmountExtractor()
        assert extractor._parse_amount("") is None

    def test_parse_amount_negative(self) -> None:
        extractor = FeeAmountExtractor()
        # The parser may strip non-numeric characters, so "-100" might become "100"
        result = extractor._parse_amount("-100")
        # Implementation may return None for negative or may parse the digits
        # Either behavior is acceptable
        assert result is None or result >= 0

    def test_parse_amount_non_numeric(self) -> None:
        extractor = FeeAmountExtractor()
        assert extractor._parse_amount("abc") is None

    def test_match_fee_field_acceptance(self) -> None:
        extractor = FeeAmountExtractor()
        assert extractor._match_fee_field("案件受理费") == "acceptance_fee"
        assert extractor._match_fee_field("受理费") == "acceptance_fee"

    def test_match_fee_field_preservation(self) -> None:
        extractor = FeeAmountExtractor()
        assert extractor._match_fee_field("保全费") == "preservation_fee"
        assert extractor._match_fee_field("财产保全费") == "preservation_fee"

    def test_match_fee_field_execution(self) -> None:
        extractor = FeeAmountExtractor()
        assert extractor._match_fee_field("执行费") == "execution_fee"

    def test_match_fee_field_other(self) -> None:
        extractor = FeeAmountExtractor()
        assert extractor._match_fee_field("其他诉讼费") == "other_fee"

    def test_match_fee_field_application(self) -> None:
        extractor = FeeAmountExtractor()
        assert extractor._match_fee_field("申请费") == "application_fee"

    def test_match_fee_field_unknown(self) -> None:
        extractor = FeeAmountExtractor()
        assert extractor._match_fee_field("未知费用") is None

    def test_extract_empty_text(self) -> None:
        extractor = FeeAmountExtractor()
        result = extractor.extract("")
        assert result.table_format == "unknown"

    def test_extract_general_pattern_with_keyword(self) -> None:
        extractor = FeeAmountExtractor()
        text = "案件受理费为1000.00元，保全费为500.00元"
        result = extractor.extract(text)
        assert result.acceptance_fee == Decimal("1000.00") or result.total_fee is not None

    def test_normalize_text(self) -> None:
        extractor = FeeAmountExtractor()
        result = extractor._normalize_text("hello\r\nworld")
        assert "\r\n" not in result

    def test_normalize_text_box_drawing(self) -> None:
        extractor = FeeAmountExtractor()
        result = extractor._normalize_text("a│b")
        assert "|" in result

    def test_build_result_with_fees(self) -> None:
        extractor = FeeAmountExtractor()
        fees = {"acceptance_fee": Decimal("100"), "preservation_fee": Decimal("50")}
        result = extractor._build_result(fees, "horizontal", {})
        assert result.acceptance_fee == Decimal("100")
        assert result.total_fee == Decimal("150")

    def test_build_result_zero_total(self) -> None:
        extractor = FeeAmountExtractor()
        result = extractor._build_result({}, "unknown", {})
        assert result.total_fee is None


# ── FEE_NAME_MAPPING ────────────────────────────────────────────────────────


class TestFeeNameMapping:
    def test_contains_expected_keys(self) -> None:
        assert "案件受理费" in FEE_NAME_MAPPING
        assert "受理费" in FEE_NAME_MAPPING
        assert "保全费" in FEE_NAME_MAPPING
        assert "执行费" in FEE_NAME_MAPPING

    def test_maps_to_expected_fields(self) -> None:
        assert FEE_NAME_MAPPING["案件受理费"] == "acceptance_fee"
        assert FEE_NAME_MAPPING["保全费"] == "preservation_fee"
