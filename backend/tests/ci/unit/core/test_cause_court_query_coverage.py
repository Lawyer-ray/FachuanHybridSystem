"""Coverage tests for core.services.cause_court_query_service."""

from unittest.mock import MagicMock

import pytest

from apps.core.services.cause_court_query_service import CauseCourtQueryService


class TestCauseCourtQueryService:
    def _make(self):
        repo = MagicMock()
        return CauseCourtQueryService(repository=repo), repo

    def test_has_active_causes(self):
        svc, repo = self._make()
        repo.has_active_causes.return_value = True
        assert svc.has_active_causes_internal() is True

    def test_has_active_courts(self):
        svc, repo = self._make()
        repo.has_active_courts.return_value = False
        assert svc.has_active_courts_internal() is False

    def test_get_cause_id_by_name_found(self):
        svc, repo = self._make()
        mock_cause = MagicMock()
        mock_cause.id = 42
        repo.get_cause_by_name.return_value = mock_cause
        assert svc.get_cause_id_by_name_internal("test") == 42

    def test_get_cause_id_by_name_not_found(self):
        svc, repo = self._make()
        repo.get_cause_by_name.return_value = None
        assert svc.get_cause_id_by_name_internal("missing") is None

    def test_get_cause_id_by_name_empty(self):
        svc, repo = self._make()
        assert svc.get_cause_id_by_name_internal("") is None

    def test_get_cause_ancestor_codes(self):
        svc, repo = self._make()
        parent = MagicMock()
        parent.code = "P1"
        parent.parent = None
        cause = MagicMock()
        cause.code = "C1"
        cause.parent = parent
        repo.get_cause_by_id.return_value = cause
        result = svc.get_cause_ancestor_codes_internal(1)
        assert "C1" in result
        assert "P1" in result

    def test_get_cause_ancestor_codes_not_found(self):
        svc, repo = self._make()
        repo.get_cause_by_id.return_value = None
        assert svc.get_cause_ancestor_codes_internal(999) == []

    def test_get_cause_by_id_found(self):
        svc, repo = self._make()
        mock_cause = MagicMock()
        mock_cause.id = 1
        mock_cause.name = "test"
        mock_cause.code = "T1"
        mock_cause.case_type = "civil"
        repo.get_active_cause_by_id.return_value = mock_cause
        result = svc.get_cause_by_id_internal(1)
        assert result["name"] == "test"

    def test_get_cause_by_id_not_found(self):
        svc, repo = self._make()
        repo.get_active_cause_by_id.return_value = None
        assert svc.get_cause_by_id_internal(999) is None

    def test_get_cause_ancestor_names(self):
        svc, repo = self._make()
        parent = MagicMock()
        parent.name = "Parent"
        parent.parent = None
        cause = MagicMock()
        cause.name = "Child"
        cause.parent = parent
        repo.get_cause_by_id.return_value = cause
        result = svc.get_cause_ancestor_names_internal(1)
        assert "Child" in result
        assert "Parent" in result

    def test_search_causes_empty_query(self):
        svc, repo = self._make()
        result = svc.search_causes_internal("", None, 10)
        assert result == []

    def test_search_causes_bankruptcy(self):
        svc, repo = self._make()
        result = svc.search_causes_internal("test", "bankruptcy", 10)
        assert result == []

    def test_search_courts_empty(self):
        svc, repo = self._make()
        result = svc.search_courts_internal("", 10)
        assert result == []

    def test_case_type_db_map(self):
        assert "civil" in CauseCourtQueryService.CASE_TYPE_DB_MAP
        assert "execution" in CauseCourtQueryService.CASE_TYPE_DB_MAP
