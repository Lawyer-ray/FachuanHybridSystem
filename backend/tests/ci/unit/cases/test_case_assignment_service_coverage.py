"""Tests for case_assignment_service — coverage for uncovered branches."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.cases.services.party.case_assignment_service import CaseAssignmentService
from apps.core.exceptions import ConflictError, NotFoundError


class TestCaseAssignmentServiceInit:
    def test_init_no_deps(self) -> None:
        svc = CaseAssignmentService()
        assert svc._case_service is None
        assert svc._contract_assignment_query_service is None

    def test_init_with_deps(self) -> None:
        mock_cs = MagicMock()
        mock_caq = MagicMock()
        svc = CaseAssignmentService(case_service=mock_cs, contract_assignment_query_service=mock_caq)
        assert svc._case_service is mock_cs
        assert svc._contract_assignment_query_service is mock_caq

    def test_case_service_property_not_injected_raises(self) -> None:
        svc = CaseAssignmentService()
        with pytest.raises(RuntimeError, match="case_service 未注入"):
            _ = svc.case_service

    def test_contract_assignment_query_service_property_not_injected_raises(self) -> None:
        svc = CaseAssignmentService()
        with pytest.raises(RuntimeError, match="contract_assignment_query_service 未注入"):
            _ = svc.contract_assignment_query_service

    def test_case_service_property_injected(self) -> None:
        mock_cs = MagicMock()
        svc = CaseAssignmentService(case_service=mock_cs)
        assert svc.case_service is mock_cs

    def test_contract_assignment_query_service_property_injected(self) -> None:
        mock_caq = MagicMock()
        svc = CaseAssignmentService(contract_assignment_query_service=mock_caq)
        assert svc.contract_assignment_query_service is mock_caq


@pytest.mark.django_db()
class TestListAssignments:
    def test_list_no_filters(self) -> None:
        svc = CaseAssignmentService()
        mock_user = MagicMock()
        mock_user.is_superuser = True
        qs = svc.list_assignments(user=mock_user)
        assert qs is not None

    def test_list_with_case_id_filter(self) -> None:
        svc = CaseAssignmentService()
        mock_user = MagicMock()
        mock_user.is_superuser = True
        qs = svc.list_assignments(case_id=1, user=mock_user)
        assert qs is not None

    def test_list_with_lawyer_id_filter(self) -> None:
        svc = CaseAssignmentService()
        mock_user = MagicMock()
        mock_user.is_superuser = True
        qs = svc.list_assignments(lawyer_id=1, user=mock_user)
        assert qs is not None


@pytest.mark.django_db()
class TestGetAssignment:
    def test_not_found(self) -> None:
        svc = CaseAssignmentService()
        mock_user = MagicMock()
        mock_user.is_superuser = True
        with pytest.raises(NotFoundError, match="指派不存在"):
            svc.get_assignment(99999, user=mock_user)


@pytest.mark.django_db()
class TestDeleteAssignment:
    def test_not_found(self) -> None:
        svc = CaseAssignmentService()
        mock_user = MagicMock()
        mock_user.is_superuser = True
        with pytest.raises(NotFoundError, match="指派不存在"):
            svc.delete_assignment(99999, user=mock_user)
