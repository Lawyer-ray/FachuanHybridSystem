"""automation.api.court_filing_helpers 补充覆盖测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock
from typing import Any

import pytest


# ── _resolve_court_name ───────────────────────────────────────────

class TestResolveCourtName:
    def _import_func(self):
        from apps.automation.api.court_filing_helpers import _resolve_court_name
        return _resolve_court_name

    def test_already_has_renmfy(self):
        func = self._import_func()
        result = func("广州市天河区人民法院")
        assert result == "广州市天河区人民法院"

    @pytest.mark.django_db
    def test_not_found_appends_suffix(self):
        func = self._import_func()
        result = func("不存在的法院")
        assert result == "不存在的法院人民法院"


# ── _normalize_filing_engine ──────────────────────────────────────

class TestNormalizeFilingEngine:
    def _import_func(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_engine
        return _normalize_filing_engine

    def test_valid_engine(self):
        func = self._import_func()
        with patch("apps.automation.api.court_filing_helpers._VALID_FILING_ENGINES", {"api", "web"}):
            result = func("api")
            assert result == "api"

    def test_invalid_engine_returns_default(self):
        func = self._import_func()
        with patch("apps.automation.api.court_filing_helpers._VALID_FILING_ENGINES", {"api", "web"}):
            with patch("apps.automation.api.court_filing_helpers._FILING_ENGINE_API", "api"):
                result = func("invalid")
                assert result == "api"

    def test_none_engine_returns_default(self):
        func = self._import_func()
        with patch("apps.automation.api.court_filing_helpers._VALID_FILING_ENGINES", {"api", "web"}):
            with patch("apps.automation.api.court_filing_helpers._FILING_ENGINE_API", "api"):
                result = func(None)
                assert result == "api"

    def test_empty_engine_returns_default(self):
        func = self._import_func()
        with patch("apps.automation.api.court_filing_helpers._VALID_FILING_ENGINES", {"api", "web"}):
            with patch("apps.automation.api.court_filing_helpers._FILING_ENGINE_API", "api"):
                result = func("")
                assert result == "api"


# ── _normalize_filing_type ────────────────────────────────────────

class TestNormalizeFilingType:
    def _import_func(self):
        from apps.automation.api.court_filing_helpers import _normalize_filing_type
        return _normalize_filing_type

    def test_valid_type(self):
        func = self._import_func()
        with patch("apps.automation.api.court_filing_helpers._VALID_FILING_TYPES", {"civil", "execution"}):
            result = func(requested_filing_type="civil", case=MagicMock(), parties=[])
            assert result == "civil"

    def test_case_insensitive(self):
        func = self._import_func()
        with patch("apps.automation.api.court_filing_helpers._VALID_FILING_TYPES", {"civil", "execution"}):
            result = func(requested_filing_type="Civil", case=MagicMock(), parties=[])
            assert result == "civil"

    def test_invalid_type_infers(self):
        func = self._import_func()
        with patch("apps.automation.api.court_filing_helpers._VALID_FILING_TYPES", {"civil", "execution"}):
            with patch("apps.automation.api.court_filing_helpers._infer_filing_type") as mock_infer:
                mock_infer.return_value = "civil"
                result = func(requested_filing_type="invalid", case=MagicMock(), parties=[])
                assert result == "civil"

    def test_none_type_infers(self):
        func = self._import_func()
        with patch("apps.automation.api.court_filing_helpers._VALID_FILING_TYPES", {"civil", "execution"}):
            with patch("apps.automation.api.court_filing_helpers._infer_filing_type") as mock_infer:
                mock_infer.return_value = "execution"
                result = func(requested_filing_type=None, case=MagicMock(), parties=[])
                assert result == "execution"


# ── _resolve_original_case_number ─────────────────────────────────

class TestResolveOriginalCaseNumber:
    def _import_func(self):
        from apps.automation.api.court_filing_helpers import _resolve_original_case_number
        return _resolve_original_case_number

    def test_no_case_numbers(self):
        func = self._import_func()
        case = MagicMock()
        case.case_numbers = None
        result = func(case)
        assert result == ""

    def test_active_number(self):
        func = self._import_func()
        case = MagicMock()
        case.case_numbers.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = "(2024)粤01民初123号"
        result = func(case)
        assert result == "(2024)粤01民初123号"

    def test_fallback_number(self):
        func = self._import_func()
        case = MagicMock()
        case.case_numbers.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        case.case_numbers.order_by.return_value.values_list.return_value.first.return_value = "(2024)粤01民初456号"
        result = func(case)
        assert result == "(2024)粤01民初456号"

    def test_no_numbers(self):
        func = self._import_func()
        case = MagicMock()
        case.case_numbers.filter.return_value.order_by.return_value.values_list.return_value.first.return_value = None
        case.case_numbers.order_by.return_value.values_list.return_value.first.return_value = None
        result = func(case)
        assert result == ""


# ── _infer_filing_type ────────────────────────────────────────────

class TestInferFilingType:
    def _import_func(self):
        from apps.automation.api.court_filing_helpers import _infer_filing_type
        return _infer_filing_type

    @pytest.mark.django_db
    def test_execution_hint_status(self):
        func = self._import_func()
        party = MagicMock()
        party.legal_status = "被执行人"
        with patch("apps.automation.api.court_filing_helpers._EXECUTION_HINT_STATUSES", {"被执行人"}):
            result = func(case=MagicMock(), parties=[party])
            assert result == "execution"

    @pytest.mark.django_db
    def test_execution_keyword_in_name(self):
        func = self._import_func()
        case = MagicMock()
        case.name = "张三申请执行案"
        case.cause_of_action = ""
        with patch("apps.automation.api.court_filing_helpers._EXECUTION_HINT_STATUSES", set()):
            with patch("apps.cases.models.CaseMaterial") as mock_cm:
                mock_cm.objects.filter.return_value.values_list.return_value = []
                result = func(case=case, parties=[])
                assert result == "execution"

    @pytest.mark.django_db
    def test_civil_default(self):
        func = self._import_func()
        case = MagicMock()
        case.name = "张三诉李四买卖合同纠纷"
        case.cause_of_action = "买卖合同纠纷"
        with patch("apps.automation.api.court_filing_helpers._EXECUTION_HINT_STATUSES", set()):
            with patch("apps.cases.models.CaseMaterial") as mock_cm:
                mock_cm.objects.filter.return_value.values_list.return_value = []
                result = func(case=case, parties=[])
                assert result == "civil"


# ── _build_party_payloads ─────────────────────────────────────────

class TestBuildPartyPayloads:
    def _import_func(self):
        from apps.automation.api.court_filing_helpers import _build_party_payloads
        return _build_party_payloads

    def test_basic_plaintiff(self):
        func = self._import_func()
        party = MagicMock()
        party.client.client_type = "natural"
        party.client.name = "张三"
        party.client.address = "北京市朝阳区"
        party.client.phone = "13800138000"
        party.client.id_number = "110101199001011234"
        party.legal_status = "plaintiff"

        with patch("apps.automation.api.court_filing_helpers._PLAINTIFF_SIDE_STATUSES", {"plaintiff"}):
            with patch("apps.automation.api.court_filing_helpers._DEFENDANT_SIDE_STATUSES", set()):
                with patch("apps.automation.api.court_filing_helpers._THIRD_SIDE_STATUSES", set()):
                    with patch("apps.core.utils.id_card_utils.IdCardUtils.extract_gender", return_value="男"):
                        plaintiffs, defendants, third_parties = func([party])
                        assert len(plaintiffs) == 1
                        assert plaintiffs[0]["name"] == "张三"

    def test_legal_entity(self):
        func = self._import_func()
        party = MagicMock()
        party.client.client_type = "legal"
        party.client.name = "某公司"
        party.client.address = "北京市海淀区"
        party.client.phone = "010-12345678"
        party.client.id_number = "91110000MA12345678"
        party.legal_status = "defendant"

        with patch("apps.automation.api.court_filing_helpers._PLAINTIFF_SIDE_STATUSES", set()):
            with patch("apps.automation.api.court_filing_helpers._DEFENDANT_SIDE_STATUSES", {"defendant"}):
                with patch("apps.automation.api.court_filing_helpers._THIRD_SIDE_STATUSES", set()):
                    plaintiffs, defendants, third_parties = func([party])
                    assert len(defendants) == 1
                    assert defendants[0]["name"] == "某公司"

    def test_third_party(self):
        func = self._import_func()
        party = MagicMock()
        party.client.client_type = "legal"
        party.client.name = "第三方"
        party.client.address = ""
        party.client.phone = ""
        party.client.id_number = ""
        party.legal_status = "third_party"

        with patch("apps.automation.api.court_filing_helpers._PLAINTIFF_SIDE_STATUSES", set()):
            with patch("apps.automation.api.court_filing_helpers._DEFENDANT_SIDE_STATUSES", set()):
                with patch("apps.automation.api.court_filing_helpers._THIRD_SIDE_STATUSES", {"third_party"}):
                    plaintiffs, defendants, third_parties = func([party])
                    assert len(third_parties) == 1


# ── _SESSION_UPDATE_EXECUTOR ──────────────────────────────────────

class TestExecutor:
    def test_executor_exists(self):
        from apps.automation.api.court_filing_helpers import _SESSION_UPDATE_EXECUTOR
        assert _SESSION_UPDATE_EXECUTOR is not None


# ── _get_organization_service ─────────────────────────────────────

class TestGetOrganizationService:
    def test_is_callable(self):
        from apps.automation.api.court_filing_helpers import _get_organization_service
        assert callable(_get_organization_service)
