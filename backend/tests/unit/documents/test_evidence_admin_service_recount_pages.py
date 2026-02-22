import pytest

from apps.documents.models import EvidenceItem, EvidenceList, ListType
from apps.documents.services.evidence_admin_service import EvidenceAdminService
from tests.factories.case_factories import CaseFactory


@pytest.mark.django_db
def test_recount_pages_does_not_count_items_without_file():
    case = CaseFactory()

    list_1 = EvidenceList.objects.create(case=case, list_type=ListType.LIST_1, total_pages=19)  # type: ignore[misc]
    list_2 = EvidenceList.objects.create(case=case, list_type=ListType.LIST_2, previous_list=list_1, total_pages=1)  # type: ignore[misc]

    item = EvidenceItem.objects.create(
        evidence_list=list_2,
        order=1,
        name="无文件证据",
        purpose="测试",
        file=None,
        page_count=1,
        page_start=20,
        page_end=20,
    )

    result = EvidenceAdminService().recount_pages(list_2.id)

    list_2.refresh_from_db()
    item.refresh_from_db()

    assert result["total_pages"] == 0
    assert result["updated"] == 1
    assert list_2.total_pages == 0
    assert list_2.page_range_display == ""
    assert item.page_count == 0
    assert item.page_start is None
    assert item.page_end is None
