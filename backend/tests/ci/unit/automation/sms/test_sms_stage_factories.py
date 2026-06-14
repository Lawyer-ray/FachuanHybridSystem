"""Tests for sms_matching_stage pure functions and SMSRenamingStage factory."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.automation.services.sms.stages.sms_matching_stage import (
    SMSMatchingStage,
    create_sms_matching_stage,
    filter_valid_case_numbers,
)
from apps.automation.services.sms.stages.sms_renaming_stage import (
    SMSRenamingStage,
    create_sms_renaming_stage,
)


class TestFilterValidCaseNumbers:
    """Tests for the pure function filter_valid_case_numbers."""

    def test_empty_list(self) -> None:
        assert filter_valid_case_numbers([]) == []

    def test_valid_case_number_kept(self) -> None:
        result = filter_valid_case_numbers(["（2025）粤0604民初41257号"])
        assert result == ["（2025）粤0604民初41257号"]

    def test_date_with_ri_filtered(self) -> None:
        """Contains 年, 月, 日 → filtered."""
        assert filter_valid_case_numbers(["2025年10月1日"]) == []

    def test_date_with_hao_filtered(self) -> None:
        """Matches YYYY年M月D号 pattern exactly."""
        assert filter_valid_case_numbers(["2025年10月15号"]) == []

    def test_year_month_only_kept(self) -> None:
        """'2025年10月判决' doesn't contain 日 or end with 号 matching regex."""
        result = filter_valid_case_numbers(["2025年10月判决"])
        assert result == ["2025年10月判决"]

    def test_mixed_valid_and_invalid(self) -> None:
        nums = ["（2025）粤0604民初123号", "2025年10月1日", "（2024）京01民终567号"]
        result = filter_valid_case_numbers(nums)
        assert "2025年10月1日" not in result
        assert len(result) == 2

    def test_non_date_with_year_month_ri_chars(self) -> None:
        """Contains 年, 月, 日 so it is filtered."""
        assert filter_valid_case_numbers(["某年某月某日"]) == []


class TestSMSMatchingStage:
    def test_stage_name(self) -> None:
        stage = SMSMatchingStage()
        assert stage.stage_name == "匹配"

    def test_injected_deps(self) -> None:
        matcher = MagicMock()
        extractor = MagicMock()
        case_svc = MagicMock()
        lawyer_svc = MagicMock()
        stage = SMSMatchingStage(
            matcher=matcher,
            case_number_extractor=extractor,
            case_service=case_svc,
            lawyer_service=lawyer_svc,
        )
        assert stage.matcher is matcher
        assert stage.case_number_extractor is extractor
        assert stage.case_service is case_svc
        assert stage.lawyer_service is lawyer_svc


class TestSMSRenamingStage:
    def test_stage_name(self) -> None:
        stage = SMSRenamingStage()
        assert stage.stage_name == "重命名"

    def test_injected_deps(self) -> None:
        attachment = MagicMock()
        extractor = MagicMock()
        matcher = MagicMock()
        lawyer = MagicMock()
        stage = SMSRenamingStage(
            document_attachment=attachment,
            case_number_extractor=extractor,
            matcher=matcher,
            lawyer_service=lawyer,
        )
        assert stage.document_attachment is attachment
        assert stage.case_number_extractor is extractor
        assert stage.matcher is matcher
        assert stage.lawyer_service is lawyer


class TestFactoryFunctions:
    def test_create_sms_matching_stage(self) -> None:
        stage = create_sms_matching_stage()
        assert isinstance(stage, SMSMatchingStage)

    def test_create_sms_renaming_stage(self) -> None:
        stage = create_sms_renaming_stage()
        assert isinstance(stage, SMSRenamingStage)
