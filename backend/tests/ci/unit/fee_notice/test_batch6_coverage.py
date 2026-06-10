"""Batch 6 coverage tests for fee_notice module."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest


class TestFeeNoticeTypes:
    def test_detection_result(self):
        from apps.fee_notice.services.types import DetectionResult

        result = DetectionResult(
            is_fee_notice=True, page_num=1, confidence=0.95, matched_keywords=["受理费"]
        )
        assert result.is_fee_notice is True
        assert result.page_num == 1
        assert result.confidence == 0.95
        assert result.raw_text == ""

    def test_fee_amount_result(self):
        from apps.fee_notice.services.types import FeeAmountResult

        result = FeeAmountResult()
        assert result.acceptance_fee is None
        assert result.application_fee is None
        assert result.preservation_fee is None
        assert result.total_fee is None
        assert result.table_format == "unknown"

    def test_fee_amount_result_with_values(self):
        from apps.fee_notice.services.types import FeeAmountResult

        result = FeeAmountResult(
            acceptance_fee=Decimal("5000"),
            total_fee=Decimal("5000"),
        )
        assert result.acceptance_fee == Decimal("5000")

    def test_fee_notice_info(self):
        from apps.fee_notice.services.types import (
            DetectionResult,
            FeeAmountResult,
            FeeNoticeInfo,
        )

        info = FeeNoticeInfo(
            file_name="test.pdf",
            file_path="/path/to/test.pdf",
            page_num=1,
            detection=DetectionResult(
                is_fee_notice=True, page_num=1, confidence=0.9, matched_keywords=[]
            ),
            amounts=FeeAmountResult(),
            extraction_method="pdf_direct",
        )
        assert info.file_name == "test.pdf"
        assert info.extraction_method == "pdf_direct"

    def test_fee_notice_extraction_result(self):
        from apps.fee_notice.services.types import FeeNoticeExtractionResult

        result = FeeNoticeExtractionResult(
            notices=[], total_files=0, total_pages=0, errors=[]
        )
        assert result.notices == []
        assert result.debug_logs == []

    def test_case_comparison_info(self):
        from apps.fee_notice.services.types import CaseComparisonInfo

        info = CaseComparisonInfo(case_id=1, case_name="测试案件")
        assert info.case_number is None
        assert info.is_complete is False

    def test_case_search_result(self):
        from apps.fee_notice.services.types import CaseSearchResult

        result = CaseSearchResult(id=1, name="测试案件")
        assert result.case_number is None

    def test_fee_comparison_result(self):
        from apps.fee_notice.services.types import (
            CaseComparisonInfo,
            FeeComparisonResult,
        )

        result = FeeComparisonResult(
            case_info=CaseComparisonInfo(case_id=1, case_name="测试案件"),
        )
        assert result.acceptance_fee_match is False
        assert result.can_compare is True
