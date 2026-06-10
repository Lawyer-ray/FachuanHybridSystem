"""Extended tests for oa_filing services - import_session, script_executor, case_import, client_import."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.oa_filing.services.case_import_service import CaseImportService, CasePreviewResult
from apps.oa_filing.services.client_import_service import ClientImportService, ImportResult
from apps.oa_filing.services.script_executor_service import ScriptExecutorService


# ── ScriptExecutorService mapping methods ─────────────────────────────────────


class TestScriptExecutorServiceMappings:
    def setup_method(self):
        self.service = ScriptExecutorService()

    def test_map_case_category_civil(self):
        case = MagicMock(case_type="civil")
        assert self.service._map_case_category(case) == "03"

    def test_map_case_category_criminal(self):
        case = MagicMock(case_type="criminal")
        assert self.service._map_case_category(case) == "05"

    def test_map_case_category_administrative(self):
        case = MagicMock(case_type="administrative")
        assert self.service._map_case_category(case) == "04"

    def test_map_case_category_labor(self):
        case = MagicMock(case_type="labor")
        assert self.service._map_case_category(case) == "03"

    def test_map_case_category_intl(self):
        case = MagicMock(case_type="intl")
        assert self.service._map_case_category(case) == "06"

    def test_map_case_category_execution(self):
        case = MagicMock(case_type="execution")
        assert self.service._map_case_category(case) == "03"

    def test_map_case_category_bankruptcy(self):
        case = MagicMock(case_type="bankruptcy")
        assert self.service._map_case_category(case) == "03"

    def test_map_case_category_special(self):
        case = MagicMock(case_type="special")
        assert self.service._map_case_category(case) == "02"

    def test_map_case_category_advisor(self):
        case = MagicMock(case_type="advisor")
        assert self.service._map_case_category(case) == "01"

    def test_map_case_category_unknown(self):
        case = MagicMock(case_type="unknown")
        assert self.service._map_case_category(case) == "03"

    def test_map_case_stage_advisor_returns_empty(self):
        case = MagicMock(case_type="advisor")
        assert self.service._map_case_stage(case) == ""

    def test_map_case_stage_civil_first_trial(self):
        case = MagicMock(case_type="civil", current_stage="first_trial")
        assert self.service._map_case_stage(case) == "0301"

    def test_map_case_stage_civil_second_trial(self):
        case = MagicMock(case_type="civil", current_stage="second_trial")
        assert self.service._map_case_stage(case) == "0305"

    def test_map_case_stage_civil_enforcement(self):
        case = MagicMock(case_type="civil", current_stage="enforcement")
        assert self.service._map_case_stage(case) == "0314"

    def test_map_case_stage_admin_first_trial(self):
        case = MagicMock(case_type="administrative", current_stage="first_trial")
        assert self.service._map_case_stage(case) == "0402"

    def test_map_case_stage_criminal_first_trial(self):
        case = MagicMock(case_type="criminal", current_stage="first_trial")
        assert self.service._map_case_stage(case) == "0503"

    def test_map_fee_mode_fixed(self):
        contract = MagicMock(fee_mode="FIXED")
        assert self.service._map_fee_mode(contract) == "01"

    def test_map_fee_mode_semi_risk(self):
        contract = MagicMock(fee_mode="SEMI_RISK")
        assert self.service._map_fee_mode(contract) == "02"

    def test_map_fee_mode_full_risk(self):
        contract = MagicMock(fee_mode="FULL_RISK")
        assert self.service._map_fee_mode(contract) == "02"

    def test_map_fee_mode_custom(self):
        contract = MagicMock(fee_mode="CUSTOM")
        assert self.service._map_fee_mode(contract) == "01"

    def test_map_fee_mode_unknown(self):
        contract = MagicMock(fee_mode=None)
        assert self.service._map_fee_mode(contract) == "01"

    def test_map_kindtype_litigation_returns_empty(self):
        principal, sed = self.service._map_kindtype("03", [])
        assert principal == ""
        assert sed == ""

    def test_map_kindtype_advisor_enterprise(self):
        party = MagicMock()
        party.client.client_type = "legal"
        principal, sed = self.service._map_kindtype("01", [party])
        assert principal == "KindType01_01"
        assert sed == "KindType01_0103"

    def test_map_kindtype_advisor_natural(self):
        party = MagicMock()
        party.client.client_type = "natural"
        principal, sed = self.service._map_kindtype("01", [party])
        assert principal == "KindType01_05"
        assert sed == ""

    def test_map_kindtype_special_enterprise(self):
        party = MagicMock()
        party.client.client_type = "legal"
        principal, sed = self.service._map_kindtype("02", [party])
        assert principal == "KindType02_01"

    def test_map_kindtype_special_natural(self):
        party = MagicMock()
        party.client.client_type = "natural"
        principal, sed = self.service._map_kindtype("02", [party])
        assert principal == "KindType02_05"

    def test_dispatch_unsupported_site(self):
        with pytest.raises(Exception):
            self.service._dispatch("unsupported_site", MagicMock(), 1, None)


# ── CaseImportService mapping methods ────────────────────────────────────────


class TestCaseImportServiceMappings:
    def setup_method(self):
        self.session = MagicMock()
        self.session.credential = MagicMock()
        self.service = CaseImportService(self.session)

    def test_map_oa_case_type_from_text_code_01(self):
        assert self.service._map_oa_case_type_from_text("01") == "advisor"

    def test_map_oa_case_type_from_text_code_03(self):
        assert self.service._map_oa_case_type_from_text("03") == "civil"

    def test_map_oa_case_type_from_text_keyword_criminal(self):
        assert self.service._map_oa_case_type_from_text("刑事案件") == "criminal"

    def test_map_oa_case_type_from_text_keyword_admin(self):
        assert self.service._map_oa_case_type_from_text("行政复议") == "administrative"

    def test_map_oa_case_type_from_text_keyword_labor(self):
        assert self.service._map_oa_case_type_from_text("劳动仲裁") == "labor"

    def test_map_oa_case_type_from_text_keyword_intl(self):
        assert self.service._map_oa_case_type_from_text("商事仲裁") == "intl"

    def test_map_oa_case_type_from_text_keyword_special(self):
        assert self.service._map_oa_case_type_from_text("专项法律服务") == "special"

    def test_map_oa_case_type_from_text_keyword_civil(self):
        assert self.service._map_oa_case_type_from_text("民商事纠纷") == "civil"

    def test_map_oa_case_type_from_text_empty(self):
        assert self.service._map_oa_case_type_from_text("") is None

    def test_map_oa_case_type_from_text_none(self):
        assert self.service._map_oa_case_type_from_text(None) is None

    def test_map_oa_case_type_from_text_unknown(self):
        assert self.service._map_oa_case_type_from_text("未知类型") is None

    def test_map_oa_case_type_labor_priority(self):
        # When category is INTL but business type is LABOR, LABOR wins
        result = self.service._map_oa_case_type("仲裁案件", "劳动争议仲裁")
        assert result == "labor"

    def test_should_create_case_for_dispute_types(self):
        assert self.service._should_create_case_for_contract_type("civil") is True
        assert self.service._should_create_case_for_contract_type("criminal") is True
        assert self.service._should_create_case_for_contract_type("advisor") is False
        assert self.service._should_create_case_for_contract_type(None) is False

    def test_parse_date_iso(self):
        from datetime import date

        assert self.service._parse_date("2024-01-15") == date(2024, 1, 15)

    def test_parse_date_slash(self):
        from datetime import date

        assert self.service._parse_date("2024/01/15") == date(2024, 1, 15)

    def test_parse_date_chinese(self):
        from datetime import date

        assert self.service._parse_date("2024年01月15日") == date(2024, 1, 15)

    def test_parse_date_empty(self):
        assert self.service._parse_date("") is None

    def test_parse_date_invalid(self):
        assert self.service._parse_date("not a date") is None

    def test_check_conflicts(self):
        conflict = MagicMock()
        conflict.name = "对方公司"
        warnings = self.service._check_conflicts([conflict])
        assert len(warnings) == 1
        assert "对方公司" in warnings[0]

    def test_import_single_case_no_data(self):
        result = self.service._import_single_case_data("CASE001", None)
        assert result.status == "error"
        assert "未找到" in result.message

    def test_resolve_search_workers_single(self):
        assert self.service._resolve_search_workers(1) == 1

    def test_resolve_search_workers_multiple(self):
        workers = self.service._resolve_search_workers(10)
        assert workers >= 1


# ── ClientImportService ──────────────────────────────────────────────────────


class TestClientImportService:
    def setup_method(self):
        self.session = MagicMock()
        self.session.credential = MagicMock()
        self.session.pk = 1
        self.session.total_count = 0
        self.session.discovered_count = 0
        self.service = ClientImportService(self.service_session)

    @property
    def service_session(self):
        return self.session

    def _make_service(self):
        svc = ClientImportService.__new__(ClientImportService)
        svc._session = self.session
        svc._credential = MagicMock()
        return svc

    def test_to_int_valid(self):
        assert ClientImportService._to_int("42") == 42

    def test_to_int_invalid(self):
        assert ClientImportService._to_int("abc") == 0

    def test_to_int_none(self):
        assert ClientImportService._to_int(None) == 0

    def test_handle_script_progress_discovery_started(self):
        svc = self._make_service()
        with patch("apps.oa_filing.services.client_import_service.ClientImportSession") as mock_model:
            mock_model.objects.filter.return_value.update.return_value = None
            svc._handle_script_progress({"event": "discovery_started", "message": "开始查找"})

    def test_handle_script_progress_discovery_progress(self):
        svc = self._make_service()
        with patch("apps.oa_filing.services.client_import_service.ClientImportSession") as mock_model:
            mock_model.objects.filter.return_value.update.return_value = None
            svc._handle_script_progress({
                "event": "discovery_progress",
                "discovered_count": 10,
                "page": 2,
            })

    def test_handle_script_progress_discovery_completed(self):
        svc = self._make_service()
        with patch("apps.oa_filing.services.client_import_service.ClientImportSession") as mock_model:
            mock_model.objects.filter.return_value.update.return_value = None
            svc._handle_script_progress({
                "event": "discovery_completed",
                "total_count": 50,
            })

    def test_handle_script_progress_import_started(self):
        svc = self._make_service()
        with patch("apps.oa_filing.services.client_import_service.ClientImportSession") as mock_model:
            mock_model.objects.filter.return_value.update.return_value = None
            svc._handle_script_progress({
                "event": "import_started",
                "total_count": 50,
            })

    def test_handle_script_progress_import_progress(self):
        svc = self._make_service()
        with patch("apps.oa_filing.services.client_import_service.ClientImportSession") as mock_model:
            mock_model.objects.filter.return_value.update.return_value = None
            svc._handle_script_progress({
                "event": "import_progress",
                "index": 5,
                "total_count": 50,
                "name": "测试公司",
            })

    def test_handle_script_progress_unknown_event(self):
        svc = self._make_service()
        svc._handle_script_progress({"event": "unknown"})


# ── ImportResult ──────────────────────────────────────────────────────────────


class TestImportResult:
    def test_created(self):
        result = ImportResult(status="created", message="ok")
        assert result.status == "created"
        assert result.message == "ok"

    def test_skipped(self):
        result = ImportResult(status="skipped", message="exists")
        assert result.status == "skipped"


# ── CasePreviewResult ────────────────────────────────────────────────────────


class TestCasePreviewResult:
    def test_matched(self):
        result = CasePreviewResult(case_no="CASE001", status="matched", existing_contract_id=1)
        assert result.status == "matched"
        assert result.existing_contract_id == 1

    def test_unmatched(self):
        result = CasePreviewResult(case_no="CASE002", status="unmatched")
        assert result.existing_contract_id is None
