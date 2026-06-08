"""Tests for CaseImportService."""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.models.enums import CaseType
from apps.oa_filing.services.case_import_service import (
    CaseImportResult,
    CaseImportService,
    CasePreviewResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(**overrides: Any) -> MagicMock:
    session = MagicMock()
    session.pk = overrides.get("pk", 1)
    session.credential = MagicMock()
    session.credential.account = "user@test.com"  # allowlist secret
    session.credential.password = "pass"  # allowlist secret
    session.started_at = None
    return session


def _make_service(**overrides: Any) -> CaseImportService:
    session = overrides.get("session", _make_session())
    return CaseImportService(session)


# ===========================================================================
# Data class tests
# ===========================================================================


class TestCasePreviewResult:
    def test_creation(self) -> None:
        r = CasePreviewResult(case_no="c1", status="matched", existing_contract_id=10, customer_names=["张三"])
        assert r.case_no == "c1"
        assert r.status == "matched"
        assert r.existing_contract_id == 10
        assert r.customer_names == ["张三"]

    def test_defaults(self) -> None:
        r = CasePreviewResult(case_no="c2", status="unmatched")
        assert r.existing_contract_id is None
        assert r.customer_names is None
        assert r.error_message == ""


class TestCaseImportResult:
    def test_creation(self) -> None:
        r = CaseImportResult(case_no="c1", status="created", contract_id=5, message="ok", customer_ids=[1], conflict_warnings=["w1"])
        assert r.contract_id == 5
        assert r.conflict_warnings == ["w1"]

    def test_defaults(self) -> None:
        r = CaseImportResult(case_no="c2", status="error")
        assert r.contract_id is None
        assert r.customer_ids is None
        assert r.conflict_warnings is None


# ===========================================================================
# parse_date tests
# ===========================================================================


class TestParseDate:
    def test_slash_format(self) -> None:
        assert CaseImportService._parse_date("2024/06/01") == date(2024, 6, 1)

    def test_dash_format(self) -> None:
        assert CaseImportService._parse_date("2024-06-01") == date(2024, 6, 1)

    def test_chinese_format(self) -> None:
        assert CaseImportService._parse_date("2024年6月1日") == date(2024, 6, 1)

    def test_us_format(self) -> None:
        assert CaseImportService._parse_date("06/01/2024") == date(2024, 6, 1)

    def test_with_time(self) -> None:
        assert CaseImportService._parse_date("2024/06/01 10:30:00") == date(2024, 6, 1)

    def test_empty_string(self) -> None:
        assert CaseImportService._parse_date("") is None

    def test_none(self) -> None:
        assert CaseImportService._parse_date(None) is None  # type: ignore[arg-type]

    def test_invalid_format(self) -> None:
        assert CaseImportService._parse_date("not-a-date") is None


# ===========================================================================
# map_oa_case_type_from_text tests
# ===========================================================================


class TestMapOaCaseTypeFromText:
    def test_code_01_advisor(self) -> None:
        svc = _make_service()
        assert svc._map_oa_case_type_from_text("01") == CaseType.ADVISOR

    def test_code_03_civil(self) -> None:
        svc = _make_service()
        assert svc._map_oa_case_type_from_text("03") == CaseType.CIVIL

    def test_code_06_intl(self) -> None:
        svc = _make_service()
        assert svc._map_oa_case_type_from_text("06") == CaseType.INTL

    def test_criminal_keyword(self) -> None:
        svc = _make_service()
        assert svc._map_oa_case_type_from_text("刑事犯罪案件") == CaseType.CRIMINAL

    def test_administrative_keyword(self) -> None:
        svc = _make_service()
        assert svc._map_oa_case_type_from_text("行政复议") == CaseType.ADMINISTRATIVE

    def test_labor_keyword(self) -> None:
        svc = _make_service()
        assert svc._map_oa_case_type_from_text("劳动仲裁") == CaseType.LABOR

    def test_intl_arbitration(self) -> None:
        svc = _make_service()
        assert svc._map_oa_case_type_from_text("国际仲裁") == CaseType.INTL

    def test_special_keyword(self) -> None:
        svc = _make_service()
        assert svc._map_oa_case_type_from_text("专项法律服务") == CaseType.SPECIAL

    def test_civil_keyword(self) -> None:
        svc = _make_service()
        assert svc._map_oa_case_type_from_text("民商事合同纠纷") == CaseType.CIVIL

    def test_advisor_keyword(self) -> None:
        svc = _make_service()
        assert svc._map_oa_case_type_from_text("常年法律顾问") == CaseType.ADVISOR

    def test_empty(self) -> None:
        svc = _make_service()
        assert svc._map_oa_case_type_from_text("") is None

    def test_none(self) -> None:
        svc = _make_service()
        assert svc._map_oa_case_type_from_text(None) is None

    def test_whitespace_only(self) -> None:
        svc = _make_service()
        assert svc._map_oa_case_type_from_text("   ") is None

    def test_case_insensitive(self) -> None:
        svc = _make_service()
        assert svc._map_oa_case_type_from_text("  劳动仲裁  ") == CaseType.LABOR


# ===========================================================================
# map_oa_case_type tests
# ===========================================================================


class TestMapOaCaseType:
    def test_category_priority(self) -> None:
        svc = _make_service()
        result = svc._map_oa_case_type("刑事", "民事")
        assert result == CaseType.CRIMINAL

    def test_fallback_to_business(self) -> None:
        svc = _make_service()
        result = svc._map_oa_case_type(None, "民事")
        assert result == CaseType.CIVIL

    def test_labor_override_intl(self) -> None:
        """仲裁案件(国际) + 劳动仲裁 → 应落劳动仲裁."""
        svc = _make_service()
        result = svc._map_oa_case_type("仲裁案件", "劳动仲裁")
        assert result == CaseType.LABOR

    def test_both_none(self) -> None:
        svc = _make_service()
        result = svc._map_oa_case_type(None, None)
        assert result is None


# ===========================================================================
# should_create_case_for_contract_type tests
# ===========================================================================


class TestShouldCreateCaseForContractType:
    def test_civil(self) -> None:
        svc = _make_service()
        assert svc._should_create_case_for_contract_type(CaseType.CIVIL) is True

    def test_criminal(self) -> None:
        svc = _make_service()
        assert svc._should_create_case_for_contract_type(CaseType.CRIMINAL) is True

    def test_advisor(self) -> None:
        svc = _make_service()
        assert svc._should_create_case_for_contract_type(CaseType.ADVISOR) is False

    def test_special(self) -> None:
        svc = _make_service()
        assert svc._should_create_case_for_contract_type(CaseType.SPECIAL) is False

    def test_none(self) -> None:
        svc = _make_service()
        assert svc._should_create_case_for_contract_type(None) is False

    def test_empty_string(self) -> None:
        svc = _make_service()
        assert svc._should_create_case_for_contract_type("") is False


# ===========================================================================
# check_conflicts tests
# ===========================================================================


class TestCheckConflicts:
    def test_with_conflicts(self) -> None:
        svc = _make_service()
        c1 = MagicMock()
        c1.name = "张三"
        c2 = MagicMock()
        c2.name = "李四"
        warnings = svc._check_conflicts([c1, c2])
        assert len(warnings) == 2
        assert "张三" in warnings[0]
        assert "李四" in warnings[1]

    def test_no_conflicts(self) -> None:
        svc = _make_service()
        warnings = svc._check_conflicts([])
        assert warnings == []


# ===========================================================================
# credential property tests
# ===========================================================================


class TestCredentialProperty:
    def test_returns_credential(self) -> None:
        session = _make_session()
        svc = CaseImportService(session)
        assert svc.credential is session.credential

    def test_caches_credential(self) -> None:
        session = _make_session()
        svc = CaseImportService(session)
        c1 = svc.credential
        c2 = svc.credential
        assert c1 is c2


# ===========================================================================
# resolve_search_workers tests
# ===========================================================================


class TestResolveSearchWorkers:
    def test_single_case(self) -> None:
        svc = _make_service()
        assert svc._resolve_search_workers(1) == 1

    def test_env_override(self) -> None:
        svc = _make_service()
        with patch.dict("os.environ", {"OA_CASE_IMPORT_SEARCH_WORKERS": "4"}):
            result = svc._resolve_search_workers(10)
            assert result == 4

    def test_invalid_env_fallback(self) -> None:
        svc = _make_service()
        with patch.dict("os.environ", {"OA_CASE_IMPORT_SEARCH_WORKERS": "invalid"}):
            result = svc._resolve_search_workers(10)
            assert result == 2

    def test_clamped_to_total(self) -> None:
        svc = _make_service()
        with patch.dict("os.environ", {"OA_CASE_IMPORT_SEARCH_WORKERS": "100"}):
            result = svc._resolve_search_workers(5)
            assert result == 5

    def test_min_1(self) -> None:
        svc = _make_service()
        with patch.dict("os.environ", {"OA_CASE_IMPORT_SEARCH_WORKERS": "0"}):
            result = svc._resolve_search_workers(10)
            assert result == 1


# ===========================================================================
# handle_script_progress tests
# ===========================================================================


class TestHandleScriptProgress:
    def test_searching_event(self) -> None:
        svc = _make_service()
        with patch.object(svc, "_update_session") as mock_update:
            svc._handle_script_progress({"event": "searching", "case_no": "2024-cv-1"})
            mock_update.assert_called_once()

    def test_other_event_noop(self) -> None:
        svc = _make_service()
        with patch.object(svc, "_update_session") as mock_update:
            svc._handle_script_progress({"event": "other"})
            mock_update.assert_not_called()


# ===========================================================================
# update_session tests
# ===========================================================================


class TestUpdateSession:
    def test_updates_fields(self) -> None:
        session = _make_session()
        svc = CaseImportService(session)
        with patch("apps.oa_filing.services.case_import_service.CaseImportSession") as MockSession:
            svc._update_session(status="completed", progress_message="done")
            MockSession.objects.filter.return_value.update.assert_called_once()
            assert session.status == "completed"
            assert session.progress_message == "done"

    def test_empty_fields_noop(self) -> None:
        session = _make_session()
        svc = CaseImportService(session)
        with patch("apps.oa_filing.services.case_import_service.CaseImportSession") as MockSession:
            svc._update_session()
            MockSession.objects.filter.return_value.update.assert_not_called()


# ===========================================================================
# import_single_case_data tests
# ===========================================================================


class TestImportSingleCaseData:
    def test_no_oa_data(self) -> None:
        svc = _make_service()
        result = svc._import_single_case_data("c1", None)
        assert result.status == "error"
        assert "未找到" in result.message

    def test_success_created(self) -> None:
        svc = _make_service()
        oa_data = MagicMock()
        oa_data.conflicts = []
        with patch.object(svc, "_check_conflicts", return_value=[]), \
             patch.object(svc, "_create_or_update_case", return_value=10):
            result = svc._import_single_case_data("c1", oa_data, should_exist=False)
            assert result.status == "created"
            assert result.contract_id == 10

    def test_success_updated(self) -> None:
        svc = _make_service()
        oa_data = MagicMock()
        oa_data.conflicts = []
        with patch.object(svc, "_check_conflicts", return_value=[]), \
             patch.object(svc, "_create_or_update_case", return_value=10):
            result = svc._import_single_case_data("c1", oa_data, should_exist=True)
            assert result.status == "updated"

    def test_create_fails(self) -> None:
        svc = _make_service()
        oa_data = MagicMock()
        oa_data.conflicts = []
        with patch.object(svc, "_check_conflicts", return_value=[]), \
             patch.object(svc, "_create_or_update_case", return_value=None):
            result = svc._import_single_case_data("c1", oa_data)
            assert result.status == "error"

    def test_exception_returns_error(self) -> None:
        svc = _make_service()
        oa_data = MagicMock()
        oa_data.conflicts = []
        with patch.object(svc, "_check_conflicts", side_effect=RuntimeError("boom")):
            result = svc._import_single_case_data("c1", oa_data)
            assert result.status == "error"
            assert "boom" in result.message

    def test_with_conflict_warnings(self) -> None:
        svc = _make_service()
        oa_data = MagicMock()
        oa_data.conflicts = [MagicMock(name="张三")]
        with patch.object(svc, "_check_conflicts", return_value=["利益冲突: 张三"]), \
             patch.object(svc, "_create_or_update_case", return_value=10):
            result = svc._import_single_case_data("c1", oa_data)
            assert result.conflict_warnings == ["利益冲突: 张三"]


# ===========================================================================
# get_or_create_client tests
# ===========================================================================


class TestGetOrCreateClient:
    _LAZY_CLIENT = "apps.client.models.Client"

    def test_existing_client_updates_phone(self) -> None:
        svc = _make_service()
        customer = MagicMock()
        customer.name = "张三"
        customer.phone = "12000000000"
        customer.address = ""
        customer.id_number = ""
        customer.customer_type = "natural"

        with patch(self._LAZY_CLIENT) as MockClient:
            existing = MagicMock()
            existing.phone = ""
            existing.address = ""
            existing.id_number = ""
            MockClient.objects.filter.return_value.first.return_value = existing
            result = svc._get_or_create_client(customer)
            assert result is existing
            assert existing.phone == "12000000000"
            existing.save.assert_called()

    def test_new_client(self) -> None:
        svc = _make_service()
        customer = MagicMock()
        customer.name = "李四"
        customer.phone = "139"
        customer.address = "addr"
        customer.id_number = "id"
        customer.legal_representative = "rep"
        customer.customer_type = "legal"

        with patch(self._LAZY_CLIENT) as MockClient:
            MockClient.objects.filter.return_value.first.return_value = None
            new_client = MagicMock()
            MockClient.objects.create.return_value = new_client
            result = svc._get_or_create_client(customer)
            assert result is new_client
            MockClient.objects.create.assert_called_once()

    def test_exception_returns_none(self) -> None:
        svc = _make_service()
        customer = MagicMock()
        customer.name = "err"

        with patch(self._LAZY_CLIENT) as MockClient:
            MockClient.objects.filter.side_effect = RuntimeError("db error")
            result = svc._get_or_create_client(customer)
            assert result is None


# ===========================================================================
# assign_lawyer tests
# ===========================================================================


class TestAssignLawyer:
    _LAZY_LAWYER = "apps.organization.models.Lawyer"
    _LAZY_CA = "apps.contracts.models.ContractAssignment"

    def test_empty_name_noop(self) -> None:
        svc = _make_service()
        contract = MagicMock()
        svc._assign_lawyer(contract, "")

    def test_found_lawyer(self) -> None:
        svc = _make_service()
        contract = MagicMock()
        with patch(self._LAZY_LAWYER) as MockLawyer, \
             patch(self._LAZY_CA) as MockAssign:
            lawyer = MagicMock()
            MockLawyer.objects.filter.return_value.first.return_value = lawyer
            MockAssign.objects.get_or_create.return_value = (MagicMock(), False)
            svc._assign_lawyer(contract, "张律师", is_primary=True)
            MockAssign.objects.get_or_create.assert_called_once()

    def test_lawyer_not_found(self) -> None:
        svc = _make_service()
        contract = MagicMock()
        with patch(self._LAZY_LAWYER) as MockLawyer:
            MockLawyer.objects.filter.return_value.first.return_value = None
            svc._assign_lawyer(contract, "Unknown")


# ===========================================================================
# preview_cases tests
# ===========================================================================


class TestPreviewCases:
    def test_matched(self) -> None:
        svc = _make_service()
        with patch("apps.oa_filing.services.case_import_service.Contract") as MockContract:
            MockContract.objects.filter.return_value.prefetch_related.return_value.exists.return_value = True
            mock_contract = MagicMock()
            mock_contract.id = 42
            mock_contract.contract_parties.select_related.return_value.all.return_value = []
            MockContract.objects.filter.return_value.prefetch_related.return_value.first.return_value = mock_contract
            results = svc.preview_cases(["c1"])
            assert len(results) == 1
            assert results[0].status == "matched"
            assert results[0].existing_contract_id == 42

    def test_unmatched(self) -> None:
        svc = _make_service()
        with patch("apps.oa_filing.services.case_import_service.Contract") as MockContract:
            MockContract.objects.filter.return_value.prefetch_related.return_value.exists.return_value = False
            results = svc.preview_cases(["c1"])
            assert len(results) == 1
            assert results[0].status == "unmatched"

    def test_exception_returns_error(self) -> None:
        svc = _make_service()
        with patch("apps.oa_filing.services.case_import_service.Contract") as MockContract:
            MockContract.objects.filter.return_value.prefetch_related.return_value.exists.side_effect = RuntimeError("db error")
            results = svc.preview_cases(["c1"])
            assert results[0].status == "error"

    def test_multiple_cases(self) -> None:
        svc = _make_service()
        with patch("apps.oa_filing.services.case_import_service.Contract") as MockContract:
            MockContract.objects.filter.return_value.prefetch_related.return_value.exists.return_value = False
            results = svc.preview_cases(["c1", "c2", "c3"])
            assert len(results) == 3


# ===========================================================================
# parse_excel tests
# ===========================================================================


class TestParseExcel:
    def test_parse(self) -> None:
        svc = _make_service()
        with patch("pandas.read_excel") as mock_read:
            mock_series = MagicMock()
            mock_series.tolist.return_value = ["c1", "c2"]
            mock_col = MagicMock()
            mock_col.dropna.return_value = mock_series
            mock_df = MagicMock()
            mock_df.__getitem__ = MagicMock(return_value=mock_col)
            mock_read.return_value = mock_df
            result = svc.parse_excel("/tmp/test.xlsx")
            assert result == ["c1", "c2"]
