"""Tests for fee_notice check_service - pure dataclass tests only."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class TestFeeCheckItem:
    """Test FeeCheckItem dataclass."""

    def test_defaults(self):
        from apps.fee_notice.services.comparison.check_service import FeeCheckItem

        item = FeeCheckItem(file_name="test.pdf", file_path="/path/test.pdf")
        assert item.extracted_acceptance_fee is None
        assert item.acceptance_fee_match is False
        assert item.can_compare is True
        assert item.compare_message is None


class TestFeeCheckResult:
    """Test FeeCheckResult dataclass."""

    def test_defaults(self):
        from apps.fee_notice.services.comparison.check_service import FeeCheckResult

        result = FeeCheckResult()
        assert result.has_fee_notice is False
        assert result.items == []
        assert result.case_name is None

    def test_with_values(self):
        from apps.fee_notice.services.comparison.check_service import FeeCheckResult

        result = FeeCheckResult(
            has_fee_notice=True,
            case_name="Test Case",
            case_number="(2025)粤01民初1号",
            target_amount=Decimal("100000"),
        )
        assert result.has_fee_notice is True
        assert result.case_name == "Test Case"
        assert result.target_amount == Decimal("100000")


class TestFeeNoticeCheckServiceInit:
    """Test FeeNoticeCheckService initialization."""

    def test_default_init(self):
        from apps.fee_notice.services.comparison.check_service import FeeNoticeCheckService

        svc = FeeNoticeCheckService()
        assert svc._extraction_service is None
        assert svc._comparison_service is None

    def test_init_with_services(self):
        from apps.fee_notice.services.comparison.check_service import FeeNoticeCheckService

        mock_ext = MagicMock()
        mock_comp = MagicMock()
        svc = FeeNoticeCheckService(extraction_service=mock_ext, comparison_service=mock_comp)
        assert svc.extraction_service is mock_ext
        assert svc.comparison_service is mock_comp


class TestFeeNoticeCheckServiceFilterFeeNoticeFiles:
    """Test _filter_fee_notice_files."""

    def test_filters_by_keyword(self):
        from apps.fee_notice.services.comparison.check_service import FeeNoticeCheckService

        svc = FeeNoticeCheckService()
        paths = [
            "/path/交费通知书.pdf",
            "/path/起诉状.pdf",
            "/path/缴费通知书_张三.pdf",
            "/path/document.docx",
        ]
        result = svc._filter_fee_notice_files(paths)
        assert "/path/交费通知书.pdf" in result
        assert "/path/缴费通知书_张三.pdf" in result
        assert "/path/起诉状.pdf" not in result
        assert "/path/document.docx" not in result

    def test_empty_list(self):
        from apps.fee_notice.services.comparison.check_service import FeeNoticeCheckService

        svc = FeeNoticeCheckService()
        assert svc._filter_fee_notice_files([]) == []

    def test_all_keywords(self):
        from apps.fee_notice.services.comparison.check_service import FeeNoticeCheckService

        svc = FeeNoticeCheckService()
        for keyword in svc.FEE_NOTICE_KEYWORDS:
            paths = [f"/path/{keyword}.pdf"]
            result = svc._filter_fee_notice_files(paths)
            assert len(result) == 1, f"Keyword '{keyword}' not matched"


class TestFeeNoticeCheckServiceCheckFeeNotices:
    """Test check_fee_notices."""

    def test_no_case_binding(self):
        from apps.fee_notice.services.comparison.check_service import FeeNoticeCheckService

        svc = FeeNoticeCheckService()
        sms = SimpleNamespace(id=1, case=None)
        result = svc.check_fee_notices(sms, ["/path/test.pdf"])
        assert result.has_fee_notice is False

    def test_no_documents(self):
        from apps.fee_notice.services.comparison.check_service import FeeNoticeCheckService

        svc = FeeNoticeCheckService()
        sms = SimpleNamespace(id=1, case=SimpleNamespace(id=1))
        result = svc.check_fee_notices(sms, [])
        assert result.has_fee_notice is False


class TestFeeNoticeCheckServiceFormatFeishuMessage:
    """Test format_feishu_message."""

    def test_no_fee_notice(self):
        from apps.fee_notice.services.comparison.check_service import FeeNoticeCheckService, FeeCheckResult

        svc = FeeNoticeCheckService()
        result = FeeCheckResult(has_fee_notice=False)
        assert svc.format_feishu_message(result) is None

    def test_no_items(self):
        from apps.fee_notice.services.comparison.check_service import FeeNoticeCheckService, FeeCheckResult

        svc = FeeNoticeCheckService()
        result = FeeCheckResult(has_fee_notice=True, items=[])
        assert svc.format_feishu_message(result) is None

    def test_with_uncomparable_item(self):
        from apps.fee_notice.services.comparison.check_service import (
            FeeNoticeCheckService, FeeCheckResult, FeeCheckItem,
        )

        svc = FeeNoticeCheckService()
        item = FeeCheckItem(
            file_name="交费通知书.pdf", file_path="/path/交费通知书.pdf",
            can_compare=False, compare_message="案件信息不完整",
        )
        result = FeeCheckResult(has_fee_notice=True, items=[item])
        msg = svc.format_feishu_message(result)
        assert msg is not None
        assert "交费通知书" in msg

    def test_long_filename_truncated(self):
        from apps.fee_notice.services.comparison.check_service import (
            FeeNoticeCheckService, FeeCheckResult, FeeCheckItem,
        )

        svc = FeeNoticeCheckService()
        long_name = "a" * 50 + ".pdf"
        item = FeeCheckItem(file_name=long_name, file_path=f"/path/{long_name}", can_compare=False)
        result = FeeCheckResult(has_fee_notice=True, items=[item])
        msg = svc.format_feishu_message(result)
        assert msg is not None

    def test_format_acceptance_fee_match(self):
        """Test _format_acceptance_fee_line with match via a direct call.

        Note: format_feishu_message crashes when can_compare=True due to a source code bug
        where _format_preservation_fee_line is incorrectly defined as a nested function
        inside _format_acceptance_fee_line instead of as a class method.
        """
        from apps.fee_notice.services.comparison.check_service import FeeCheckItem

        svc = MagicMock()
        item = FeeCheckItem(
            file_name="test.pdf", file_path="/test.pdf",
            can_compare=True,
            extracted_acceptance_fee=Decimal("5000"),
            calculated_acceptance_fee=Decimal("5000"),
            acceptance_fee_match=True,
        )
        lines: list[str] = []
        from apps.fee_notice.services.comparison.check_service import FeeNoticeCheckService
        FeeNoticeCheckService._format_acceptance_fee_line(svc, item, lines)
        assert any("5,000" in l for l in lines)

    def test_format_acceptance_fee_close(self):
        """Test _format_acceptance_fee_line with close match."""
        from apps.fee_notice.services.comparison.check_service import FeeCheckItem, FeeNoticeCheckService

        svc = MagicMock()
        item = FeeCheckItem(
            file_name="test.pdf", file_path="/test.pdf",
            can_compare=True,
            extracted_acceptance_fee=Decimal("5001"),
            calculated_acceptance_fee=Decimal("5000"),
            acceptance_fee_close=True,
        )
        lines: list[str] = []
        FeeNoticeCheckService._format_acceptance_fee_line(svc, item, lines)
        assert len(lines) > 0

    def test_format_acceptance_fee_mismatch(self):
        """Test _format_acceptance_fee_line with mismatch."""
        from apps.fee_notice.services.comparison.check_service import FeeCheckItem, FeeNoticeCheckService

        svc = MagicMock()
        item = FeeCheckItem(
            file_name="test.pdf", file_path="/test.pdf",
            can_compare=True,
            extracted_acceptance_fee=Decimal("6000"),
            calculated_acceptance_fee=Decimal("5000"),
            acceptance_fee_diff=Decimal("1000"),
        )
        lines: list[str] = []
        FeeNoticeCheckService._format_acceptance_fee_line(svc, item, lines)
        assert len(lines) > 0

    def test_format_no_extracted_acceptance_fee(self):
        """Test _format_acceptance_fee_line with no extracted fee returns early."""
        from apps.fee_notice.services.comparison.check_service import FeeCheckItem, FeeNoticeCheckService

        svc = MagicMock()
        item = FeeCheckItem(
            file_name="test.pdf", file_path="/test.pdf",
            can_compare=True, extracted_acceptance_fee=None,
        )
        lines: list[str] = []
        FeeNoticeCheckService._format_acceptance_fee_line(svc, item, lines)
        assert len(lines) == 0  # Returns early when no extracted fee


class TestCaseMatcherHelpers:
    """Test case_matcher helper functions."""

    def test_detect_case_type_criminal(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        assert matcher._detect_case_type_from_number("（2025）粤01刑初1号") == "criminal"

    def test_detect_case_type_administrative(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        assert matcher._detect_case_type_from_number("（2025）粤01行初1号") == "administrative"

    def test_detect_case_type_civil(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        assert matcher._detect_case_type_from_number("（2025）粤01民初1号") == "civil"

    def test_detect_case_type_bankruptcy_returns_none(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        assert matcher._detect_case_type_from_number("（2025）粤01破1号") is None

    def test_detect_case_type_empty(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        assert matcher._detect_case_type_from_number("") is None

    def test_detect_stage_enforcement(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        assert matcher._detect_case_stage_from_number("（2025）粤01执1号") == "enforcement"

    def test_detect_stage_second_trial(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        assert matcher._detect_case_stage_from_number("（2025）粤01民终1号") == "second_trial"

    def test_detect_stage_first_trial(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        assert matcher._detect_case_stage_from_number("（2025）粤01民初1号") == "first_trial"

    def test_detect_stage_empty(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        assert matcher._detect_case_stage_from_number("") is None

    def test_is_bankruptcy_true(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        assert matcher._is_bankruptcy_case_number("（2025）粤01破1号") is True

    def test_is_bankruptcy_false(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        assert matcher._is_bankruptcy_case_number("（2025）粤01民初1号") is False

    def test_is_bankruptcy_empty(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        assert matcher._is_bankruptcy_case_number("") is False

    def test_select_latest_case_empty(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        assert matcher._select_latest_case([]) is None

    def test_select_latest_case_single(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        case = SimpleNamespace(id=1, name="Case 1", current_stage="first_trial")
        assert matcher._select_latest_case([case]) is case

    def test_select_latest_case_picks_highest_id(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        c1 = SimpleNamespace(id=1, name="C1", current_stage="first_trial")
        c2 = SimpleNamespace(id=5, name="C5", current_stage="first_trial")
        c3 = SimpleNamespace(id=3, name="C3", current_stage="first_trial")
        assert matcher._select_latest_case([c1, c2, c3]) is c2

    def test_apply_type_filter_match(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        c1 = SimpleNamespace(case_type="civil")
        c2 = SimpleNamespace(case_type="criminal")
        assert matcher._apply_type_filter([c1, c2], "civil") == [c1]

    def test_apply_type_filter_none_returns_all(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        c1 = SimpleNamespace(case_type="civil")
        assert matcher._apply_type_filter([c1], None) == [c1]

    def test_apply_stage_filter_match(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        c1 = SimpleNamespace(current_stage="first_trial")
        c2 = SimpleNamespace(current_stage="second_trial")
        assert matcher._apply_stage_filter([c1, c2], "first_trial") == [c1]

    def test_apply_stage_filter_none_returns_all(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        c1 = SimpleNamespace(current_stage="first_trial")
        assert matcher._apply_stage_filter([c1], None) == [c1]

    def test_filter_bankruptcy(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        c1 = SimpleNamespace(name="破产案件")
        c2 = SimpleNamespace(name="普通案件")
        result = matcher._filter_bankruptcy([c1, c2])
        assert c1 in result
        assert c2 not in result

    def test_filter_bankruptcy_no_match_returns_all(self):
        from apps.automation.services.sms.case_matcher import CaseMatcher
        matcher = CaseMatcher()
        c1 = SimpleNamespace(name="普通案件1")
        c2 = SimpleNamespace(name="普通案件2")
        result = matcher._filter_bankruptcy([c1, c2])
        assert len(result) == 2
