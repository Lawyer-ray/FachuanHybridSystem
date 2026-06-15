"""Unit tests for CaseQueryOrchestrator and sub-orchestrators."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.cases.services.case.case_query_orchestrator import (
    CaseAccessQueryOrchestrator,
    CaseNumberQueryOrchestrator,
    CasePartyQueryOrchestrator,
    CaseQueryOrchestrator,
)


# ──────────── CaseNumberQueryOrchestrator ────────────


class TestCaseNumberQueryOrchestrator:
    def test_init_defaults(self):
        orch = CaseNumberQueryOrchestrator()
        assert orch.case_number_repo is not None
        assert orch.case_search_repo is not None
        assert orch.case_number_aggregation_service is not None

    def test_get_primary_case_number(self):
        mock_repo = MagicMock()
        mock_repo.get_primary_case_number.return_value = "（2024）京01民初1号"
        orch = CaseNumberQueryOrchestrator(case_number_repo=mock_repo)
        result = orch.get_primary_case_number(case_id=1)
        assert result == "（2024）京01民初1号"
        mock_repo.get_primary_case_number.assert_called_once_with(1)

    def test_get_primary_case_numbers_by_case_ids(self):
        mock_agg = MagicMock()
        mock_agg.get_primary_case_numbers_by_case_ids.return_value = {1: "CN1", 2: "CN2"}
        orch = CaseNumberQueryOrchestrator(case_number_aggregation_service=mock_agg)
        result = orch.get_primary_case_numbers_by_case_ids([1, 2])
        assert result == {1: "CN1", 2: "CN2"}

    def test_get_case_numbers_by_case(self):
        mock_repo = MagicMock()
        mock_repo.get_case_numbers_by_case.return_value = ["CN1", "CN2"]
        orch = CaseNumberQueryOrchestrator(case_number_repo=mock_repo)
        result = orch.get_case_numbers_by_case(case_id=5)
        assert result == ["CN1", "CN2"]

    def test_search_cases_by_case_number(self):
        mock_search = MagicMock()
        mock_search.search_cases_by_case_number.return_value = []
        orch = CaseNumberQueryOrchestrator(case_search_repo=mock_search)
        result = orch.search_cases_by_case_number("2024-123")
        assert result == []


# ──────────── CasePartyQueryOrchestrator ────────────


class TestCasePartyQueryOrchestrator:
    def test_init_defaults(self):
        orch = CasePartyQueryOrchestrator()
        assert orch.case_party_repo is not None
        assert orch.case_party_aggregation_service is not None

    def test_search_cases_by_party(self):
        mock_repo = MagicMock()
        mock_repo.search_cases_by_party.return_value = []
        orch = CasePartyQueryOrchestrator(case_party_repo=mock_repo)
        result = orch.search_cases_by_party(["张三"])
        assert result == []
        mock_repo.search_cases_by_party.assert_called_once_with(["张三"], status=None)

    def test_get_case_party_names(self):
        mock_agg = MagicMock()
        mock_agg.get_case_party_names.return_value = ["原告A", "被告B"]
        orch = CasePartyQueryOrchestrator(case_party_aggregation_service=mock_agg)
        result = orch.get_case_party_names(case_id=1)
        assert result == ["原告A", "被告B"]


# ──────────── CaseAccessQueryOrchestrator ────────────


class TestCaseAccessQueryOrchestrator:
    def test_init_defaults(self):
        orch = CaseAccessQueryOrchestrator()
        assert orch.case_access_repo is not None
        assert orch.case_assignment_repo is not None
        assert orch.case_assignment_aggregation_service is not None

    def test_check_case_access(self):
        mock_repo = MagicMock()
        mock_repo.check_case_access.return_value = True
        orch = CaseAccessQueryOrchestrator(case_assignment_repo=mock_repo)
        assert orch.check_case_access(case_id=1, user_id=2) is True

    def test_get_user_extra_case_access(self):
        mock_repo = MagicMock()
        mock_repo.get_user_extra_case_access.return_value = [10, 20]
        orch = CaseAccessQueryOrchestrator(case_access_repo=mock_repo)
        result = orch.get_user_extra_case_access(user_id=1)
        assert result == [10, 20]

    def test_get_primary_lawyer_names(self):
        mock_agg = MagicMock()
        mock_agg.get_primary_lawyer_names_by_case_ids.return_value = {1: "律师A"}
        orch = CaseAccessQueryOrchestrator(case_assignment_aggregation_service=mock_agg)
        result = orch.get_primary_lawyer_names_by_case_ids([1])
        assert result == {1: "律师A"}


# ──────────── CaseQueryOrchestrator ────────────


class TestCaseQueryOrchestrator:
    def test_init_defaults(self):
        orch = CaseQueryOrchestrator()
        assert orch.case_repo is not None
        assert orch.case_search_repo is not None
        assert orch.case_number_orchestrator is not None
        assert orch.case_party_orchestrator is not None
        assert orch.case_access_orchestrator is not None
        assert orch.assembler is not None

    def test_get_case_found(self):
        mock_repo = MagicMock()
        mock_case = MagicMock()
        mock_repo.get_case_by_id.return_value = mock_case
        mock_number_orch = MagicMock()
        mock_number_orch.get_primary_case_number.return_value = "CN-1"
        mock_assembler = MagicMock()
        mock_dto = MagicMock()
        mock_assembler.to_dto.return_value = mock_dto

        orch = CaseQueryOrchestrator(
            case_repo=mock_repo,
            case_number_orchestrator=mock_number_orch,
            assembler=mock_assembler,
        )
        result = orch.get_case(case_id=1)
        assert result is mock_dto
        mock_assembler.to_dto.assert_called_once_with(mock_case, "CN-1")

    def test_get_case_not_found(self):
        mock_repo = MagicMock()
        mock_repo.get_case_by_id.return_value = None
        orch = CaseQueryOrchestrator(case_repo=mock_repo)
        result = orch.get_case(case_id=999)
        assert result is None

    def test_validate_case_active(self):
        mock_repo = MagicMock()
        mock_repo.validate_case_active.return_value = True
        orch = CaseQueryOrchestrator(case_repo=mock_repo)
        assert orch.validate_case_active(1) is True

    def test_get_case_current_stage(self):
        mock_repo = MagicMock()
        mock_repo.get_case_current_stage.return_value = "first_trial"
        orch = CaseQueryOrchestrator(case_repo=mock_repo)
        assert orch.get_case_current_stage(1) == "first_trial"

    def test_check_case_access_delegates(self):
        mock_access_orch = MagicMock()
        mock_access_orch.check_case_access.return_value = True
        orch = CaseQueryOrchestrator(case_access_orchestrator=mock_access_orch)
        assert orch.check_case_access(1, 2) is True

    def test_get_user_extra_case_access(self):
        mock_access_orch = MagicMock()
        mock_access_orch.get_user_extra_case_access.return_value = [5]
        orch = CaseQueryOrchestrator(case_access_orchestrator=mock_access_orch)
        assert orch.get_user_extra_case_access(1) == [5]

    def test_get_primary_lawyer_names(self):
        mock_access_orch = MagicMock()
        mock_access_orch.get_primary_lawyer_names_by_case_ids.return_value = {}
        orch = CaseQueryOrchestrator(case_access_orchestrator=mock_access_orch)
        assert orch.get_primary_lawyer_names_by_case_ids([1]) == {}

    def test_get_primary_case_numbers(self):
        mock_number_orch = MagicMock()
        mock_number_orch.get_primary_case_numbers_by_case_ids.return_value = {}
        orch = CaseQueryOrchestrator(case_number_orchestrator=mock_number_orch)
        assert orch.get_primary_case_numbers_by_case_ids([1]) == {}

    def test_search_cases(self):
        mock_search = MagicMock()
        mock_search.search_cases.return_value = []
        mock_assembler = MagicMock()
        mock_assembler.to_dtos.return_value = []
        orch = CaseQueryOrchestrator(
            case_search_repo=mock_search, assembler=mock_assembler
        )
        result = orch.search_cases("张三", status="active")
        assert result == []
        mock_search.search_cases.assert_called_once_with(query="张三", status="active", limit=30)

    def test_search_cases_by_party(self):
        mock_party_orch = MagicMock()
        mock_party_orch.search_cases_by_party.return_value = []
        mock_assembler = MagicMock()
        mock_assembler.to_dtos.return_value = []
        orch = CaseQueryOrchestrator(
            case_party_orchestrator=mock_party_orch, assembler=mock_assembler
        )
        result = orch.search_cases_by_party(["原告"])
        assert result == []

    def test_list_cases(self):
        mock_repo = MagicMock()
        mock_repo.list_cases.return_value = []
        mock_assembler = MagicMock()
        mock_assembler.to_dtos.return_value = []
        orch = CaseQueryOrchestrator(case_repo=mock_repo, assembler=mock_assembler)
        result = orch.list_cases(status="active", limit=10)
        assert result == []

    def test_get_cases_by_ids(self):
        mock_repo = MagicMock()
        mock_repo.get_cases_by_ids.return_value = []
        mock_assembler = MagicMock()
        mock_assembler.to_dtos.return_value = []
        orch = CaseQueryOrchestrator(case_repo=mock_repo, assembler=mock_assembler)
        result = orch.get_cases_by_ids([1, 2])
        assert result == []

    def test_get_case_numbers_by_case(self):
        mock_number_orch = MagicMock()
        mock_number_orch.get_case_numbers_by_case.return_value = ["CN1"]
        orch = CaseQueryOrchestrator(case_number_orchestrator=mock_number_orch)
        assert orch.get_case_numbers_by_case(1) == ["CN1"]

    def test_get_case_party_names(self):
        mock_party_orch = MagicMock()
        mock_party_orch.get_case_party_names.return_value = ["原告A"]
        orch = CaseQueryOrchestrator(case_party_orchestrator=mock_party_orch)
        assert orch.get_case_party_names(1) == ["原告A"]

    def test_search_cases_by_case_number(self):
        mock_number_orch = MagicMock()
        mock_number_orch.search_cases_by_case_number.return_value = []
        mock_assembler = MagicMock()
        mock_assembler.to_dtos.return_value = []
        orch = CaseQueryOrchestrator(
            case_number_orchestrator=mock_number_orch, assembler=mock_assembler
        )
        result = orch.search_cases_by_case_number("2024-123")
        assert result == []
