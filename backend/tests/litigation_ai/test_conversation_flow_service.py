from types import SimpleNamespace

import pytest
from asgiref.sync import async_to_sync

from apps.litigation_ai.models import LitigationSession
from apps.litigation_ai.services.conversation_flow_service import ConversationFlowService, ConversationStep, FlowContext
from tests.factories.case_factories import CaseFactory
from tests.factories.organization_factories import LawyerFactory


@pytest.mark.django_db
def test_flow_init_auto_sets_document_type_and_asks_goal(monkeypatch):
    monkeypatch.setattr(
        "apps.litigation_ai.services.prompt_template_service.PromptTemplateService.get_system_template",
        lambda self, name: None,
    )

    case = CaseFactory()
    lawyer = LawyerFactory()
    session = LitigationSession.objects.create(case=case, user=lawyer, status="active", metadata={})

    flow = ConversationFlowService()
    flow._conversation_service = SimpleNamespace(
        get_recommended_document_types=lambda case_id: ["complaint"],
        add_message=lambda **kwargs: None,
    )

    sent = []

    async def send_cb(payload):
        sent.append(payload)

    ctx = FlowContext(
        session_id=str(session.session_id), case_id=case.id, user_id=lawyer.id, current_step=ConversationStep.INIT
    )
    async_to_sync(flow.handle_init)(ctx, send_cb)

    session.refresh_from_db()
    assert session.document_type == "complaint"
    assert session.metadata["current_step"] == ConversationStep.LITIGATION_GOAL.value
    assert any(p.get("type") == "system_message" and "诉讼" in (p.get("content") or "") for p in sent)


@pytest.mark.django_db
def test_flow_init_enters_doc_plan_when_counterclaim_defense_optional(monkeypatch):
    monkeypatch.setattr(
        "apps.litigation_ai.services.prompt_template_service.PromptTemplateService.get_system_template",
        lambda self, name: None,
    )

    case = CaseFactory()
    lawyer = LawyerFactory()
    session = LitigationSession.objects.create(case=case, user=lawyer, status="active", metadata={})

    flow = ConversationFlowService()
    flow._conversation_service = SimpleNamespace(
        get_recommended_document_types=lambda case_id: ["complaint", "counterclaim_defense"],
        add_message=lambda **kwargs: None,
    )

    sent = []

    async def send_cb(payload):
        sent.append(payload)

    ctx = FlowContext(
        session_id=str(session.session_id), case_id=case.id, user_id=lawyer.id, current_step=ConversationStep.INIT
    )
    async_to_sync(flow.handle_init)(ctx, send_cb)

    session.refresh_from_db()
    assert session.metadata["current_step"] == ConversationStep.DOC_PLAN.value
    assert session.metadata["primary_document_type"] == "complaint"
    assert "counterclaim_defense" in session.metadata["optional_document_types"]
    assert any(p.get("type") == "system_message" for p in sent)


@pytest.mark.django_db
def test_goal_intake_can_request_clarification(monkeypatch):
    monkeypatch.setattr(
        "apps.litigation_ai.services.prompt_template_service.PromptTemplateService.get_system_template",
        lambda self, name: None,
    )

    class _FakeGoal:
        goal_text = "追回欠款"
        need_clarification = True
        clarifying_question = "请补充欠款金额。"
        requests = []

        def model_dump(self):
            return {
                "goal_text": self.goal_text,
                "need_clarification": True,
                "clarifying_question": self.clarifying_question,
                "requests": [],
            }

    async def _fake_arun(self, *, case_info, document_type, user_input):
        return _FakeGoal()

    monkeypatch.setattr(
        "apps.litigation_ai.chains.litigation_goal_intake_chain.LitigationGoalIntakeChain.arun",
        _fake_arun,
    )

    case = CaseFactory()
    lawyer = LawyerFactory()
    session = LitigationSession.objects.create(
        case=case, user=lawyer, status="active", document_type="complaint", metadata={}
    )

    flow = ConversationFlowService()
    sent = []

    async def send_cb(payload):
        sent.append(payload)

    ctx = FlowContext(
        session_id=str(session.session_id),
        case_id=case.id,
        user_id=lawyer.id,
        current_step=ConversationStep.LITIGATION_GOAL,
    )
    async_to_sync(flow.handle_litigation_goal_collection)(ctx, "我要追回欠款", send_cb)

    session.refresh_from_db()
    assert session.metadata["current_step"] == ConversationStep.LITIGATION_GOAL.value
    assert session.metadata["litigation_goal"] == "追回欠款"
    assert any("补充" in (p.get("content") or "") for p in sent)
