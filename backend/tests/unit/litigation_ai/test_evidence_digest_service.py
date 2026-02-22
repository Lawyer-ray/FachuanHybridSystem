import pytest

from apps.documents.models import EvidenceItem, EvidenceList
from apps.documents.models.evidence import ListType
from apps.litigation_ai.services.evidence_digest_service import EvidenceDigestService
from tests.factories.case_factories import CaseFactory


@pytest.mark.django_db
def test_evidence_digest_service_formats_items():
    case = CaseFactory()
    evidence_list = EvidenceList.objects.create(case=case, list_type=ListType.LIST_1)  # type: ignore[misc]
    EvidenceItem.objects.create(
        evidence_list=evidence_list,
        order=1,
        name="借款合同",
        purpose="证明借款关系成立",
        page_start=1,
        page_end=2,
    )

    text = EvidenceDigestService().build_evidence_text([evidence_list.id], [])
    assert "1. 借款合同" in text
    assert "[证据#" in text
    assert "页码：1-2" in text
