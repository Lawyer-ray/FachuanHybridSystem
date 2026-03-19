from __future__ import annotations

from concurrent.futures import TimeoutError as FutureTimeoutError

import pytest
from django.core.cache import cache

from apps.core.exceptions import ConflictError, RecognitionTimeoutError, ServiceUnavailableError
from apps.legal_research.models import LegalResearchResult, LegalResearchTask, LegalResearchTaskEvent, LegalResearchTaskStatus
from apps.legal_research.schemas import AgentSearchRequestV1
from apps.legal_research.services.capability_service import LegalResearchCapabilityService
from apps.organization.models import AccountCredential


def _build_credential(*, lawyer) -> AccountCredential:
    return AccountCredential.objects.create(
        lawyer=lawyer,
        site_name="wkxx",
        url="https://www.wkinfo.com.cn/login/index",
        account="capability-account",
        password="capability-password",
    )


@pytest.mark.django_db
def test_capability_search_returns_structured_response_and_idempotent_cache(monkeypatch: pytest.MonkeyPatch, lawyer) -> None:
    cache.clear()
    credential = _build_credential(lawyer=lawyer)
    calls = {"count": 0}

    def _stub_execute(self, *, task_id: str, timeout_ms: int):  # noqa: ARG001
        calls["count"] += 1
        task = LegalResearchTask.objects.get(id=int(task_id))
        task.status = LegalResearchTaskStatus.COMPLETED
        task.scanned_count = 12
        task.matched_count = 1
        task.message = "能力模式执行完成"
        task.save(update_fields=["status", "scanned_count", "matched_count", "message", "updated_at"])
        LegalResearchResult.objects.create(
            task=task,
            rank=1,
            source_doc_id="DOC-001",
            source_url="https://example.com/doc-001",
            title="示例案例",
            court_text="示例法院",
            judgment_date="2025-10-01",
            case_digest="本院认为，被告存在违约行为。",
            similarity_score=0.92,
            match_reason="事实要素与争点高度重合",
            metadata={
                "similarity_structured": {
                    "decision": "high",
                    "facts_match": 0.9,
                    "legal_relation_match": 0.88,
                    "dispute_match": 0.91,
                    "damage_match": 0.84,
                    "key_conflicts": ["无显著冲突"],
                }
            },
        )
        return {
            "status": "completed",
            "query_trace": {
                "primary_queries": ["买卖合同 违约 赔偿"],
                "expansion_queries": ["买卖合同 逾期交货"],
                "feedback_queries": ["买卖合同 价差损失"],
                "query_stats": {
                    "买卖合同 违约 赔偿": {"scanned": 10, "matched": 2},
                    "买卖合同 逾期交货": {"scanned": 6, "matched": 1},
                    "买卖合同 价差损失": {"scanned": 4, "matched": 1},
                },
            },
        }

    monkeypatch.setattr(LegalResearchCapabilityService, "_execute_with_timeout", _stub_execute)
    service = LegalResearchCapabilityService()
    payload = AgentSearchRequestV1(
        credential_id=credential.id,
        intent="similar_case",
        facts="被告逾期交货，原告主张价差损失与违约金。",
        legal_issue="违约责任与损失范围",
        cause_type="",
        target_count=3,
    )

    first = service.search(payload=payload, user=lawyer, idempotency_key="idem-key-001")
    second = service.search(payload=payload, user=lawyer, idempotency_key="idem-key-001")

    assert first.status == "partial"
    assert first.degradation_flags == ["partial_result"]
    assert len(first.results) == 1
    assert first.results[0].doc_id == "DOC-001"
    assert first.results[0].decision == "accept"
    assert first.query_trace.primary_queries == ["买卖合同 违约 赔偿"]
    assert first.query_trace.query_type_metrics["primary"].contribution_rate == 0.5
    assert first.query_trace.query_type_metrics["expansion"].contribution_rate == 0.25
    assert first.query_trace.query_type_metrics["feedback"].contribution_rate == 0.25
    assert calls["count"] == 1
    assert second.request_id == first.request_id
    task = LegalResearchTask.objects.order_by("-id").first()
    assert task is not None
    assert LegalResearchTaskEvent.objects.filter(task_id=task.id, interface_name="capability_direct_call", success=True).exists()


