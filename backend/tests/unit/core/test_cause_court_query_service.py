import pytest

from apps.core.models import CauseOfAction, Court
from apps.core.services.cause_court_query_service import CauseCourtQueryService


@pytest.mark.django_db
def test_cause_ancestor_chain_codes_and_names():
    root = CauseOfAction.objects.create(code="A", name="根", case_type="civil", level=1, is_active=True, is_deprecated=False)
    child = CauseOfAction.objects.create(
        code="A1",
        name="子",
        case_type="civil",
        level=2,
        parent=root,
        is_active=True,
        is_deprecated=False,
    )

    service = CauseCourtQueryService()
    assert service.get_cause_ancestor_codes_internal(child.id) == ["A1", "A"]
    assert service.get_cause_ancestor_names_internal(child.id) == ["子", "根"]


@pytest.mark.django_db
def test_get_cause_id_by_name_and_search_courts():
    CauseOfAction.objects.create(code="X", name="合同纠纷", case_type="civil", level=1, is_active=True, is_deprecated=False)
    Court.objects.create(code="C1", name="广州中院", is_active=True)

    service = CauseCourtQueryService()
    assert service.get_cause_id_by_name_internal("合同纠纷") is not None
    assert service.has_active_courts_internal() is True
    courts = service.search_courts_internal("广州", limit=10)
    assert courts and courts[0]["name"] == "广州中院"

