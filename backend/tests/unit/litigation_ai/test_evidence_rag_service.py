import pytest

from apps.documents.models import EvidenceItem, EvidenceList
from apps.documents.models.evidence import ListType
from apps.litigation_ai.models import EvidenceChunk
from apps.litigation_ai.services.evidence_rag_service import EvidenceRAGService
from tests.factories.case_factories import CaseFactory


@pytest.mark.django_db
def test_evidence_rag_service_retrieves_chunks(monkeypatch):
    monkeypatch.setattr("apps.core.llm.config.LLMConfig.get_api_key", lambda: "")

    case = CaseFactory()
    evidence_list = EvidenceList.objects.create(case=case, list_type=ListType.LIST_1)  # type: ignore[misc]
    item = EvidenceItem.objects.create(
        evidence_list=evidence_list,
        order=1,
        name="合同",
        purpose="证明合同关系",
        page_start=1,
        page_end=2,
    )

    EvidenceChunk.objects.create(
        evidence_item=item,
        page_start=1,
        page_end=1,
        text="双方于2023年签订买卖合同，约定价款与交付。",
        extraction_method="text",
        embedding=[],
    )

    chunks = EvidenceRAGService().retrieve("合同 价款 交付", [item.id], top_k=3)
    assert len(chunks) == 1
    assert chunks[0].evidence_item_id == item.id