@pytest.mark.django_db
def test_capability_search_applies_hard_filters(monkeypatch: pytest.MonkeyPatch, lawyer) -> None:
    cache.clear()
    credential = _build_credential(lawyer=lawyer)

    def _stub_execute(self, *, task_id: str, timeout_ms: int):  # noqa: ARG001
        task = LegalResearchTask.objects.get(id=int(task_id))
        task.status = LegalResearchTaskStatus.COMPLETED
        task.scanned_count = 20
        task.matched_count = 2
        task.save(update_fields=["status", "scanned_count", "matched_count", "updated_at"])
        LegalResearchResult.objects.create(
            task=task,
            rank=1,
            source_doc_id="DOC-HARD-1",
            source_url="https://example.com/doc-hard-1",
            title="买卖合同纠纷一案",
            court_text="广州市中级人民法院",
            judgment_date="2025-06-01",
            case_digest="这是买卖合同纠纷，争议涉及逾期交货。",
            similarity_score=0.93,
            match_reason="核心事实重合",
            metadata={"similarity_structured": {"decision": "high"}},
        )
        LegalResearchResult.objects.create(
            task=task,
            rank=2,
            source_doc_id="DOC-HARD-2",
            source_url="https://example.com/doc-hard-2",
            title="买卖合同纠纷二案",
            court_text="深圳市中级人民法院",
            judgment_date="2023-03-01",
            case_digest="这是买卖合同纠纷，但法院与年份不满足过滤条件。",
            similarity_score=0.9,
            match_reason="次优候选",
            metadata={"similarity_structured": {"decision": "high"}},
        )
        return {"status": "completed"}

    monkeypatch.setattr(LegalResearchCapabilityService, "_execute_with_timeout", _stub_execute)
    service = LegalResearchCapabilityService()
    payload = AgentSearchRequestV1(
        credential_id=credential.id,
        intent="same_court_precedent",
        facts="围绕买卖合同违约责任展开。",
        legal_issue="逾期交货损失",
        cause_type="买卖合同纠纷",
        court_scope={"mode": "same_court", "court_name": "广州市中级人民法院"},
        year_range={"from": 2024, "to": 2025},
        target_count=1,
    )

    response = service.search(payload=payload, user=lawyer, idempotency_key="")
    assert len(response.results) == 1
    assert response.results[0].doc_id == "DOC-HARD-1"
    assert "constraint_unsatisfied" in response.degradation_flags


@pytest.mark.django_db
def test_capability_search_rejects_idempotency_conflict(monkeypatch: pytest.MonkeyPatch, lawyer) -> None:
    cache.clear()
    credential = _build_credential(lawyer=lawyer)

    def _stub_execute(self, *, task_id: str, timeout_ms: int):  # noqa: ARG001
        task = LegalResearchTask.objects.get(id=int(task_id))
        task.status = LegalResearchTaskStatus.COMPLETED
        task.save(update_fields=["status", "updated_at"])
        return {"status": "completed"}

    monkeypatch.setattr(LegalResearchCapabilityService, "_execute_with_timeout", _stub_execute)
    service = LegalResearchCapabilityService()

    payload_a = AgentSearchRequestV1(
        credential_id=credential.id,
        intent="similar_case",
        facts="事实A：逾期交货。",
        legal_issue="争点A",
        cause_type="买卖合同纠纷",
    )
    payload_b = AgentSearchRequestV1(
        credential_id=credential.id,
        intent="similar_case",
        facts="事实B：货物质量瑕疵。",
        legal_issue="争点B",
        cause_type="买卖合同纠纷",
    )

    service.search(payload=payload_a, user=lawyer, idempotency_key="idem-key-conflict")
    with pytest.raises(ConflictError, match="Idempotency-Key"):
        service.search(payload=payload_b, user=lawyer, idempotency_key="idem-key-conflict")


