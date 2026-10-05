"""EvidenceMutationService 链式清单与删除清理补充测试。

覆盖 validate_list_type_creation 的前置依赖三分支、
auto_link_previous_list 的自动挂链、delete_evidence_item 的
文件清理分支（既有测试只覆盖无文件路径）。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.evidence.models import EvidenceItem, EvidenceList, ListType
from apps.evidence.services.mutation.evidence_mutation_service import EvidenceMutationService
from apps.testing.factories import CaseFactory


@pytest.fixture
def case(db: None):
    return CaseFactory()


@pytest.fixture
def svc() -> EvidenceMutationService:
    return EvidenceMutationService()


@pytest.mark.django_db
class TestValidateListTypeCreation:
    def test_first_list_has_no_requirement(self, svc, case) -> None:
        ok, error, previous = svc.validate_list_type_creation(case_id=case.id, list_type=ListType.LIST_1)
        assert ok is True
        assert error is None
        assert previous is None

    def test_next_list_requires_previous_missing(self, svc, case) -> None:
        ok, error, previous = svc.validate_list_type_creation(case_id=case.id, list_type=ListType.LIST_2)
        assert ok is False
        assert previous is None
        assert "证据清单一" in (error or "")
        assert "证据清单二" in (error or "")

    def test_next_list_with_previous_satisfied(self, svc, case) -> None:
        list_1 = EvidenceList.objects.create(case=case, title="一", list_type=ListType.LIST_1, order=1)
        ok, error, previous = svc.validate_list_type_creation(case_id=case.id, list_type=ListType.LIST_2)
        assert ok is True
        assert error is None
        assert previous is not None and previous.pk == list_1.pk


@pytest.mark.django_db
class TestAutoLinkPreviousList:
    def test_no_requirement_returns_none(self, svc, case) -> None:
        list_1 = EvidenceList.objects.create(case=case, title="一", list_type=ListType.LIST_1, order=1)
        assert svc.auto_link_previous_list(evidence_list=list_1) is None

    def test_previous_missing_returns_none(self, svc, case) -> None:
        list_2 = EvidenceList.objects.create(case=case, title="二", list_type=ListType.LIST_2, order=2)
        assert svc.auto_link_previous_list(evidence_list=list_2) is None
        list_2.refresh_from_db()
        assert list_2.previous_list_id is None

    def test_links_to_existing_previous(self, svc, case) -> None:
        list_1 = EvidenceList.objects.create(case=case, title="一", list_type=ListType.LIST_1, order=1)
        list_2 = EvidenceList.objects.create(case=case, title="二", list_type=ListType.LIST_2, order=2)
        linked = svc.auto_link_previous_list(evidence_list=list_2)

        assert linked is not None and linked.pk == list_1.pk
        list_2.refresh_from_db()
        assert list_2.previous_list_id == list_1.pk

    def test_already_linked_not_rewritten(self, svc, case) -> None:
        list_1 = EvidenceList.objects.create(case=case, title="一", list_type=ListType.LIST_1, order=1)
        list_2 = EvidenceList.objects.create(
            case=case, title="二", list_type=ListType.LIST_2, order=2, previous_list=list_1
        )
        with patch.object(EvidenceList, "save", wraps=EvidenceList.save) as mock_save:
            linked = svc.auto_link_previous_list(evidence_list=list_2)

        assert linked is not None and linked.pk == list_1.pk
        # 已挂链指向同一前清单时不重复 save
        mock_save.assert_not_called()


@pytest.mark.django_db
class TestDeleteEvidenceItemWithFile:
    def test_file_deleted_and_items_reordered(self, svc, case, settings, tmp_path) -> None:
        from django.core.files.uploadedfile import SimpleUploadedFile

        settings.MEDIA_ROOT = tmp_path
        evidence_list = EvidenceList.objects.create(case=case, title="清理清单", list_type=ListType.LIST_1, order=1)
        first = EvidenceItem.objects.create(
            evidence_list=evidence_list,
            order=1,
            name="证据一",
            purpose="证明目的",
            file=SimpleUploadedFile("a.pdf", b"%PDF-1.4 evidence"),
            file_name="a.pdf",
        )
        second = EvidenceItem.objects.create(evidence_list=evidence_list, order=2, name="证据二", purpose="证明目的")
        stored = Path(first.file.path)
        assert stored.exists()

        assert svc.delete_evidence_item(item=first) is True

        assert not EvidenceItem.objects.filter(pk=first.pk).exists()
        assert not stored.exists(), "删除明细时应清理其存储文件"
        # 剩余明细重排为 1 起
        second.refresh_from_db()
        assert second.order == 1

    def test_delete_without_file_skips_storage_cleanup(self, svc, case) -> None:
        evidence_list = EvidenceList.objects.create(case=case, title="无文件清单", list_type=ListType.LIST_1, order=1)
        item = EvidenceItem.objects.create(evidence_list=evidence_list, order=1, name="无文件", purpose="目的")

        assert svc.delete_evidence_item(item=item) is True
        assert not EvidenceItem.objects.filter(pk=item.pk).exists()

    def test_reorder_after_delete_compacts_gaps(self, svc, case) -> None:
        evidence_list = EvidenceList.objects.create(case=case, title="重排清单", list_type=ListType.LIST_1, order=1)
        i1 = EvidenceItem.objects.create(evidence_list=evidence_list, order=1, name="甲", purpose="p")
        i2 = EvidenceItem.objects.create(evidence_list=evidence_list, order=2, name="乙", purpose="p")
        i3 = EvidenceItem.objects.create(evidence_list=evidence_list, order=3, name="丙", purpose="p")

        svc.delete_evidence_item(item=i2)

        i1.refresh_from_db()
        i3.refresh_from_db()
        assert (i1.order, i3.order) == (1, 2)
