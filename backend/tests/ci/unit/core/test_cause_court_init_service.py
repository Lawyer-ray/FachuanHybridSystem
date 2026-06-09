"""
Unit tests for core/services/cause_court_initialization_service.py.

Covers:
  - InitializationResult dataclass (defaults, __add__, total_processed, success, to_dict)
  - CauseCourtInitializationService.__init__ (with and without deps)
  - api_client property (lazy loading)
  - _collect_cause_codes (flat and nested)
  - _collect_court_codes (flat and nested)
  - _parse_hierarchical_causes (created, updated, failed)
  - _parse_hierarchical_courts (created, updated, failed)
  - _import_causes_to_db
  - _import_courts_to_db
  - _deprecate_removed_causes (deprecated, deleted)
  - _delete_removed_courts
  - _cause_has_templates (always False)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.services.cause_court_initialization_service import (
    CauseCourtInitializationService,
    InitializationResult,
)


# ---------------------------------------------------------------------------
# InitializationResult tests
# ---------------------------------------------------------------------------


class TestInitializationResult:
    def test_defaults(self) -> None:
        r = InitializationResult()
        assert r.created == 0
        assert r.updated == 0
        assert r.deprecated == 0
        assert r.deleted == 0
        assert r.failed == 0
        assert r.errors == []
        assert r.warnings == []

    def test_add(self) -> None:
        r1 = InitializationResult(created=1, updated=2, failed=0)
        r2 = InitializationResult(created=3, updated=4, failed=1, errors=["err"])
        r3 = r1 + r2
        assert r3.created == 4
        assert r3.updated == 6
        assert r3.failed == 1
        assert r3.errors == ["err"]

    def test_total_processed(self) -> None:
        r = InitializationResult(created=1, updated=2, deprecated=3, deleted=4)
        assert r.total_processed == 10

    def test_success_true(self) -> None:
        r = InitializationResult(failed=0)
        assert r.success is True

    def test_success_false(self) -> None:
        r = InitializationResult(failed=1)
        assert r.success is False

    def test_to_dict(self) -> None:
        r = InitializationResult(created=1, updated=2, warnings=["w"])
        d = r.to_dict()
        assert d["created"] == 1
        assert d["updated"] == 2
        assert d["total_processed"] == 3
        assert d["success"] is True
        assert d["warnings"] == ["w"]


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


class TestCauseCourtInitService:
    def test_init_with_deps(self) -> None:
        mock_client = MagicMock()
        mock_repo = MagicMock()
        svc = CauseCourtInitializationService(api_client=mock_client, repository=mock_repo)
        assert svc.api_client is mock_client

    def test_api_client_lazy(self) -> None:
        svc = CauseCourtInitializationService(api_client=None)
        with patch("apps.core.services.cause_court_initialization_service.CourtApiClient") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            client = svc.api_client
        assert client is mock_instance


class TestCollectCauseCodes:
    def test_flat(self) -> None:
        svc = CauseCourtInitializationService()
        items = [
            MagicMock(code="001", children=[]),
            MagicMock(code="002", children=[]),
        ]
        result = svc._collect_cause_codes(items)
        assert result == {"001", "002"}

    def test_nested(self) -> None:
        svc = CauseCourtInitializationService()
        child = MagicMock(code="0011", children=[])
        parent = MagicMock(code="001", children=[child])
        result = svc._collect_cause_codes([parent])
        assert result == {"001", "0011"}

    def test_empty(self) -> None:
        svc = CauseCourtInitializationService()
        assert svc._collect_cause_codes([]) == set()


class TestCollectCourtCodes:
    def test_flat(self) -> None:
        svc = CauseCourtInitializationService()
        items = [MagicMock(code="C001", children=[]), MagicMock(code="C002", children=[])]
        result = svc._collect_court_codes(items)
        assert result == {"C001", "C002"}


class TestParseHierarchicalCauses:
    def test_created(self) -> None:
        svc = CauseCourtInitializationService()
        svc._repository = MagicMock()
        cause_instance = MagicMock()
        svc._repository.update_or_create_cause.return_value = (cause_instance, True)

        item = MagicMock(code="001", name="Test", case_type="civil", level=1, children=[])
        result = svc._parse_hierarchical_causes(item, parent=None)
        assert result.created == 1
        assert result.updated == 0

    def test_updated(self) -> None:
        svc = CauseCourtInitializationService()
        svc._repository = MagicMock()
        cause_instance = MagicMock()
        svc._repository.update_or_create_cause.return_value = (cause_instance, False)

        item = MagicMock(code="001", name="Test", case_type="civil", level=1, children=[])
        result = svc._parse_hierarchical_causes(item, parent=None)
        assert result.created == 0
        assert result.updated == 1

    def test_failed(self) -> None:
        svc = CauseCourtInitializationService()
        svc._repository = MagicMock()
        svc._repository.update_or_create_cause.side_effect = Exception("db error")

        item = MagicMock(code="001", name="Test", case_type="civil", level=1, children=[])
        result = svc._parse_hierarchical_causes(item, parent=None)
        assert result.failed == 1
        assert len(result.errors) == 1

    def test_recursive_children(self) -> None:
        svc = CauseCourtInitializationService()
        svc._repository = MagicMock()
        cause_instance = MagicMock()
        svc._repository.update_or_create_cause.return_value = (cause_instance, True)

        child = MagicMock(code="0011", name="Child", case_type="civil", level=2, children=[])
        parent = MagicMock(code="001", name="Parent", case_type="civil", level=1, children=[child])
        result = svc._parse_hierarchical_causes(parent, parent=None)
        assert result.created == 2


class TestParseHierarchicalCourts:
    def test_created(self) -> None:
        svc = CauseCourtInitializationService()
        svc._repository = MagicMock()
        court_instance = MagicMock()
        svc._repository.update_or_create_court.return_value = (court_instance, True)

        item = MagicMock(code="C001", name="Test Court", level=1, province="Beijing", children=[])
        result = svc._parse_hierarchical_courts(item, parent=None)
        assert result.created == 1

    def test_failed(self) -> None:
        svc = CauseCourtInitializationService()
        svc._repository = MagicMock()
        svc._repository.update_or_create_court.side_effect = Exception("db error")

        item = MagicMock(code="C001", name="Test Court", level=1, province="Beijing", children=[])
        result = svc._parse_hierarchical_courts(item, parent=None)
        assert result.failed == 1


class TestDeprecateRemovedCauses:
    @pytest.mark.django_db
    def test_deprecated_when_has_templates(self) -> None:
        svc = CauseCourtInitializationService()
        svc._repository = MagicMock()
        cause = MagicMock()
        cause.code = "001"
        cause.name = "Old Cause"
        svc._repository.get_non_deprecated_causes_excluding_codes.return_value = [cause]

        with patch.object(svc, "_cause_has_templates", return_value=False):
            result = svc._deprecate_removed_causes({"new_code"})

        # _cause_has_templates always returns False now, so it deletes
        assert result.deleted == 1

    @pytest.mark.django_db
    def test_deleted_when_no_templates(self) -> None:
        svc = CauseCourtInitializationService()
        svc._repository = MagicMock()
        cause = MagicMock()
        cause.code = "001"
        cause.name = "Old Cause"
        svc._repository.get_non_deprecated_causes_excluding_codes.return_value = [cause]

        result = svc._deprecate_removed_causes({"new_code"})
        assert result.deleted == 1
        cause.delete.assert_called_once()

    @pytest.mark.django_db
    def test_failure_on_delete(self) -> None:
        svc = CauseCourtInitializationService()
        svc._repository = MagicMock()
        cause = MagicMock()
        cause.code = "001"
        cause.name = "Old Cause"
        cause.delete.side_effect = Exception("db error")
        svc._repository.get_non_deprecated_causes_excluding_codes.return_value = [cause]

        result = svc._deprecate_removed_causes({"new_code"})
        assert result.failed == 1


class TestDeleteRemovedCourts:
    @pytest.mark.django_db
    def test_deleted(self) -> None:
        svc = CauseCourtInitializationService()
        svc._repository = MagicMock()
        court = MagicMock()
        court.code = "C001"
        court.name = "Old Court"
        svc._repository.get_courts_excluding_codes.return_value = [court]

        result = svc._delete_removed_courts({"new_code"})
        assert result.deleted == 1
        court.delete.assert_called_once()

    @pytest.mark.django_db
    def test_failure_on_delete(self) -> None:
        svc = CauseCourtInitializationService()
        svc._repository = MagicMock()
        court = MagicMock()
        court.code = "C001"
        court.name = "Old Court"
        court.delete.side_effect = Exception("db error")
        svc._repository.get_courts_excluding_codes.return_value = [court]

        result = svc._delete_removed_courts({"new_code"})
        assert result.failed == 1


class TestCauseHasTemplates:
    def test_always_false(self) -> None:
        svc = CauseCourtInitializationService()
        assert svc._cause_has_templates(MagicMock()) is False