@pytest.mark.django_db
def test_capability_search_timeout_raises_504_exception(monkeypatch: pytest.MonkeyPatch, lawyer) -> None:
    cache.clear()
    credential = _build_credential(lawyer=lawyer)

    def _stub_timeout(self, *, task_id: str, timeout_ms: int):  # noqa: ARG001
        raise FutureTimeoutError()

    monkeypatch.setattr(LegalResearchCapabilityService, "_execute_with_timeout", _stub_timeout)
    service = LegalResearchCapabilityService()
    payload = AgentSearchRequestV1(
        credential_id=credential.id,
        intent="similar_case",
        facts="被告未按约交付货物。",
        legal_issue="违约责任承担方式",
        cause_type="买卖合同纠纷",
        target_count=2,
    )

    with pytest.raises(RecognitionTimeoutError, match="超时"):
        service.search(payload=payload, user=lawyer, idempotency_key="")


@pytest.mark.django_db
def test_capability_search_extracts_four_snippet_sections(monkeypatch: pytest.MonkeyPatch, lawyer) -> None:
    cache.clear()
    credential = _build_credential(lawyer=lawyer)

    def _stub_execute(self, *, task_id: str, timeout_ms: int):  # noqa: ARG001
        task = LegalResearchTask.objects.get(id=int(task_id))
        task.status = LegalResearchTaskStatus.COMPLETED
        task.scanned_count = 8
        task.matched_count = 1
        task.save(update_fields=["status", "scanned_count", "matched_count", "updated_at"])
        LegalResearchResult.objects.create(
            task=task,
            rank=1,
            source_doc_id="DOC-SNIPPET-1",
            source_url="https://example.com/doc-snippet-1",
            title="买卖合同纠纷示例",
            court_text="广州市中级人民法院",
            judgment_date="2024-06-01",
            case_digest="围绕货物买卖的违约责任争议。",
            similarity_score=0.91,
            match_reason="事实和争点重合",
            metadata={
                "content_excerpt": (
                    "诉讼请求：一、判令被告支付货款。二、判令被告承担违约金。"
                    "\n本院经审理查明：双方签订买卖合同后，被告未按约履行交货义务。"
                    "\n本院认为：被告违约事实清楚，应承担违约责任及价差损失。"
                    "\n判决如下：一、被告于十日内向原告赔偿损失。二、驳回其他诉讼请求。"
                ),
                "similarity_structured": {
                    "decision": "high",
                    "facts_match": 0.9,
                    "legal_relation_match": 0.89,
                    "dispute_match": 0.87,
                    "damage_match": 0.82,
                    "key_conflicts": [],
                },
            },
        )
        return {"status": "completed"}

    monkeypatch.setattr(LegalResearchCapabilityService, "_execute_with_timeout", _stub_execute)
    service = LegalResearchCapabilityService()
    payload = AgentSearchRequestV1(
        credential_id=credential.id,
        intent="similar_case",
        facts="被告逾期交货并产生赔偿争议。",
        legal_issue="违约责任与损失范围",
        cause_type="",
        target_count=1,
    )

    response = service.search(payload=payload, user=lawyer, idempotency_key="")

    assert len(response.results) == 1
    snippets = response.results[0].snippets
    assert "诉讼请求" in snippets.claims
    assert "查明" in snippets.findings
    assert "本院认为" in snippets.reasoning
    assert "判决如下" in snippets.holdings


