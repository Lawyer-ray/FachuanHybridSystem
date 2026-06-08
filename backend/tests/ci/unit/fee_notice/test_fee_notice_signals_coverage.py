"""Coverage tests for fee_notice.services.types and chat_records.signals."""

from unittest.mock import MagicMock, patch

import pytest

from decimal import Decimal


class TestFeeNoticeTypes:
    def test_detection_result(self):
        from apps.fee_notice.services.types import DetectionResult

        r = DetectionResult(is_fee_notice=True, page_num=1, confidence=0.95, matched_keywords=["受理费"])
        assert r.is_fee_notice is True
        assert r.confidence == 0.95

    def test_fee_amount_result(self):
        from apps.fee_notice.services.types import FeeAmountResult

        r = FeeAmountResult(
            acceptance_fee=Decimal("1000"),
            total_fee=Decimal("1500"),
        )
        assert r.acceptance_fee == Decimal("1000")
        assert r.table_format == "unknown"

    def test_fee_notice_info(self):
        from apps.fee_notice.services.types import FeeNoticeInfo, DetectionResult, FeeAmountResult

        det = DetectionResult(is_fee_notice=True, page_num=1, confidence=0.9, matched_keywords=[])
        amt = FeeAmountResult()
        info = FeeNoticeInfo(
            file_name="test.pdf",
            file_path="/tmp/test.pdf",
            page_num=1,
            detection=det,
            amounts=amt,
            extraction_method="pdf_direct",
        )
        assert info.file_name == "test.pdf"

    def test_fee_notice_extraction_result(self):
        from apps.fee_notice.services.types import FeeNoticeExtractionResult

        r = FeeNoticeExtractionResult(notices=[], total_files=1, total_pages=5, errors=[])
        assert r.total_files == 1

    def test_case_comparison_info(self):
        from apps.fee_notice.services.types import CaseComparisonInfo

        info = CaseComparisonInfo(case_id=1, case_name="Test Case")
        assert info.is_complete is False

    def test_case_search_result(self):
        from apps.fee_notice.services.types import CaseSearchResult

        r = CaseSearchResult(id=1, name="Test")
        assert r.case_number is None

    def test_fee_comparison_result(self):
        from apps.fee_notice.services.types import FeeComparisonResult, CaseComparisonInfo

        case = CaseComparisonInfo(case_id=1, case_name="Test")
        r = FeeComparisonResult(case_info=case)
        assert r.can_compare is True


class TestChatRecordsSignals:
    def test_safe_prune_empty_parents_none(self):
        from apps.chat_records.signals import _safe_prune_empty_parents

        _safe_prune_empty_parents(None)
        # Should not raise

    def test_safe_prune_empty_parents_empty_string(self):
        from apps.chat_records.signals import _safe_prune_empty_parents

        _safe_prune_empty_parents("")
        # Should not raise

    def test_delete_field_file_none(self):
        from apps.chat_records.signals import _delete_field_file

        _delete_field_file(None)
        # Should not raise

    def test_delete_field_file_with_mock(self):
        from apps.chat_records.signals import _delete_field_file

        mock_file = MagicMock()
        mock_file.path = "/tmp/test.txt"
        _delete_field_file(mock_file)
        mock_file.delete.assert_called_once_with(save=False)

    def test_delete_field_file_by_name_none(self):
        from apps.chat_records.signals import _delete_field_file_by_name

        _delete_field_file_by_name(None)
        # Should not raise

    def test_delete_field_file_by_name_empty(self):
        from apps.chat_records.signals import _delete_field_file_by_name

        _delete_field_file_by_name("")
        # Should not raise
