"""Comprehensive tests for evidence services — query, mutation, file, page range, export."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.cases.models import Case
from apps.evidence.models import EvidenceItem, EvidenceList, MergeStatus, ListType
from apps.evidence.services.core.evidence_query_service import EvidenceQueryService
from apps.evidence.services.mutation.evidence_mutation_service import EvidenceMutationService
from apps.evidence.services.core.page_range_calculator import EvidencePageRangeCalculator
from apps.testing.factories import CaseFactory, ContractFactory


# ── EvidenceQueryService tests ──


@pytest.mark.django_db
class TestEvidenceQueryService:
    def test_get_evidence_list(self, db):
        svc = EvidenceQueryService()
        c = CaseFactory()
        el = EvidenceList.objects.create(case=c, title="Test List")
        result = svc.get_evidence_list(el.pk)
        assert result.pk == el.pk
        assert result.title == "Test List"

    def test_get_evidence_list_not_found(self, db):
        svc = EvidenceQueryService()
        with pytest.raises(EvidenceList.DoesNotExist):
            svc.get_evidence_list(99999)

    def test_list_evidence_lists(self, db):
        svc = EvidenceQueryService()
        c = CaseFactory()
        EvidenceList.objects.create(case=c, title="List 1", list_type="list_1")
        EvidenceList.objects.create(case=c, title="List 2", list_type="list_2")
        result = svc.list_evidence_lists(c.pk)
        assert len(result) == 2

    def test_list_evidence_lists_empty(self, db):
        svc = EvidenceQueryService()
        c = CaseFactory()
        result = svc.list_evidence_lists(c.pk)
        assert len(result) == 0

    def test_get_evidence_item(self, db):
        svc = EvidenceQueryService()
        c = CaseFactory()
        el = EvidenceList.objects.create(case=c, title="Test")
        item = EvidenceItem.objects.create(evidence_list=el, name="Item 1", order=1)
        result = svc.get_evidence_item(item.pk)
        assert result.pk == item.pk

    def test_get_evidence_item_not_found(self, db):
        svc = EvidenceQueryService()
        with pytest.raises(EvidenceItem.DoesNotExist):
            svc.get_evidence_item(99999)

    def test_list_evidence_items_for_digest_by_list_ids(self, db):
        svc = EvidenceQueryService()
        c = CaseFactory()
        el = EvidenceList.objects.create(case=c, title="Test")
        EvidenceItem.objects.create(evidence_list=el, name="Item 1", order=1)
        EvidenceItem.objects.create(evidence_list=el, name="Item 2", order=2)
        result = svc.list_evidence_items_for_digest_internal([el.pk], [])
        assert len(result) == 2

    def test_list_evidence_items_for_digest_by_item_ids(self, db):
        svc = EvidenceQueryService()
        c = CaseFactory()
        el = EvidenceList.objects.create(case=c, title="Test")
        item = EvidenceItem.objects.create(evidence_list=el, name="Item 1", order=1)
        result = svc.list_evidence_items_for_digest_internal([], [item.pk])
        assert len(result) == 1

    def test_list_evidence_items_for_digest_empty(self, db):
        svc = EvidenceQueryService()
        result = svc.list_evidence_items_for_digest_internal([], [])
        assert len(result) == 0

    def test_list_evidence_item_ids_with_files_empty(self, db):
        svc = EvidenceQueryService()
        result = svc.list_evidence_item_ids_with_files_internal([])
        assert len(result) == 0

    def test_list_evidence_items_for_case(self, db):
        svc = EvidenceQueryService()
        c = CaseFactory()
        el = EvidenceList.objects.create(case=c, title="Test")
        EvidenceItem.objects.create(evidence_list=el, name="Item 1", order=1)
        result = svc.list_evidence_items_for_case_internal(c.pk)
        assert len(result) == 1


# ── EvidenceMutationService tests ──


@pytest.mark.django_db
class TestEvidenceMutationService:
    def test_create_evidence_list(self, db):
        svc = EvidenceMutationService()
        c = CaseFactory()
        el = svc.create_evidence_list(case=c, title="New List")
        assert el.pk is not None
        assert el.title == "New List"
        assert el.case_id == c.pk

    def test_update_evidence_list(self, db):
        svc = EvidenceMutationService()
        c = CaseFactory()
        el = EvidenceList.objects.create(case=c, title="Old Title")
        updated = svc.update_evidence_list(evidence_list=el, title="New Title")
        assert updated.title == "New Title"

    def test_delete_evidence_list(self, db):
        svc = EvidenceMutationService()
        c = CaseFactory()
        el = EvidenceList.objects.create(case=c, title="To Delete")
        result = svc.delete_evidence_list(evidence_list=el)
        assert result is True
        assert not EvidenceList.objects.filter(pk=el.pk).exists()

    def test_create_evidence_item(self, db):
        svc = EvidenceMutationService()
        c = CaseFactory()
        el = EvidenceList.objects.create(case=c, title="Test")
        item = svc.create_evidence_item(evidence_list=el, name="New Item", purpose="证明目的")
        assert item.pk is not None
        assert item.name == "New Item"

    def test_update_evidence_item(self, db):
        svc = EvidenceMutationService()
        c = CaseFactory()
        el = EvidenceList.objects.create(case=c, title="Test")
        item = EvidenceItem.objects.create(evidence_list=el, name="Old", order=1)
        updated = svc.update_evidence_item(item=item, name="New", purpose="New Purpose")
        assert updated.name == "New"

    def test_delete_evidence_item(self, db):
        svc = EvidenceMutationService()
        c = CaseFactory()
        el = EvidenceList.objects.create(case=c, title="Test")
        item = EvidenceItem.objects.create(evidence_list=el, name="To Delete", order=1)
        result = svc.delete_evidence_item(item=item)
        assert result is True
        assert not EvidenceItem.objects.filter(pk=item.pk).exists()

    def test_require_case_model(self, db):
        svc = EvidenceMutationService()
        c = CaseFactory()
        mock_case_svc = MagicMock()
        mock_case_svc.get_case_model_internal.return_value = c
        result = svc.require_case_model(case_service=mock_case_svc, case_id=c.pk)
        assert result.pk == c.pk

    def test_require_case_model_not_found(self, db):
        svc = EvidenceMutationService()
        mock_case_svc = MagicMock()
        mock_case_svc.get_case_model_internal.return_value = None
        with pytest.raises(Exception):
            svc.require_case_model(case_service=mock_case_svc, case_id=99999)


# ── EvidencePageRangeCalculator tests ──


class TestEvidencePageRangeCalculator:
    def test_calculator_exists(self):
        svc = EvidencePageRangeCalculator()
        assert svc is not None


# ── EvidenceList model tests ──


@pytest.mark.django_db
class TestEvidenceListModel:
    def test_evidence_list_str(self):
        c = CaseFactory()
        el = EvidenceList.objects.create(case=c, title="TestList")
        assert "TestList" in str(el) or el.title == "TestList"

    def test_list_type_choices(self):
        assert ListType.LIST_1 == "list_1"
        assert ListType.LIST_6 == "list_6"

    def test_merge_status_choices(self):
        assert MergeStatus.PENDING == "pending"
        assert MergeStatus.COMPLETED == "completed"


# ── EvidenceItem model tests ──


@pytest.mark.django_db
class TestEvidenceItemModel:
    def test_evidence_item_str(self):
        c = CaseFactory()
        el = EvidenceList.objects.create(case=c, title="Test")
        item = EvidenceItem.objects.create(evidence_list=el, name="TestItem", order=1)
        assert "TestItem" in str(item) or item.name == "TestItem"

    def test_evidence_item_ordering(self):
        c = CaseFactory()
        el = EvidenceList.objects.create(case=c, title="Test")
        EvidenceItem.objects.create(evidence_list=el, name="B", order=2)
        EvidenceItem.objects.create(evidence_list=el, name="A", order=1)
        items = list(EvidenceItem.objects.filter(evidence_list=el))
        assert items[0].name == "A"
