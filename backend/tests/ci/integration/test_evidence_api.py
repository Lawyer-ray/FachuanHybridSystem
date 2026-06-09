"""Evidence API integration tests."""

from __future__ import annotations

import json

from unittest.mock import patch

import pytest

from apps.evidence.models import EvidenceList


# ===================================================================
# Evidence Reorder
# ===================================================================


@pytest.mark.django_db
def test_reorder_evidence_items_empty(authenticated_client):
    """Reorder with empty list should succeed."""
    from apps.contracts.models import Contract
    from apps.cases.models import Case

    contract = Contract.objects.create(name="证据测试合同", case_type="civil")
    case = Case.objects.create(name="证据测试案件", contract=contract)
    ev_list = EvidenceList.objects.create(title="测试证据清单", case=case)
    resp = authenticated_client.post(
        f"/api/v1/evidence/evidence-lists/{ev_list.id}/reorder",
        data=json.dumps({"item_ids": []}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True


# ===================================================================
# AI Suggest Purpose (mocked)
# ===================================================================


@pytest.mark.django_db
def test_ai_suggest_purpose(authenticated_client):
    with patch(
        "apps.evidence.services.ai.evidence_ai_service.EvidenceAIService.suggest_purpose",
        return_value=["证明借款事实", "证明利息约定"],
    ):
        resp = authenticated_client.post(
            "/api/v1/evidence/ai/suggest-purpose",
            data=json.dumps({
                "cause_of_action": "借款合同纠纷",
                "evidence_type": "书证",
                "evidence_name": "借条",
                "content_summary": "被告向原告借款10万元",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data
        assert len(data["suggestions"]) == 2


# ===================================================================
# AI Generate Cross Examination (mocked)
# ===================================================================


@pytest.mark.django_db
def test_ai_generate_cross_examination(authenticated_client):
    with patch(
        "apps.evidence.services.ai.evidence_ai_service.EvidenceAIService.generate_cross_examination",
        return_value={"opinion": "真实性无异议", "reason": "证据原件清晰"},
    ):
        resp = authenticated_client.post(
            "/api/v1/evidence/ai/generate-cross-examination",
            data=json.dumps({
                "cause_of_action": "借款合同纠纷",
                "our_claim": "被告应偿还借款",
                "evidence_name": "银行转账记录",
                "content_summary": "原告通过银行转账向被告转款10万元",
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "cross_examination" in data
