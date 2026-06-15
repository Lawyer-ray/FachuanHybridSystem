"""Tests for case_service_adapter — coverage for uncovered branches."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.cases.services.case.case_service_adapter import CaseServiceAdapter


class TestCaseServiceAdapterInit:
    def test_missing_contract_service_raises(self) -> None:
        with pytest.raises(RuntimeError, match="contract_service"):
            CaseServiceAdapter(contract_service=None, client_service=MagicMock())

    def test_missing_client_service_raises(self) -> None:
        with pytest.raises(RuntimeError, match="client_service"):
            CaseServiceAdapter(contract_service=MagicMock(), client_service=None)

    def test_valid_init(self) -> None:
        adapter = CaseServiceAdapter(contract_service=MagicMock(), client_service=MagicMock())
        assert adapter is not None


class TestCaseServiceAdapterQueryMethods:
    @pytest.fixture()
    def adapter(self) -> CaseServiceAdapter:
        return CaseServiceAdapter(contract_service=MagicMock(), client_service=MagicMock())

    def test_get_case(self, adapter: CaseServiceAdapter) -> None:
        adapter._internal_query = MagicMock()
        adapter._internal_query.get_case_internal.return_value = SimpleNamespace(id=1)
        result = adapter.get_case(1)
        assert result.id == 1

    def test_get_cases_by_contract(self, adapter: CaseServiceAdapter) -> None:
        adapter._internal_query = MagicMock()
        adapter.get_cases_by_contract(1)
        adapter._internal_query.get_cases_by_contract_internal.assert_called_once_with(contract_id=1)

    def test_count_cases_by_contract(self, adapter: CaseServiceAdapter) -> None:
        adapter._command = MagicMock()
        adapter._command.count_cases_by_contract.return_value = 5
        assert adapter.count_cases_by_contract(1) == 5

    def test_get_primary_lawyer_names(self, adapter: CaseServiceAdapter) -> None:
        adapter._internal_query = MagicMock()
        adapter.get_primary_lawyer_names_by_case_ids_internal([1, 2])
        adapter._internal_query.get_primary_lawyer_names_by_case_ids_internal.assert_called_once()

    def test_search_cases_for_binding_internal(self, adapter: CaseServiceAdapter) -> None:
        adapter._internal_query = MagicMock()
        adapter._internal_query.search_cases_for_binding_internal.return_value = [{"id": 1}]
        result = adapter.search_cases_for_binding_internal("test")
        assert isinstance(result, list)

    def test_search_cases_for_binding_internal_type_error(self, adapter: CaseServiceAdapter) -> None:
        adapter._internal_query = MagicMock()
        adapter._internal_query.search_cases_for_binding_internal.return_value = "not a list"
        with pytest.raises(TypeError, match="search_cases_for_binding_internal"):
            adapter.search_cases_for_binding_internal("test")

    def test_get_primary_case_numbers(self, adapter: CaseServiceAdapter) -> None:
        adapter._internal_query = MagicMock()
        adapter.get_primary_case_numbers_by_case_ids_internal([1])
        adapter._internal_query.get_primary_case_numbers_by_case_ids_internal.assert_called_once()

    def test_check_case_access(self, adapter: CaseServiceAdapter) -> None:
        adapter._internal_query = MagicMock()
        adapter.check_case_access(1, 2)
        adapter._internal_query.check_case_access_internal.assert_called_once_with(case_id=1, user_id=2)

    def test_get_cases_by_ids(self, adapter: CaseServiceAdapter) -> None:
        adapter._internal_query = MagicMock()
        adapter.get_cases_by_ids([1, 2])
        adapter._internal_query.get_cases_by_ids_internal.assert_called_once_with(case_ids=[1, 2])

    def test_validate_case_active(self, adapter: CaseServiceAdapter) -> None:
        adapter._internal_query = MagicMock()
        adapter.validate_case_active(1)
        adapter._internal_query.validate_case_active_internal.assert_called_once_with(case_id=1)

    def test_get_case_current_stage(self, adapter: CaseServiceAdapter) -> None:
        adapter._internal_query = MagicMock()
        adapter.get_case_current_stage(1)
        adapter._internal_query.get_case_current_stage_internal.assert_called_once_with(case_id=1)

    def test_get_user_extra_case_access(self, adapter: CaseServiceAdapter) -> None:
        adapter._internal_query = MagicMock()
        adapter.get_user_extra_case_access(1)
        adapter._internal_query.get_user_extra_case_access_internal.assert_called_once_with(user_id=1)

    def test_search_cases_by_party(self, adapter: CaseServiceAdapter) -> None:
        adapter._internal_query = MagicMock()
        adapter.search_cases_by_party_internal(["A"], status="active")
        adapter._internal_query.search_cases_by_party_internal.assert_called_once_with(party_names=["A"], status="active")

    def test_search_cases_by_case_number(self, adapter: CaseServiceAdapter) -> None:
        adapter._internal_query = MagicMock()
        adapter.search_cases_by_case_number_internal("2024-CA-123")
        adapter._internal_query.search_cases_by_case_number_internal.assert_called_once_with(case_number="2024-CA-123")

    def test_list_cases_internal(self, adapter: CaseServiceAdapter) -> None:
        adapter._internal_query = MagicMock()
        adapter.list_cases_internal(status="active", limit=10)
        adapter._internal_query.list_cases_internal.assert_called_once_with(status="active", limit=10, order_by="-start_date")

    def test_search_cases_internal(self, adapter: CaseServiceAdapter) -> None:
        adapter._internal_query = MagicMock()
        adapter.search_cases_internal("query", status="active", limit=5)
        adapter._internal_query.search_cases_internal.assert_called_once_with(query="query", status="active", limit=5)

    def test_get_case_by_id_internal(self, adapter: CaseServiceAdapter) -> None:
        adapter._internal_query = MagicMock()
        adapter.get_case_by_id_internal(1)
        adapter._internal_query.get_case_internal.assert_called_with(case_id=1)


class TestCaseServiceAdapterDetailMethods:
    @pytest.fixture()
    def adapter(self) -> CaseServiceAdapter:
        return CaseServiceAdapter(contract_service=MagicMock(), client_service=MagicMock())

    def test_get_case_model_internal(self, adapter: CaseServiceAdapter) -> None:
        adapter._details_query = MagicMock()
        adapter.get_case_model_internal(1)
        adapter._details_query.get_case_model_internal.assert_called_once_with(case_id=1)

    def test_get_case_with_details_internal(self, adapter: CaseServiceAdapter) -> None:
        adapter._details_query = MagicMock()
        adapter.get_case_with_details_internal(1)
        adapter._details_query.get_case_with_details_internal.assert_called_once_with(case_id=1)

    def test_get_case_log_model_internal(self, adapter: CaseServiceAdapter) -> None:
        adapter._log_internal = MagicMock()
        adapter.get_case_log_model_internal(1)
        adapter._log_internal.get_case_log_model_internal.assert_called_once_with(case_log_id=1)

    def test_get_case_parties_by_legal_status(self, adapter: CaseServiceAdapter) -> None:
        adapter._party_query = MagicMock()
        adapter.get_case_parties_by_legal_status_internal(1, "plaintiff")
        adapter._party_query.get_case_parties_by_legal_status_internal.assert_called_once_with(case_id=1, legal_status="plaintiff")

    def test_get_case_parties_internal(self, adapter: CaseServiceAdapter) -> None:
        adapter._party_query = MagicMock()
        adapter.get_case_parties_internal(1, "defendant")
        adapter._party_query.get_case_parties_internal.assert_called_once_with(case_id=1, legal_status="defendant")

    def test_get_case_template_binding_internal(self, adapter: CaseServiceAdapter) -> None:
        adapter._template_binding_query = MagicMock()
        adapter.get_case_template_binding_internal(1)
        adapter._template_binding_query.get_case_template_binding_internal.assert_called_once_with(case_id=1)

    def test_get_case_template_bindings_by_name_internal(self, adapter: CaseServiceAdapter) -> None:
        adapter._template_binding_query = MagicMock()
        adapter.get_case_template_bindings_by_name_internal(1, "template_name")
        adapter._template_binding_query.get_case_template_bindings_by_name_internal.assert_called_once_with(case_id=1, template_name="template_name")


class TestCaseServiceAdapterMutations:
    @pytest.fixture()
    def adapter(self) -> CaseServiceAdapter:
        return CaseServiceAdapter(contract_service=MagicMock(), client_service=MagicMock())

    def test_create_case_no_user_sets_perm(self, adapter: CaseServiceAdapter) -> None:
        adapter._command = MagicMock()
        mock_case = SimpleNamespace(id=1)
        adapter._command.create_case.return_value = mock_case
        adapter._internal_query = MagicMock()
        adapter._internal_query.get_case_internal.return_value = SimpleNamespace(id=1)
        result = adapter.create_case(data={"name": "test"})
        assert result.id == 1

    def test_unbind_cases(self, adapter: CaseServiceAdapter) -> None:
        adapter._command = MagicMock()
        adapter.unbind_cases_from_contract_internal(1)
        adapter._command.unbind_cases_from_contract_internal.assert_called_once_with(1)

    def test_close_cases(self, adapter: CaseServiceAdapter) -> None:
        adapter._command = MagicMock()
        adapter._command.close_cases_by_contract_internal.return_value = 3
        assert adapter.close_cases_by_contract_internal(1) == 3

    def test_create_case_log_internal(self, adapter: CaseServiceAdapter) -> None:
        adapter._log_internal = MagicMock()
        adapter.create_case_log_internal(1, "content", user_id=10)
        adapter._log_internal.create_case_log_internal.assert_called_once_with(case_id=1, content="content", user_id=10)

    def test_add_case_log_attachment_internal(self, adapter: CaseServiceAdapter) -> None:
        adapter._log_internal = MagicMock()
        adapter.add_case_log_attachment_internal(1, "/path", "name.pdf")
        adapter._log_internal.add_case_log_attachment_internal.assert_called_once_with(case_log_id=1, file_path="/path", file_name="name.pdf")

    def test_add_case_number_internal(self, adapter: CaseServiceAdapter) -> None:
        adapter._number_internal = MagicMock()
        adapter.add_case_number_internal(1, "2024-CA-123", user_id=10)
        adapter._number_internal.add_case_number_internal.assert_called_once_with(case_id=1, case_number="2024-CA-123", user_id=10)

    def test_update_case_log_reminder_internal(self, adapter: CaseServiceAdapter) -> None:
        adapter._log_internal = MagicMock()
        adapter.update_case_log_reminder_internal(1, "2024-01-01", "reminder")
        adapter._log_internal.update_case_log_reminder_internal.assert_called_once_with(case_log_id=1, reminder_time="2024-01-01", reminder_type="reminder")

    def test_create_case_party(self, adapter: CaseServiceAdapter) -> None:
        with patch("apps.cases.services.party.case_party_mutation_service.CasePartyMutationService") as mock_svc:
            adapter.create_case_party(1, 2, legal_status="plaintiff")
            mock_svc.assert_called_once()

    def test_get_case_numbers_by_case_internal(self, adapter: CaseServiceAdapter) -> None:
        adapter._internal_query = MagicMock()
        adapter.get_case_numbers_by_case_internal(1)
        adapter._internal_query.get_case_numbers_by_case_internal.assert_called_once_with(case_id=1)

    def test_get_case_party_names_internal(self, adapter: CaseServiceAdapter) -> None:
        adapter._internal_query = MagicMock()
        adapter.get_case_party_names_internal(1)
        adapter._internal_query.get_case_party_names_internal.assert_called_once_with(case_id=1)
