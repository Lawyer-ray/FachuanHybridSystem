"""Tests for case_full_create_workflow — coverage for uncovered branches."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.cases.services.case.workflows.case_full_create_workflow import CaseFullCreateWorkflow
from apps.core.exceptions import ConflictError, ValidationException


class TestCaseFullCreateWorkflowInit:
    def test_repo_property_creates_default(self) -> None:
        with patch("apps.cases.services.case.workflows.case_full_create_workflow.CaseFullCreateRepo"):
            wf = CaseFullCreateWorkflow(case_service=MagicMock())
            assert wf.repo is not None

    def test_repo_property_returns_injected(self) -> None:
        mock_repo = MagicMock()
        wf = CaseFullCreateWorkflow(case_service=MagicMock(), repo=mock_repo)
        assert wf.repo is mock_repo


@pytest.mark.django_db(transaction=True)
class TestCaseFullCreateWorkflowRun:
    """Tests that use transaction=True to get past the @transaction.atomic on run()."""

    def test_logs_without_actor_raises(self) -> None:
        wf = CaseFullCreateWorkflow(case_service=MagicMock())
        data = {
            "case": {},
            "parties": [],
            "assignments": [],
            "logs": [{"content": "test"}],
            "supervising_authorities": [],
        }
        with pytest.raises(ValidationException, match="操作人不能为空"):
            wf.run(data=data, actor_id=None)

    def test_duplicate_party_client_ids_raises(self) -> None:
        wf = CaseFullCreateWorkflow(case_service=MagicMock())
        mock_repo = MagicMock()
        wf._repo = mock_repo
        data = {
            "case": {},
            "parties": [{"client_id": 1}, {"client_id": 1}],
            "assignments": [],
            "logs": [],
            "supervising_authorities": [],
        }
        with pytest.raises(ConflictError, match="当事人数据重复"):
            wf.run(data=data)

    def test_duplicate_lawyer_ids_raises(self) -> None:
        wf = CaseFullCreateWorkflow(case_service=MagicMock())
        mock_repo = MagicMock()
        wf._repo = mock_repo
        data = {
            "case": {},
            "parties": [{"client_id": 1}, {"client_id": 2}],
            "assignments": [{"lawyer_id": 1}, {"lawyer_id": 1}],
            "logs": [],
            "supervising_authorities": [],
        }
        with pytest.raises(ConflictError, match="指派数据重复"):
            wf.run(data=data)

    def test_successful_create_no_logs(self) -> None:
        case_service = MagicMock()
        mock_case = SimpleNamespace(id=1)
        case_service.create_case.return_value = mock_case
        mock_repo = MagicMock()
        mock_repo.bulk_create_case_parties.return_value = [SimpleNamespace(id=1)]
        mock_repo.bulk_create_case_assignments.return_value = [SimpleNamespace(id=1)]
        wf = CaseFullCreateWorkflow(case_service=case_service, repo=mock_repo)
        data = {"case": {"name": "test"}, "parties": [{"client_id": 1}], "assignments": [{"lawyer_id": 1}], "logs": [], "supervising_authorities": []}
        result = wf.run(data=data)
        assert result["case"] is mock_case
        mock_repo.bulk_create_case_logs.assert_not_called()

    def test_successful_create_with_logs(self) -> None:
        case_service = MagicMock()
        mock_case = SimpleNamespace(id=1)
        case_service.create_case.return_value = mock_case
        mock_repo = MagicMock()
        mock_repo.bulk_create_case_parties.return_value = []
        mock_repo.bulk_create_case_assignments.return_value = []
        mock_repo.bulk_create_case_logs.return_value = [SimpleNamespace(id=1)]
        mock_repo.bulk_create_supervising_authorities.return_value = []
        wf = CaseFullCreateWorkflow(case_service=case_service, repo=mock_repo)
        data = {"case": {}, "parties": [], "assignments": [], "logs": [{"content": "created"}], "supervising_authorities": []}
        result = wf.run(data=data, actor_id=10)
        mock_repo.bulk_create_case_logs.assert_called_once()

    def test_with_supervising_authorities(self) -> None:
        case_service = MagicMock()
        mock_case = SimpleNamespace(id=1)
        case_service.create_case.return_value = mock_case
        mock_repo = MagicMock()
        mock_repo.bulk_create_case_parties.return_value = []
        mock_repo.bulk_create_case_assignments.return_value = []
        mock_repo.bulk_create_supervising_authorities.return_value = [SimpleNamespace(id=1)]
        wf = CaseFullCreateWorkflow(case_service=case_service, repo=mock_repo)
        data = {"case": {}, "parties": [], "assignments": [], "logs": [], "supervising_authorities": [{"name": "court"}]}
        result = wf.run(data=data)
        mock_repo.bulk_create_supervising_authorities.assert_called_once()

    def test_empty_data(self) -> None:
        case_service = MagicMock()
        mock_case = SimpleNamespace(id=1)
        case_service.create_case.return_value = mock_case
        mock_repo = MagicMock()
        mock_repo.bulk_create_case_parties.return_value = []
        mock_repo.bulk_create_case_assignments.return_value = []
        wf = CaseFullCreateWorkflow(case_service=case_service, repo=mock_repo)
        result = wf.run(data={})
        assert result["case"] is mock_case
