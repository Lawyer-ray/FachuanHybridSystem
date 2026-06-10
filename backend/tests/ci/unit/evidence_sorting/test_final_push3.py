"""Final push coverage tests for evidence_sorting, fee_notice, express_query modules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest


# ============================================================================
# evidence_sorting/services/classifier.py tests
# ============================================================================


class TestClassifiedImage:
    def test_creation(self):
        from apps.evidence_sorting.services.classifier import ClassifiedImage

        img = ClassifiedImage(
            filename="test.jpg",
            category="statement",
            ocr_text="对账单内容",
        )
        assert img.filename == "test.jpg"
        assert img.category == "statement"
        assert img.confidence == 0.0
        assert img.rotation == 0
        assert img.date is None
        assert img.amount is None
        assert img.signed is None

    def test_with_all_fields(self):
        from apps.evidence_sorting.services.classifier import ClassifiedImage

        img = ClassifiedImage(
            filename="receipt.png",
            category="receipt",
            ocr_text="收款凭证",
            date="20240615",
            amount="65500",
            signed=True,
            confidence=0.95,
            image_data="base64data",
            rotation=90,
        )
        assert img.date == "20240615"
        assert img.amount == "65500"
        assert img.signed is True
        assert img.rotation == 90


class TestClassifyResult:
    def test_default_creation(self):
        from apps.evidence_sorting.services.classifier import ClassifyResult

        result = ClassifyResult()
        assert result.images == []
        assert result.errors == []

    def test_with_data(self):
        from apps.evidence_sorting.services.classifier import ClassifiedImage, ClassifyResult

        img = ClassifiedImage(filename="a.jpg", category="other", ocr_text="")
        result = ClassifyResult(images=[img], errors=["err1"])
        assert len(result.images) == 1
        assert len(result.errors) == 1


class TestClassifierKeywords:
    def test_statement_keywords(self):
        from apps.evidence_sorting.services.classifier import _KEYWORDS, TYPE_STATEMENT

        assert "对账单" in _KEYWORDS[TYPE_STATEMENT]
        assert "月结" in _KEYWORDS[TYPE_STATEMENT]

    def test_delivery_keywords(self):
        from apps.evidence_sorting.services.classifier import _KEYWORDS, TYPE_DELIVERY

        assert "出库单" in _KEYWORDS[TYPE_DELIVERY]
        assert "送货单" in _KEYWORDS[TYPE_DELIVERY]

    def test_receipt_keywords(self):
        from apps.evidence_sorting.services.classifier import _KEYWORDS, TYPE_RECEIPT

        assert "收款" in _KEYWORDS[TYPE_RECEIPT]
        assert "微信支付" in _KEYWORDS[TYPE_RECEIPT]
        assert "支付宝" in _KEYWORDS[TYPE_RECEIPT]

    def test_type_constants(self):
        from apps.evidence_sorting.services.classifier import (
            TYPE_DELIVERY,
            TYPE_OTHER,
            TYPE_RECEIPT,
            TYPE_STATEMENT,
        )

        assert TYPE_STATEMENT == "statement"
        assert TYPE_DELIVERY == "delivery"
        assert TYPE_RECEIPT == "receipt"
        assert TYPE_OTHER == "other"


# ============================================================================
# fee_notice/services/types.py tests
# ============================================================================


class TestDetectionResult:
    def test_creation(self):
        from apps.fee_notice.services.types import DetectionResult

        result = DetectionResult(
            is_fee_notice=True,
            page_num=1,
            confidence=0.95,
            matched_keywords=["交费通知书", "受理费"],
        )
        assert result.is_fee_notice is True
        assert result.page_num == 1
        assert result.confidence == 0.95
        assert len(result.matched_keywords) == 2
        assert result.raw_text == ""

    def test_not_fee_notice(self):
        from apps.fee_notice.services.types import DetectionResult

        result = DetectionResult(
            is_fee_notice=False,
            page_num=1,
            confidence=0.1,
            matched_keywords=[],
        )
        assert result.is_fee_notice is False


class TestFeeAmountResult:
    def test_default_creation(self):
        from apps.fee_notice.services.types import FeeAmountResult

        result = FeeAmountResult()
        assert result.acceptance_fee is None
        assert result.application_fee is None
        assert result.total_fee is None
        assert result.table_format == "unknown"

    def test_with_values(self):
        from apps.fee_notice.services.types import FeeAmountResult

        result = FeeAmountResult(
            acceptance_fee=Decimal("5000"),
            application_fee=Decimal("1000"),
            total_fee=Decimal("6000"),
            table_format="horizontal",
        )
        assert result.acceptance_fee == Decimal("5000")
        assert result.total_fee == Decimal("6000")
        assert result.table_format == "horizontal"


class TestFeeNoticeInfo:
    def test_creation(self):
        from apps.fee_notice.services.types import DetectionResult, FeeAmountResult, FeeNoticeInfo

        detection = DetectionResult(is_fee_notice=True, page_num=1, confidence=0.9, matched_keywords=[])
        amounts = FeeAmountResult(acceptance_fee=Decimal("5000"))

        info = FeeNoticeInfo(
            file_name="notice.pdf",
            file_path="/path/to/notice.pdf",
            page_num=1,
            detection=detection,
            amounts=amounts,
            extraction_method="pdf_direct",
        )
        assert info.file_name == "notice.pdf"
        assert info.extraction_method == "pdf_direct"


class TestFeeNoticeExtractionResult:
    def test_default_creation(self):
        from apps.fee_notice.services.types import FeeNoticeExtractionResult

        result = FeeNoticeExtractionResult(
            notices=[],
            total_files=0,
            total_pages=0,
            errors=[],
        )
        assert result.total_files == 0
        assert result.debug_logs == []

    def test_with_errors(self):
        from apps.fee_notice.services.types import FeeNoticeExtractionResult

        result = FeeNoticeExtractionResult(
            notices=[],
            total_files=1,
            total_pages=5,
            errors=[{"file": "bad.pdf", "error": "corrupt"}],
        )
        assert len(result.errors) == 1


class TestCaseComparisonInfo:
    def test_creation(self):
        from apps.fee_notice.services.types import CaseComparisonInfo

        info = CaseComparisonInfo(
            case_id=1,
            case_name="测试案件",
            case_number="（2024）粤0606执386号",
            target_amount=Decimal("100000"),
        )
        assert info.case_id == 1
        assert info.is_complete is False
        assert info.incomplete_reason is None

    def test_complete_info(self):
        from apps.fee_notice.services.types import CaseComparisonInfo

        info = CaseComparisonInfo(
            case_id=1,
            case_name="测试",
            cause_of_action_name="合同纠纷",
            target_amount=Decimal("100000"),
            is_complete=True,
        )
        assert info.is_complete is True


class TestCaseSearchResult:
    def test_creation(self):
        from apps.fee_notice.services.types import CaseSearchResult

        result = CaseSearchResult(id=1, name="测试案件")
        assert result.id == 1
        assert result.case_number is None

    def test_with_all_fields(self):
        from apps.fee_notice.services.types import CaseSearchResult

        result = CaseSearchResult(
            id=1,
            name="测试",
            case_number="（2024）粤0606执386号",
            cause_of_action="合同纠纷",
            target_amount=Decimal("100000"),
        )
        assert result.cause_of_action == "合同纠纷"


class TestFeeComparisonResult:
    def test_default_creation(self):
        from apps.fee_notice.services.types import CaseComparisonInfo, FeeComparisonResult

        case_info = CaseComparisonInfo(case_id=1, case_name="测试")
        result = FeeComparisonResult(case_info=case_info)
        assert result.acceptance_fee_match is False
        assert result.can_compare is True

    def test_match_result(self):
        from apps.fee_notice.services.types import CaseComparisonInfo, FeeComparisonResult

        case_info = CaseComparisonInfo(case_id=1, case_name="测试")
        result = FeeComparisonResult(
            case_info=case_info,
            extracted_acceptance_fee=Decimal("5000"),
            calculated_acceptance_fee=Decimal("5000"),
            acceptance_fee_match=True,
            acceptance_fee_diff=Decimal("0"),
        )
        assert result.acceptance_fee_match is True


# ============================================================================
# express_query/services/tracking_extraction_service.py tests
# ============================================================================


class TestTrackingExtractionResult:
    def test_creation(self):
        from apps.express_query.services.tracking_extraction_service import TrackingExtractionResult

        result = TrackingExtractionResult(
            carrier_type="sf",
            tracking_number="SF1234567890123",
            ocr_text="顺丰快递单号SF1234567890123",
        )
        assert result.carrier_type == "sf"
        assert result.tracking_number == "SF1234567890123"


class TestTrackingExtractionServicePatterns:
    def test_sf_pattern(self):
        from apps.express_query.services.tracking_extraction_service import TrackingExtractionService

        assert TrackingExtractionService._sf_pattern.search("SF1234567890123") is not None

    def test_ems_pattern(self):
        from apps.express_query.services.tracking_extraction_service import TrackingExtractionService

        assert TrackingExtractionService._ems_pattern.search("1234567890123") is not None

    def test_sf_no_match_short(self):
        from apps.express_query.services.tracking_extraction_service import TrackingExtractionService

        assert TrackingExtractionService._sf_pattern.search("SF123") is None

    def test_ems_no_match_short(self):
        from apps.express_query.services.tracking_extraction_service import TrackingExtractionService

        assert TrackingExtractionService._ems_pattern.search("12345") is None


class TestTrackingExtractionPickTrackingNumber:
    def test_sf_number(self):
        from apps.express_query.services.tracking_extraction_service import TrackingExtractionService

        service = TrackingExtractionService.__new__(TrackingExtractionService)
        result = service._pick_tracking_number("顺丰快递 SF1234567890123 已签收")
        assert result is not None
        assert result["carrier"] == "sf"
        assert "SF1234567890123" in result["tracking_number"]

    def test_no_tracking_number(self):
        from apps.express_query.services.tracking_extraction_service import TrackingExtractionService

        service = TrackingExtractionService.__new__(TrackingExtractionService)
        result = service._pick_tracking_number("没有运单号的文本")
        assert result is None


class TestTrackingExtractionTruncatePdf:
    def test_non_pdf_returns_false(self, tmp_path):
        from apps.express_query.services.tracking_extraction_service import TrackingExtractionService

        txt_file = tmp_path / "test.txt"
        txt_file.write_text("hello")
        assert TrackingExtractionService.truncate_pdf_to_first_page(txt_file) is False
