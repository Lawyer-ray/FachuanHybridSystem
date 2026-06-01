"""Integration contract tests for legal research capability endpoints."""

from __future__ import annotations

import pytest

from apps.legal_research.schemas.legal_research_schemas import (
    AgentSearchQueryTraceOut,
    AgentSearchRequestV1,
    AgentSearchResponseV1,
)


@pytest.mark.django_db
def test_capability_search_endpoint_returns_contract_and_passes_idempotency_key(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    class _StubCapabilityService:
        def search(self, *, payload: AgentSearchRequestV1, user, idempotency_key: str = "") -> AgentSearchResponseV1:
            captured["idempotency_key"] = idempotency_key
            return AgentSearchResponseV1(
                request_id="req-capability-001",
                status="ok",
                degradation_flags=[],
                query_trace=AgentSearchQueryTraceOut(
                    primary_queries=["买卖合同 逾期交货 价差损失"],
                    budget_used_ms=1500,
                    candidates_scanned=32,
                ),
                results=[],
            )

    monkeypatch.setattr(
        "apps.legal_research.api.legal_research_api._get_capability_service",
        lambda: _StubCapabilityService(),
    )

    response = authenticated_client.post(
        "/api/v1/legal-research/capability/search",
        data={
            "version": "v1",
            "credential_id": 1,
            "intent": "similar_case",
            "facts": "被告逾期交货并引发价差损失争议。",
            "legal_issue": "违约责任范围",
            "cause_type": "买卖合同纠纷",
            "target_count": 3,
            "search_mode": "expanded",
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="idem-capability-001",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["request_id"] == "req-capability-001"
    assert data["status"] == "ok"
    assert "query_trace" in data
    assert captured["idempotency_key"] == "idem-capability-001"


@pytest.mark.django_db
def test_capability_search_mcp_endpoint_returns_wrapper_contract(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StubWrapper:
        def search(self, *, payload: AgentSearchRequestV1, user, idempotency_key: str = "") -> dict[str, object]:
            return {
                "version": "v1",
                "request_id": "req-mcp-001",
                "status": "partial",
                "degradation_flags": ["partial_result"],
                "query_trace": {
                    "primary_queries": ["买卖合同 违约 赔偿"],
                    "expansion_queries": [],
                    "feedback_queries": [],
                    "query_type_metrics": {},
                    "budget_used_ms": 1800,
                    "candidates_scanned": 40,
                },
                "results": [
                    {
                        "doc_id": "DOC-001",
                        "title": "买卖合同纠纷案例",
                        "court": "广州市中级人民法院",
                        "judgment_date": "2024-08-01",
                        "score": 0.91,
                        "decision": "accept",
                        "subscores": {
                            "facts_match": 0.9,
                            "legal_relation_match": 0.88,
                            "dispute_match": 0.87,
                            "damage_match": 0.81,
                        },
                        "conflicts": [],
                        "snippets": {
                            "claims": "诉讼请求：判令赔偿损失。",
                            "findings": "本院查明：被告迟延交货。",
                            "reasoning": "本院认为：应承担违约责任。",
                            "holdings": "判决如下：支持部分请求。",
                        },
                        "why_selected": "关键事实与争点匹配",
                        "source_url": "https://example.com/doc-001",
                        "agent_summary": "买卖合同纠纷案例 | 广州市中级人民法院 | score=0.910 | 关键事实与争点匹配",
                    }
                ],
            }

    monkeypatch.setattr(
        "apps.legal_research.api.legal_research_api._get_capability_mcp_wrapper",
        lambda: _StubWrapper(),
    )

    response = authenticated_client.post(
        "/api/v1/legal-research/capability/search/mcp",
        data={
            "version": "v1",
            "credential_id": 1,
            "intent": "same_court_precedent",
            "facts": "围绕逾期交货责任展开争议。",
            "legal_issue": "违约责任",
            "cause_type": "买卖合同纠纷",
            "target_count": 2,
            "search_mode": "expanded",
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["request_id"] == "req-mcp-001"
    assert data["status"] == "partial"
    assert data["results"][0]["doc_id"] == "DOC-001"
    assert "agent_summary" in data["results"][0]