@pytest.mark.django_db
def test_capability_search_intent_profile_changes_ranking(monkeypatch: pytest.MonkeyPatch, lawyer) -> None:
    cache.clear()
    credential = _build_credential(lawyer=lawyer)

    def _stub_execute(self, *, task_id: str, timeout_ms: int):  # noqa: ARG001
        task = LegalResearchTask.objects.get(id=int(task_id))
        task.status = LegalResearchTaskStatus.COMPLETED
        task.scanned_count = 20
        task.matched_count = 2
        task.save(update_fields=["status", "scanned_count", "matched_count", "updated_at"])
        LegalResearchResult.objects.create(
            task=task,
            rank=1,
            source_doc_id="DOC-INTENT-A",
            source_url="https://example.com/doc-intent-a",
            title="买卖合同纠纷（异法院）",
            court_text="深圳市中级人民法院",
            judgment_date="2024-04-01",
            case_digest="围绕逾期交货与价差损失。",
            similarity_score=0.95,
            match_reason="事实高度重合",
            metadata={
                "similarity_structured": {
                    "decision": "high",
                    "facts_match": 0.95,
                    "legal_relation_match": 0.82,
                    "dispute_match": 0.90,
                    "damage_match": 0.86,
                }
            },
        )
        LegalResearchResult.objects.create(
            task=task,
            rank=2,
            source_doc_id="DOC-INTENT-B",
            source_url="https://example.com/doc-intent-b",
            title="买卖合同纠纷（同法院）",
            court_text="广州市中级人民法院",
            judgment_date="2024-02-01",
            case_digest="围绕交货迟延责任。",
            similarity_score=0.88,
            match_reason="法律关系与裁判逻辑重合",
            metadata={
                "content_excerpt": "本院认为：被告存在迟延交货。判决如下：支持部分赔偿请求。",
                "similarity_structured": {
                    "decision": "high",
                    "facts_match": 0.78,
                    "legal_relation_match": 0.85,
                    "dispute_match": 0.82,
                    "damage_match": 0.80,
                },
            },
        )
        return {"status": "completed"}

    monkeypatch.setattr(LegalResearchCapabilityService, "_execute_with_timeout", _stub_execute)
    service = LegalResearchCapabilityService()
    base_kwargs = {
        "credential_id": credential.id,
        "facts": "买卖合同中迟延交货引发赔偿争议。",
        "legal_issue": "违约责任",
        "cause_type": "买卖合同纠纷",
        "court_scope": {"mode": "same_level", "court_name": "广州市中级人民法院"},
        "target_count": 2,
    }

    similar_response = service.search(
        payload=AgentSearchRequestV1(intent="similar_case", **base_kwargs),
        user=lawyer,
        idempotency_key="",
    )
    same_court_response = service.search(
        payload=AgentSearchRequestV1(intent="same_court_precedent", **base_kwargs),
        user=lawyer,
        idempotency_key="",
    )

    assert similar_response.results[0].doc_id == "DOC-INTENT-A"
    assert same_court_response.results[0].doc_id == "DOC-INTENT-B"


@pytest.mark.django_db
def test_capability_search_returns_busy_when_concurrency_limited(monkeypatch: pytest.MonkeyPatch, lawyer) -> None:
    cache.clear()
    credential = _build_credential(lawyer=lawyer)

    class _BusySemaphore:
        def acquire(self, timeout: float | None = None) -> bool:  # noqa: ARG002
            return False

        def release(self) -> None:
            return None

    monkeypatch.setattr(LegalResearchCapabilityService, "_DIRECT_SEMAPHORE", _BusySemaphore())
    service = LegalResearchCapabilityService()
    payload = AgentSearchRequestV1(
        credential_id=credential.id,
        intent="similar_case",
        facts="被告逾期交货并引发价差损失。",
        legal_issue="违约责任范围",
        cause_type="买卖合同纠纷",
    )

    with pytest.raises(ServiceUnavailableError, match="繁忙"):
        service.search(payload=payload, user=lawyer, idempotency_key="")
    task = LegalResearchTask.objects.order_by("-id").first()
    assert task is not None
    assert LegalResearchTaskEvent.objects.filter(
        task_id=task.id,
        interface_name="capability_direct_call",
        success=False,
        error_code="LEGAL_RESEARCH_CAPABILITY_BUSY",
    ).exists()


@pytest.mark.django_db
def test_capability_search_returns_degraded_when_failure_circuit_open(monkeypatch: pytest.MonkeyPatch, lawyer) -> None:
    cache.clear()
    credential = _build_credential(lawyer=lawyer)

    def _stub_circuit_open(self, *, credential_id: int) -> bool:  # noqa: ARG001
        return True

    monkeypatch.setattr(LegalResearchCapabilityService, "_is_failure_circuit_open", _stub_circuit_open)
    service = LegalResearchCapabilityService()
    payload = AgentSearchRequestV1(
        credential_id=credential.id,
        intent="similar_case",
        facts="被告逾期交货并引发价差损失。",
        legal_issue="违约责任范围",
        cause_type="买卖合同纠纷",
    )

    with pytest.raises(ServiceUnavailableError, match="降级"):
        service.search(payload=payload, user=lawyer, idempotency_key="")
    assert LegalResearchTask.objects.count() == 0
