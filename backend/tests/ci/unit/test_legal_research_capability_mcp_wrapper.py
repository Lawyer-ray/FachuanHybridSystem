from __future__ import annotations

from apps.legal_research.schemas.legal_research_schemas import (
    AgentSearchQueryTraceOut,
    AgentSearchRequestV1,
    AgentSearchResponseV1,
    AgentSearchSnippetsOut,
    AgentSearchSubscoresOut,
    RetrievalHitV1,
)
from apps.legal_research.services.capability_mcp_wrapper import LegalResearchCapabilityMcpWrapper


def test_capability_mcp_wrapper_returns_agent_friendly_contract() -> None:
    class _StubCapabilityService:
        def search(self, *, payload: AgentSearchRequestV1, user, idempotency_key: str = "") -> AgentSearchResponseV1:
            return AgentSearchResponseV1(
                request_id="req-001",
                status="ok",
                degradation_flags=[],
                query_trace=AgentSearchQueryTraceOut(
                    primary_queries=["买卖合同 逾期交货 赔偿"],
                    expansion_queries=["买卖合同 价差损失"],
                    feedback_queries=[],
                    budget_used_ms=1200,
                    candidates_scanned=42,
                ),
                results=[
                    RetrievalHitV1(
                        doc_id="DOC-001",
                        title="买卖合同纠纷案例",
                        court="广州市中级人民法院",
                        judgment_date="2024-08-01",
                        score=0.91,
                        decision="accept",
                        subscores=AgentSearchSubscoresOut(
                            facts_match=0.9,
                            legal_relation_match=0.88,
                            dispute_match=0.87,
                            damage_match=0.8,
                        ),
                        conflicts=["无显著冲突"],
                        snippets=AgentSearchSnippetsOut(
                            claims="诉讼请求：判令被告赔偿损失。",
                            findings="本院查明：被告逾期交货。",
                            reasoning="本院认为：被告应承担违约责任。",
                            holdings="判决如下：支持原告部分诉请。",
                        ),
                        why_selected="核心事实与争点高度一致",
                        source_url="https://example.com/doc-001",
                    )
                ],
            )

    wrapper = LegalResearchCapabilityMcpWrapper(capability_service=_StubCapabilityService())
    payload = AgentSearchRequestV1(
        credential_id=1,
        intent="similar_case",
        facts="被告逾期交货引发价差损失争议。",
        legal_issue="违约责任",
        cause_type="买卖合同纠纷",
    )

    result = wrapper.search(payload=payload, user=None, idempotency_key="idem-1")

    assert result["version"] == "v1"
    assert result["request_id"] == "req-001"
    assert result["status"] == "ok"
    assert len(result["results"]) == 1
    hit = result["results"][0]
    assert hit["doc_id"] == "DOC-001"
    assert "metadata" not in hit
    assert "agent_summary" in hit
    assert "score=0.910" in hit["agent_summary"]
