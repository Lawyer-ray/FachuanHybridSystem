"""Tests for case_import_service module-level pure functions."""

from __future__ import annotations

from datetime import date

from apps.core.models.enums import CaseType
from apps.oa_filing.services.case_import_service import (
    map_oa_case_type_from_text,
    parse_date,
    should_create_case_for_contract_type,
)


class TestMapOaCaseTypeFromText:
    def test_code_03_civil(self) -> None:
        assert map_oa_case_type_from_text("03") == CaseType.CIVIL

    def test_code_01_advisor(self) -> None:
        assert map_oa_case_type_from_text("01") == CaseType.ADVISOR

    def test_code_05_criminal(self) -> None:
        assert map_oa_case_type_from_text("05") == CaseType.CRIMINAL

    def test_keyword_civil(self) -> None:
        assert map_oa_case_type_from_text("民商事") == CaseType.CIVIL
        assert map_oa_case_type_from_text("民事") == CaseType.CIVIL

    def test_keyword_criminal(self) -> None:
        assert map_oa_case_type_from_text("刑事") == CaseType.CRIMINAL

    def test_keyword_administrative(self) -> None:
        assert map_oa_case_type_from_text("行政") == CaseType.ADMINISTRATIVE

    def test_keyword_labor(self) -> None:
        assert map_oa_case_type_from_text("劳动仲裁") == CaseType.LABOR

    def test_keyword_intl(self) -> None:
        assert map_oa_case_type_from_text("仲裁案件") == CaseType.INTL

    def test_keyword_special(self) -> None:
        assert map_oa_case_type_from_text("专项法律服务") == CaseType.SPECIAL
        assert map_oa_case_type_from_text("尽调") == CaseType.SPECIAL

    def test_keyword_advisor(self) -> None:
        assert map_oa_case_type_from_text("常年法律顾问") == CaseType.ADVISOR

    def test_none(self) -> None:
        assert map_oa_case_type_from_text(None) is None

    def test_empty(self) -> None:
        assert map_oa_case_type_from_text("") is None

    def test_whitespace_handling(self) -> None:
        assert map_oa_case_type_from_text("  03  ") == CaseType.CIVIL

    def test_unknown_returns_none(self) -> None:
        assert map_oa_case_type_from_text("完全未知类型") is None


class TestParseDate:
    def test_yyyy_mm_dd(self) -> None:
        result = parse_date("2024-01-15")
        assert result == date(2024, 1, 15)

    def test_yyyy_slash_mm_dd(self) -> None:
        result = parse_date("2024/01/15")
        assert result == date(2024, 1, 15)

    def test_chinese_format(self) -> None:
        result = parse_date("2024年1月15日")
        assert result == date(2024, 1, 15)

    def test_with_time_part(self) -> None:
        result = parse_date("2024-01-15 10:30:00")
        assert result == date(2024, 1, 15)

    def test_empty(self) -> None:
        assert parse_date("") is None

    def test_invalid(self) -> None:
        assert parse_date("not a date") is None


class TestShouldCreateCaseForContractType:
    def test_civil(self) -> None:
        assert should_create_case_for_contract_type(CaseType.CIVIL) is True

    def test_criminal(self) -> None:
        assert should_create_case_for_contract_type(CaseType.CRIMINAL) is True

    def test_labor(self) -> None:
        assert should_create_case_for_contract_type(CaseType.LABOR) is True

    def test_advisor_not_allowed(self) -> None:
        assert should_create_case_for_contract_type(CaseType.ADVISOR) is False

    def test_special_not_allowed(self) -> None:
        assert should_create_case_for_contract_type(CaseType.SPECIAL) is False

    def test_none(self) -> None:
        assert should_create_case_for_contract_type(None) is False
