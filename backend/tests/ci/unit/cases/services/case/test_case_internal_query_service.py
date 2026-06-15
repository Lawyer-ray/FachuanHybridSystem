"""Tests for cases.services.case.case_internal_query_service.

Covers: __init__, orchestrator property, get_case_internal, get_cases_by_contract_internal,
get_cases_by_ids_internal, validate_case_active_internal,
get_case_current_stage_internal, check_case_access_internal,
get_primary_lawyer_names_by_case_ids_internal,
get_primary_case_numbers_by_case_ids_internal,
search_cases_by_party_internal, search_cases_for_binding_internal,
get_case_numbers_by_case_internal, get_case_party_names_internal,
search_cases_by_case_number_internal, list_cases_internal, search_cases_internal.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestCaseInternalQueryServiceInit:
    def test_default_init(self):
        from apps.cases.services.case.case_internal_query_service import CaseInternalQueryService
        svc = CaseInternalQueryService()
        assert svc._orchestrator is None

    def test_injected_orchestrator(self):
        from apps.cases.services.case.case_internal_query_service import CaseInternalQueryService
        orch = MagicMock()
        svc = CaseInternalQueryService(orchestrator=orch)
        assert svc.orchestrator is orch

    def test_orchestrator_lazy(self):
        from apps.cases.services.case.case_internal_query_service import CaseInternalQueryService
        svc = CaseInternalQueryService()
        with patch("apps.cases.services.case.case_internal_query_service.CaseQueryOrchestrator") as MockOrch:
            orch = svc.orchestrator
            assert orch is MockOrch.return_value
            assert svc._orchestrator is orch


class TestGetCaseInternal:
    def test_found(self):
        from apps.cases.services.case.case_internal_query_service import CaseInternalQueryService
        orch = MagicMock()
        orch.get_case.return_value = SimpleNamespace(id=1)
        svc = CaseInternalQueryService(orchestrator=orch)
        result = svc.get_case_internal(1)
        assert result.id == 1

    def test_not_found_returns_none(self):
        from apps.cases.services.case.case_internal_query_service import CaseInternalQueryService
        from apps.core.exceptions import NotFoundError
        orch = MagicMock()
        orch.get_case.side_effect = NotFoundError(message="not found")
        svc = CaseInternalQueryService(orchestrator=orch)
        result = svc.get_case_internal(1)
        assert result is None

    def test_other_exception_propagates(self):
        from apps.cases.services.case.case_internal_query_service import CaseInternalQueryService
        orch = MagicMock()
        orch.get_case.side_effect = RuntimeError("db error")
        svc = CaseInternalQueryService(orchestrator=orch)
        with pytest.raises(RuntimeError):
            svc.get_case_internal(1)


class TestDelegatedMethods:
    def _make_svc(self):
        from apps.cases.services.case.case_internal_query_service import CaseInternalQueryService
        orch = MagicMock()
        return CaseInternalQueryService(orchestrator=orch), orch

    def test_get_cases_by_contract(self):
        svc, orch = self._make_svc()
        orch.get_cases_by_contract.return_value = ["c1"]
        result = svc.get_cases_by_contract_internal(1)
        orch.get_cases_by_contract.assert_called_once_with(1)
        assert result == ["c1"]

    def test_get_cases_by_ids(self):
        svc, orch = self._make_svc()
        orch.get_cases_by_ids.return_value = ["c1"]
        result = svc.get_cases_by_ids_internal([1])
        orch.get_cases_by_ids.assert_called_once_with([1])
        assert result == ["c1"]

    def test_validate_case_active(self):
        svc, orch = self._make_svc()
        orch.validate_case_active.return_value = True
        assert svc.validate_case_active_internal(1) is True

    def test_get_case_current_stage(self):
        svc, orch = self._make_svc()
        orch.get_case_current_stage.return_value = "一审"
        assert svc.get_case_current_stage_internal(1) == "一审"

    def test_check_case_access(self):
        svc, orch = self._make_svc()
        orch.check_case_access.return_value = True
        assert svc.check_case_access_internal(1, 100) is True

    def test_get_primary_lawyer_names(self):
        svc, orch = self._make_svc()
        orch.get_primary_lawyer_names_by_case_ids.return_value = {1: "张律师"}
        result = svc.get_primary_lawyer_names_by_case_ids_internal([1])
        assert result == {1: "张律师"}

    def test_get_primary_case_numbers(self):
        svc, orch = self._make_svc()
        orch.get_primary_case_numbers_by_case_ids.return_value = {1: "2024京01民初1号"}
        result = svc.get_primary_case_numbers_by_case_ids_internal([1])
        assert result == {1: "2024京01民初1号"}

    def test_search_cases_by_party(self):
        svc, orch = self._make_svc()
        orch.search_cases_by_party.return_value = ["c1"]
        result = svc.search_cases_by_party_internal(["张三"])
        orch.search_cases_by_party.assert_called_once_with(["张三"], status=None)
        assert result == ["c1"]

    def test_get_case_numbers(self):
        svc, orch = self._make_svc()
        orch.get_case_numbers_by_case.return_value = ["2024京01民初1号"]
        result = svc.get_case_numbers_by_case_internal(1)
        assert result == ["2024京01民初1号"]

    def test_get_case_party_names(self):
        svc, orch = self._make_svc()
        orch.get_case_party_names.return_value = ["张三", "李四"]
        result = svc.get_case_party_names_internal(1)
        assert result == ["张三", "李四"]

    def test_search_cases_by_case_number(self):
        svc, orch = self._make_svc()
        orch.search_cases_by_case_number.return_value = ["c1"]
        result = svc.search_cases_by_case_number_internal("2024京01民初1号")
        assert result == ["c1"]

    def test_list_cases(self):
        svc, orch = self._make_svc()
        orch.list_cases.return_value = ["c1"]
        result = svc.list_cases_internal(status="active", limit=10)
        orch.list_cases.assert_called_once_with(status="active", limit=10, order_by="-start_date")
        assert result == ["c1"]

    def test_search_cases(self):
        svc, orch = self._make_svc()
        orch.search_cases.return_value = ["c1"]
        result = svc.search_cases_internal("query")
        orch.search_cases.assert_called_once_with(query="query", status=None, limit=30)
        assert result == ["c1"]


class TestSearchCasesForBindingInternal:
    def test_empty_search(self):
        from apps.cases.services.case.case_internal_query_service import CaseInternalQueryService
        svc = CaseInternalQueryService()
        with patch("apps.cases.services.case.case_internal_query_service.Case") as MockCase:
            case = SimpleNamespace(
                id=1,
                name="Test Case",
                case_numbers=[SimpleNamespace(number="2024京01民初1号")],
                parties=[SimpleNamespace(client=SimpleNamespace(name="张三"))],
                start_date=SimpleNamespace(isoformat=lambda: "2024-01-01"),
            )
            MockCase.objects.prefetch_related.return_value.order_by.return_value = [case]
            result = svc.search_cases_for_binding_internal("")
            assert len(result) == 1
            assert result[0]["name"] == "Test Case"

    def test_with_search_term(self):
        from apps.cases.services.case.case_internal_query_service import CaseInternalQueryService
        svc = CaseInternalQueryService()
        with patch("apps.cases.services.case.case_internal_query_service.Case") as MockCase, \
             patch("apps.cases.services.case.case_internal_query_service.CaseNumber") as MockCN, \
             patch("apps.cases.services.case.case_internal_query_service.CaseParty") as MockCP:
            case = SimpleNamespace(
                id=1,
                name="Test Case",
                case_numbers=[],
                parties=[SimpleNamespace(client=SimpleNamespace(name="张三"))],
                start_date=None,
            )
            MockCase.objects.filter.return_value.prefetch_related.return_value.distinct.return_value.order_by.return_value = [case]
            result = svc.search_cases_for_binding_internal("张三")
            assert len(result) == 1

    def test_limit_capped(self):
        from apps.cases.services.case.case_internal_query_service import CaseInternalQueryService
        svc = CaseInternalQueryService()
        with patch("apps.cases.services.case.case_internal_query_service.Case") as MockCase:
            MockCase.objects.prefetch_related.return_value.order_by.return_value = []
            result = svc.search_cases_for_binding_internal("", limit=100)
            assert len(result) == 0
