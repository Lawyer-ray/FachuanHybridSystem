"""
Refactored pure data processing tests for SMSMatchingStage.

Tests the extracted data filtering / validation logic that does NOT require
database, external API, or model instances.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest

from apps.automation.services.sms.stages.sms_matching_stage import SMSMatchingStage, filter_valid_case_numbers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stage() -> SMSMatchingStage:
    """Create SMSMatchingStage with all dependencies mocked."""
    return SMSMatchingStage(
        matcher=MagicMock(),
        case_number_extractor=MagicMock(),
        case_service=MagicMock(),
        lawyer_service=MagicMock(),
    )


# ═══════════════════════════════════════════════════════════════════════════
# _filter_valid_case_numbers
# ═══════════════════════════════════════════════════════════════════════════

class TestFilterValidCaseNumbers:
    """Test _filter_valid_case_numbers pure filtering logic."""

    def test_keeps_valid_case_number(self) -> None:
        """Standard case number is kept."""
        stage = _make_stage()
        result = stage._filter_valid_case_numbers(["（2025）粤0604民初123号"])
        assert result == ["（2025）粤0604民初123号"]

    def test_filters_date_with_year_month_day(self) -> None:
        """Date-like strings with 年月日 are filtered out."""
        stage = _make_stage()
        result = stage._filter_valid_case_numbers(["2025年6月1日", "（2025）粤0604民初123号"])
        assert result == ["（2025）粤0604民初123号"]

    def test_filters_date_ending_with_hao(self) -> None:
        """Date-like strings matching the regex pattern are filtered."""
        stage = _make_stage()
        result = stage._filter_valid_case_numbers(["2025年6月1号"])
        assert result == []

    def test_empty_list_returns_empty(self) -> None:
        """Empty input returns empty list."""
        stage = _make_stage()
        result = stage._filter_valid_case_numbers([])
        assert result == []

    def test_all_invalid_returns_empty(self) -> None:
        """All date-like inputs returns empty list."""
        stage = _make_stage()
        result = stage._filter_valid_case_numbers(["2025年6月1日", "2024年12月31日"])
        assert result == []

    def test_all_valid_returns_all(self) -> None:
        """All valid case numbers are returned."""
        stage = _make_stage()
        nums = ["（2025）粤0604民初123号", "（2024）京0101民初456号"]
        result = stage._filter_valid_case_numbers(nums)
        assert result == nums

    def test_mixed_valid_and_invalid(self) -> None:
        """Mix of valid and date-like strings filters correctly."""
        stage = _make_stage()
        result = stage._filter_valid_case_numbers([
            "2025年6月1日",
            "（2025）粤0604民初123号",
            "2024年12月31日",
            "（2024）京0101民初456号",
        ])
        assert result == ["（2025）粤0604民初123号", "（2024）京0101民初456号"]

    def test_string_with_year_month_but_not_date(self) -> None:
        """String with 年月 but not matching date pattern is kept."""
        stage = _make_stage()
        # "某某年某月某某号" is not a date pattern
        result = stage._filter_valid_case_numbers(["2025年某某月某某号"])
        # This has 年 and 月 but not 日, and doesn't match the regex
        assert result == ["2025年某某月某某号"]

    def test_string_with_only_year_and_month_no_day(self) -> None:
        """String with 年 and 月 but no 日 is not filtered by first check,
        but if it matches the regex it's filtered."""
        stage = _make_stage()
        # "2025年6月" has 年 and 月 but no 日, so first check passes
        result = stage._filter_valid_case_numbers(["2025年6月"])
        assert result == ["2025年6月"]

    def test_preserves_order(self) -> None:
        """Output order matches input order for valid items."""
        stage = _make_stage()
        result = stage._filter_valid_case_numbers([
            "（2025）粤001号",
            "2025年6月1日",
            "（2025）粤002号",
            "（2025）粤003号",
        ])
        assert result == ["（2025）粤001号", "（2025）粤002号", "（2025）粤003号"]


# ═══════════════════════════════════════════════════════════════════════════
# stage_name property
# ═══════════════════════════════════════════════════════════════════════════

class TestStageName:
    """Test stage_name returns correct constant."""

    def test_stage_name_is_matching(self) -> None:
        stage = _make_stage()
        assert stage.stage_name == "匹配"


# ═══════════════════════════════════════════════════════════════════════════
# can_process logic
# ═══════════════════════════════════════════════════════════════════════════

class TestCanProcess:
    """Test can_process status check logic."""

    def test_can_process_matching_status(self) -> None:
        """SMS with MATCHING status can be processed."""
        from apps.automation.models import CourtSMSStatus
        stage = _make_stage()
        sms = MagicMock()
        sms.status = CourtSMSStatus.MATCHING
        assert stage.can_process(sms) is True

    def test_cannot_process_other_status(self) -> None:
        """SMS with non-MATCHING status cannot be processed."""
        from apps.automation.models import CourtSMSStatus
        stage = _make_stage()
        sms = MagicMock()
        sms.status = CourtSMSStatus.RENAMING
        assert stage.can_process(sms) is False


# ═══════════════════════════════════════════════════════════════════════════
# Module-level pure function: filter_valid_case_numbers
# ═══════════════════════════════════════════════════════════════════════════

class TestFilterValidCaseNumbersPureFunction:
    """Test filter_valid_case_numbers as a module-level pure function."""

    def test_keeps_valid_case_number(self) -> None:
        result = filter_valid_case_numbers(["（2025）粤0604民初123号"])
        assert result == ["（2025）粤0604民初123号"]

    def test_filters_date_with_year_month_day(self) -> None:
        result = filter_valid_case_numbers(["2025年6月1日", "（2025）粤0604民初123号"])
        assert result == ["（2025）粤0604民初123号"]

    def test_empty_list(self) -> None:
        assert filter_valid_case_numbers([]) == []

    def test_all_date_strings(self) -> None:
        result = filter_valid_case_numbers(["2025年6月1日", "2024年12月31日"])
        assert result == []

    def test_mixed_input(self) -> None:
        result = filter_valid_case_numbers([
            "2025年6月1日",
            "（2025）粤0604民初123号",
            "2024年12月31日",
            "（2024）京0101民初456号",
        ])
        assert result == ["（2025）粤0604民初123号", "（2024）京0101民初456号"]

    def test_preserves_order(self) -> None:
        result = filter_valid_case_numbers(["CN001", "2025年1月1日", "CN002", "CN003"])
        assert result == ["CN001", "CN002", "CN003"]
