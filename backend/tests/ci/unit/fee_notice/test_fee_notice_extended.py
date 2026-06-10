"""Extended tests for fee_notice services - types, detection, extraction."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.fee_notice.services.types import (
    DetectionResult,
    FeeAmountResult,
    FeeNoticeExtractionResult,
    FeeNoticeInfo,
    CaseComparisonInfo,
    CaseSearchResult,
    FeeComparisonResult,
)


class TestDetectionResult:
    def test_creation(self):
        result = DetectionResult(
            is_fee_notice=True,
            page_num=1,
            confidence=0.9,
            matched_keywords=["受理费"],
        )
        assert result.is_fee_notice is True
        assert result.page_num == 1
        assert result.confidence == 0.9
        assert "受理费" in result.matched_keywords

    def test_defaults(self):
        result = DetectionResult(
            is_fee_notice=False,
            page_num=1,
            confidence=0.0,
            matched_keywords=[],
        )
        assert result.raw_text == ""


class TestFeeAmountResult:
    def test_defaults(self):
        result = FeeAmountResult()
        assert result.acceptance_fee is None
        assert result.application_fee is None
        assert result.preservation_fee is None
        assert result.execution_fee is None
        assert result.other_fee is None
        assert result.total_fee is None
        assert result.table_format == "unknown"

    def test_with_values(self):
        result = FeeAmountResult(
            acceptance_fee=Decimal("1000.00"),
            total_fee=Decimal("1500.00"),
            table_format="horizontal",
        )
        assert result.acceptance_fee == Decimal("1000.00")
        assert result.total_fee == Decimal("1500.00")
        assert result.table_format == "horizontal"


class TestFeeNoticeInfo:
    def test_creation(self):
        detection = DetectionResult(
            is_fee_notice=True,
            page_num=1,
            confidence=0.9,
            matched_keywords=["受理费"],
        )
        amounts = FeeAmountResult(acceptance_fee=Decimal("1000.00"))
        info = FeeNoticeInfo(
            file_name="test.pdf",
            file_path="/tmp/test.pdf",
            page_num=1,
            detection=detection,
            amounts=amounts,
            extraction_method="pdf_direct",
        )
        assert info.file_name == "test.pdf"
        assert info.extraction_method == "pdf_direct"


class TestFeeNoticeExtractionResult:
    def test_creation(self):
        result = FeeNoticeExtractionResult(
            notices=[],
            total_files=1,
            total_pages=5,
            errors=[],
        )
        assert result.total_files == 1
        assert result.total_pages == 5
        assert result.errors == []
        assert result.debug_logs == []


class TestCaseComparisonInfo:
    def test_defaults(self):
        info = CaseComparisonInfo(case_id=1, case_name="测试案件")
        assert info.case_id == 1
        assert info.case_name == "测试案件"
        assert info.case_number is None
        assert info.is_complete is False


class TestCaseSearchResult:
    def test_creation(self):
        result = CaseSearchResult(id=1, name="测试案件", case_number="2024民初123号")
        assert result.id == 1
        assert result.case_number == "2024民初123号"


class TestFeeComparisonResult:
    def test_defaults(self):
        case_info = CaseComparisonInfo(case_id=1, case_name="测试案件")
        result = FeeComparisonResult(case_info=case_info)
        assert result.acceptance_fee_match is False
        assert result.can_compare is True
        assert result.acceptance_fee_diff is None


class TestFeeNoticeDetector:
    def test_import(self):
        from apps.fee_notice.services.detection.detector import FeeNoticeDetector

        assert FeeNoticeDetector is not None

    def test_creation(self):
        from apps.fee_notice.services.detection.detector import FeeNoticeDetector

        detector = FeeNoticeDetector()
        assert callable(detector.detect)


class TestFeeAmountExtractor:
    def test_import(self):
        from apps.fee_notice.services.detection.extractor import FeeAmountExtractor

        assert FeeAmountExtractor is not None

    def test_creation(self):
        from apps.fee_notice.services.detection.extractor import FeeAmountExtractor

        extractor = FeeAmountExtractor()
        assert callable(extractor.extract)
