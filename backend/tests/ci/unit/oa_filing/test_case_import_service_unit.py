"""case_import_service.py 单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.models.enums import CaseType


class TestCaseImportServiceParseDate:

    @pytest.mark.parametrize("date_str,expected_year", [
        ("2024/01/15", 2024),
        ("2024-01-15", 2024),
        ("2024年01月15日", 2024),
        ("01/15/2024", 2024),
    ])
    def test_parse_date_formats(self, date_str, expected_year):
        from apps.oa_filing.services.case_import_service import CaseImportService
        result = CaseImportService._parse_date(date_str)
        assert result is not None
        assert result.year == expected_year

    def test_empty_returns_none(self):
        from apps.oa_filing.services.case_import_service import CaseImportService
        assert CaseImportService._parse_date("") is None

    def test_none_returns_none(self):
        from apps.oa_filing.services.case_import_service import CaseImportService
        assert CaseImportService._parse_date(None) is None

    def test_invalid_returns_none(self):
        from apps.oa_filing.services.case_import_service import CaseImportService
        assert CaseImportService._parse_date("not a date") is None

    def test_date_with_time_strips_time(self):
        from apps.oa_filing.services.case_import_service import CaseImportService
        result = CaseImportService._parse_date("2024/01/15 10:30:00")
        assert result is not None
        assert result.year == 2024


class TestCaseImportServiceMapOaCaseType:

    def _make_service(self):
        from apps.oa_filing.services.case_import_service import CaseImportService
        session = MagicMock()
        return CaseImportService(session)

    def test_civil_keywords(self):
        svc = self._make_service()
        assert svc._map_oa_case_type_from_text("民事案件") == CaseType.CIVIL
        assert svc._map_oa_case_type_from_text("合同纠纷") == CaseType.CIVIL

    def test_criminal_keywords(self):
        svc = self._make_service()
        assert svc._map_oa_case_type_from_text("刑事案件") == CaseType.CRIMINAL

    def test_administrative_keywords(self):
        svc = self._make_service()
        assert svc._map_oa_case_type_from_text("行政复议") == CaseType.ADMINISTRATIVE

    def test_labor_keywords(self):
        svc = self._make_service()
        assert svc._map_oa_case_type_from_text("劳动仲裁") == CaseType.LABOR

    def test_intl_keywords(self):
        svc = self._make_service()
        assert svc._map_oa_case_type_from_text("国际仲裁") == CaseType.INTL

    def test_advisor_keywords(self):
        svc = self._make_service()
        assert svc._map_oa_case_type_from_text("常年法律顾问") == CaseType.ADVISOR

    def test_special_keywords(self):
        svc = self._make_service()
        assert svc._map_oa_case_type_from_text("专项法律服务") == CaseType.SPECIAL

    def test_code_mapping(self):
        svc = self._make_service()
        assert svc._map_oa_case_type_from_text("03") == CaseType.CIVIL
        assert svc._map_oa_case_type_from_text("05") == CaseType.CRIMINAL

    def test_empty_returns_none(self):
        svc = self._make_service()
        assert svc._map_oa_case_type_from_text("") is None
        assert svc._map_oa_case_type_from_text(None) is None

    def test_unknown_returns_none(self):
        svc = self._make_service()
        assert svc._map_oa_case_type_from_text("完全未知的类别XYZ") is None


class TestCaseImportServiceMapOaCaseTypeCombo:

    def _make_service(self):
        from apps.oa_filing.services.case_import_service import CaseImportService
        session = MagicMock()
        return CaseImportService(session)

    def test_labor_priority_over_intl(self):
        """当案件类别=仲裁案件(INTL)，业务种类=劳动仲裁(LABOR)时，优先返回LABOR"""
        svc = self._make_service()
        result = svc._map_oa_case_type("仲裁案件", "劳动仲裁")
        assert result == CaseType.LABOR

    def test_category_priority(self):
        svc = self._make_service()
        result = svc._map_oa_case_type("民事案件", None)
        assert result == CaseType.CIVIL

    def test_fallback_to_business_type(self):
        svc = self._make_service()
        result = svc._map_oa_case_type(None, "刑事案件")
        assert result == CaseType.CRIMINAL

    def test_both_none(self):
        svc = self._make_service()
        assert svc._map_oa_case_type(None, None) is None


class TestCaseImportServiceShouldCreateCase:

    def _make_service(self):
        from apps.oa_filing.services.case_import_service import CaseImportService
        session = MagicMock()
        return CaseImportService(session)

    @pytest.mark.parametrize("case_type,expected", [
        (CaseType.CIVIL, True),
        (CaseType.CRIMINAL, True),
        (CaseType.ADMINISTRATIVE, True),
        (CaseType.LABOR, True),
        (CaseType.INTL, True),
        (CaseType.ADVISOR, False),
        (CaseType.SPECIAL, False),
        (None, False),
    ])
    def test_should_create_case(self, case_type, expected):
        svc = self._make_service()
        assert svc._should_create_case_for_contract_type(case_type) == expected


class TestCaseImportServiceResolveSearchWorkers:

    def _make_service(self):
        from apps.oa_filing.services.case_import_service import CaseImportService
        session = MagicMock()
        return CaseImportService(session)

    def test_single_case_returns_1(self):
        svc = self._make_service()
        assert svc._resolve_search_workers(1) == 1

    def test_zero_returns_1(self):
        svc = self._make_service()
        assert svc._resolve_search_workers(0) == 1

    @patch.dict("os.environ", {"OA_CASE_IMPORT_SEARCH_WORKERS": "3"})
    def test_uses_env_var(self):
        svc = self._make_service()
        assert svc._resolve_search_workers(10) == 3

    @patch.dict("os.environ", {"OA_CASE_IMPORT_SEARCH_WORKERS": "invalid"})
    def test_invalid_env_var_fallback(self):
        svc = self._make_service()
        assert svc._resolve_search_workers(10) == 2


class TestCaseImportResult:

    def test_creation(self):
        from apps.oa_filing.services.case_import_service import CaseImportResult
        result = CaseImportResult(
            case_no="CASE001",
            status="created",
            contract_id=1,
            message="ok",
        )
        assert result.case_no == "CASE001"
        assert result.status == "created"


class TestCasePreviewResult:

    def test_creation(self):
        from apps.oa_filing.services.case_import_service import CasePreviewResult
        result = CasePreviewResult(
            case_no="CASE001",
            status="matched",
            existing_contract_id=1,
            customer_names=["张三"],
        )
        assert result.status == "matched"
        assert "张三" in result.customer_names
