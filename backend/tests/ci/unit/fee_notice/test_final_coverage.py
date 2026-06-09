"""Final coverage tests for fee_notice module."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

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
from apps.fee_notice.services.extraction.extraction_service import FeeNoticeExtractionService


# ============================================================================
# DetectionResult tests
# ============================================================================


class TestDetectionResult:
    def test_creation(self):
        r = DetectionResult(is_fee_notice=True, page_num=1, confidence=0.9, matched_keywords=["受理费"])
        assert r.is_fee_notice is True
        assert r.confidence == 0.9
        assert "受理费" in r.matched_keywords

    def test_with_raw_text(self):
        r = DetectionResult(is_fee_notice=False, page_num=2, confidence=0.0, matched_keywords=[], raw_text="text")
        assert r.raw_text == "text"


# ============================================================================
# FeeAmountResult tests
# ============================================================================


class TestFeeAmountResult:
    def test_defaults(self):
        r = FeeAmountResult()
        assert r.acceptance_fee is None
        assert r.table_format == "unknown"
        assert r.debug_info == {}

    def test_with_values(self):
        r = FeeAmountResult(
            acceptance_fee=Decimal("1000.00"),
            application_fee=Decimal("500.00"),
            total_fee=Decimal("1500.00"),
            table_format="horizontal",
        )
        assert r.acceptance_fee == Decimal("1000.00")
        assert r.total_fee == Decimal("1500.00")


# ============================================================================
# FeeNoticeInfo tests
# ============================================================================


class TestFeeNoticeInfo:
    def test_creation(self):
        det = DetectionResult(is_fee_notice=True, page_num=1, confidence=0.9, matched_keywords=["k"])
        amt = FeeAmountResult(acceptance_fee=Decimal("100"))
        info = FeeNoticeInfo(
            file_name="test.pdf",
            file_path="/path/test.pdf",
            page_num=1,
            detection=det,
            amounts=amt,
            extraction_method="pdf_direct",
        )
        assert info.file_name == "test.pdf"
        assert info.amounts.acceptance_fee == Decimal("100")


# ============================================================================
# FeeNoticeExtractionResult tests
# ============================================================================


class TestFeeNoticeExtractionResult:
    def test_defaults(self):
        r = FeeNoticeExtractionResult(notices=[], total_files=0, total_pages=0, errors=[])
        assert r.debug_logs == []

    def test_with_data(self):
        r = FeeNoticeExtractionResult(
            notices=[],
            total_files=2,
            total_pages=10,
            errors=[{"file": "x", "error": "e"}],
            debug_logs=["log1"],
        )
        assert r.total_files == 2
        assert len(r.errors) == 1


# ============================================================================
# CaseComparisonInfo tests
# ============================================================================


class TestCaseComparisonInfo:
    def test_defaults(self):
        info = CaseComparisonInfo(case_id=1, case_name="Test")
        assert info.is_complete is False
        assert info.case_number is None

    def test_with_values(self):
        info = CaseComparisonInfo(
            case_id=1, case_name="Test", case_number="cn",
            target_amount=Decimal("10000"), is_complete=True,
        )
        assert info.target_amount == Decimal("10000")


# ============================================================================
# CaseSearchResult tests
# ============================================================================


class TestCaseSearchResult:
    def test_creation(self):
        r = CaseSearchResult(id=1, name="Test")
        assert r.case_number is None

    def test_with_values(self):
        r = CaseSearchResult(id=1, name="Test", case_number="cn", target_amount=Decimal("500"))
        assert r.case_number == "cn"


# ============================================================================
# FeeComparisonResult tests
# ============================================================================


class TestFeeComparisonResult:
    def test_defaults(self):
        case_info = CaseComparisonInfo(case_id=1, case_name="Test")
        r = FeeComparisonResult(case_info=case_info)
        assert r.can_compare is True
        assert r.acceptance_fee_match is False

    def test_with_values(self):
        case_info = CaseComparisonInfo(case_id=1, case_name="Test")
        r = FeeComparisonResult(
            case_info=case_info,
            extracted_acceptance_fee=Decimal("1000"),
            calculated_acceptance_fee=Decimal("1000"),
            acceptance_fee_match=True,
            acceptance_fee_diff=Decimal("0"),
        )
        assert r.acceptance_fee_match is True


# ============================================================================
# FeeNoticeExtractionService tests
# ============================================================================


class TestFeeNoticeExtractionServiceInit:
    def test_defaults(self):
        svc = FeeNoticeExtractionService()
        assert svc._text_service is None
        assert svc._detector is None
        assert svc._extractor is None

    def test_with_injected(self):
        mock_text = MagicMock()
        mock_detector = MagicMock()
        mock_extractor = MagicMock()
        svc = FeeNoticeExtractionService(
            text_service=mock_text,
            detector=mock_detector,
            extractor=mock_extractor,
        )
        assert svc.text_service is mock_text
        assert svc.detector is mock_detector
        assert svc.extractor is mock_extractor


class TestFeeNoticeExtractionServiceProperties:
    def test_lazy_text_service(self):
        svc = FeeNoticeExtractionService()
        with patch("apps.fee_notice.services.extraction.extraction_service.FeeNoticeExtractionService.text_service", new_callable=lambda: property(lambda self: MagicMock())):
            pass  # properties are lazy loaded

    def test_detector_property(self):
        svc = FeeNoticeExtractionService()
        mock_detector = MagicMock()
        svc._detector = mock_detector
        assert svc.detector is mock_detector

    def test_extractor_property(self):
        svc = FeeNoticeExtractionService()
        mock_extractor = MagicMock()
        svc._extractor = mock_extractor
        assert svc.extractor is mock_extractor


class TestFeeNoticeIsSupportedFormat:
    def test_pdf(self):
        svc = FeeNoticeExtractionService()
        assert svc._is_supported_format("file.pdf") is True

    def test_docx(self):
        svc = FeeNoticeExtractionService()
        assert svc._is_supported_format("file.docx") is False

    def test_uppercase_pdf(self):
        svc = FeeNoticeExtractionService()
        assert svc._is_supported_format("FILE.PDF") is True


class TestFeeNoticeExtractFromFiles:
    def test_unsupported_format(self):
        svc = FeeNoticeExtractionService()
        result = svc.extract_from_files(["file.docx"])
        assert len(result.errors) == 1
        assert result.errors[0]["code"] == "UNSUPPORTED_FORMAT"

    def test_nonexistent_file(self):
        svc = FeeNoticeExtractionService()
        result = svc.extract_from_files(["/nonexistent/file.pdf"])
        assert len(result.errors) == 1
        assert result.errors[0]["code"] == "FILE_NOT_FOUND"

    def test_empty_list(self):
        svc = FeeNoticeExtractionService()
        result = svc.extract_from_files([])
        assert result.total_files == 0
        assert result.notices == []

    def test_with_debug(self):
        svc = FeeNoticeExtractionService()
        result = svc.extract_from_files(["file.docx"], debug=True)
        assert len(result.debug_logs) > 0


class TestFeeNoticeCleanupTempFiles:
    def test_cleanup_existing_files(self, tmp_path):
        svc = FeeNoticeExtractionService()
        f = tmp_path / "test.txt"
        f.write_text("content")
        svc.cleanup_temp_files([f])
        assert not f.exists()

    def test_cleanup_nonexistent(self):
        svc = FeeNoticeExtractionService()
        svc.cleanup_temp_files([Path("/nonexistent")])  # should not raise

    def test_cleanup_empty_list(self):
        svc = FeeNoticeExtractionService()
        svc.cleanup_temp_files([])  # should not raise
