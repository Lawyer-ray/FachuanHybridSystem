"""litigation_ai 模块真实执行测试 - 覆盖 placeholders/spec, flow/types, agent/schemas, chains/schemas 等。"""
from __future__ import annotations

import pytest
from datetime import datetime


# ============================================================
# litigation_ai/placeholders/spec.py
# ============================================================


class TestLitigationPlaceholderKeys:
    def test_plaintiff_key(self) -> None:
        from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

        assert LitigationPlaceholderKeys.PLAINTIFF == "原告"

    def test_defendant_key(self) -> None:
        from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

        assert LitigationPlaceholderKeys.DEFENDANT == "被告"

    def test_court_key(self) -> None:
        from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

        assert LitigationPlaceholderKeys.COURT == "审理机构"

    def test_enforcement_keys_exist(self) -> None:
        from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

        assert LitigationPlaceholderKeys.ENFORCEMENT_APPLICANT_PARTY == "申请人信息"
        assert LitigationPlaceholderKeys.ENFORCEMENT_RESPONDENT_PARTY == "被申请人信息"
        assert LitigationPlaceholderKeys.ENFORCEMENT_CASE_NUMBER == "执行依据案号"

    def test_complaint_keys(self) -> None:
        from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

        assert LitigationPlaceholderKeys.COMPLAINT_PARTY == "起诉状当事人信息"
        assert LitigationPlaceholderKeys.COMPLAINT_SIGNATURE == "起诉状签名盖章信息"

    def test_defense_keys(self) -> None:
        from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

        assert LitigationPlaceholderKeys.DEFENSE_PARTY == "答辩状当事人信息"
        assert LitigationPlaceholderKeys.DEFENSE_SIGNATURE == "答辩状签名盖章信息"

    def test_variable_keys(self) -> None:
        from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys

        assert LitigationPlaceholderKeys.VARIABLE_LITIGATION_REQUEST == "诉讼请求"
        assert LitigationPlaceholderKeys.VARIABLE_FACTS_AND_REASONS == "事实与理由"
        assert LitigationPlaceholderKeys.VARIABLE_DEFENSE_OPINION == "答辩意见"
        assert LitigationPlaceholderKeys.VARIABLE_DEFENSE_REASONS == "答辩理由"


# ============================================================
# litigation_ai/services/flow/types.py
# ============================================================


class TestFlowTypes:
    def test_conversation_step_values(self) -> None:
        from apps.litigation_ai.services.flow.types import ConversationStep

        assert ConversationStep.INIT.value == "init"
        assert ConversationStep.DOCUMENT_TYPE.value == "document_type"
        assert ConversationStep.GENERATING.value == "generating"
        assert ConversationStep.COMPLETED.value == "completed"

    def test_conversation_step_all_steps(self) -> None:
        from apps.litigation_ai.services.flow.types import ConversationStep

        expected_steps = {"init", "document_type", "doc_plan", "litigation_goal",
                          "evidence_selection", "generating", "refining", "completed"}
        actual_steps = {step.value for step in ConversationStep}
        assert actual_steps == expected_steps

    def test_flow_context_creation(self) -> None:
        from apps.litigation_ai.services.flow.types import ConversationStep, FlowContext

        ctx = FlowContext(
            session_id="sess-123",
            case_id=1,
            user_id=1,
            current_step=ConversationStep.INIT,
        )
        assert ctx.session_id == "sess-123"
        assert ctx.document_type is None
        assert ctx.litigation_goal is None
        assert ctx.evidence_list_ids is None

    def test_flow_context_with_metadata(self) -> None:
        from apps.litigation_ai.services.flow.types import ConversationStep, FlowContext

        ctx = FlowContext(
            session_id="sess-456",
            case_id=2,
            user_id=3,
            current_step=ConversationStep.DOCUMENT_TYPE,
            document_type="complaint",
            metadata={"key": "value"},
        )
        assert ctx.document_type == "complaint"
        assert ctx.metadata == {"key": "value"}


# ============================================================
# litigation_ai/agent/schemas.py
# ============================================================


class TestAgentSchemas:
    def test_agent_response_creation(self) -> None:
        from apps.litigation_ai.agent.schemas import AgentResponse

        resp = AgentResponse(type="system_message", content="Hello")
        assert resp.type == "system_message"
        assert resp.content == "Hello"
        assert resp.metadata == {}

    def test_agent_response_with_metadata(self) -> None:
        from apps.litigation_ai.agent.schemas import AgentResponse

        resp = AgentResponse(
            type="assistant_complete",
            content="Done",
            metadata={"tool_calls": ["call1"]},
        )
        assert resp.metadata["tool_calls"] == ["call1"]

    def test_draft_output_complaint(self) -> None:
        from apps.litigation_ai.agent.schemas import DraftOutput

        draft = DraftOutput(
            document_type="complaint",
            litigation_request="请求被告支付货款",
            facts_and_reasons="原告与被告签订合同",
        )
        assert draft.defense_opinion is None
        assert draft.evidence_citations == []

    def test_draft_output_defense(self) -> None:
        from apps.litigation_ai.agent.schemas import DraftOutput

        draft = DraftOutput(
            document_type="defense",
            defense_opinion="不同意原告请求",
            defense_reasons="合同存在瑕疵",
        )
        assert draft.litigation_request is None

    def test_tool_call_record(self) -> None:
        from apps.litigation_ai.agent.schemas import ToolCallRecord

        record = ToolCallRecord(
            tool_name="get_case_info",
            arguments={"case_id": 1},
            result={"name": "Test Case"},
        )
        assert record.tool_name == "get_case_info"
        assert record.timestamp is not None
        assert record.duration_ms is None

    def test_case_info_result(self) -> None:
        from apps.litigation_ai.agent.schemas import CaseInfoResult

        result = CaseInfoResult(
            case_id=1,
            case_name="Test",
            cause_of_action="买卖合同纠纷",
            our_legal_status="plaintiff",
        )
        assert result.target_amount is None
        assert result.parties == []
        assert result.court_info is None

    def test_evidence_search_result(self) -> None:
        from apps.litigation_ai.agent.schemas import EvidenceSearchResult

        result = EvidenceSearchResult(
            evidence_item_id=1,
            text="Contract text here",
            source_name="evidence_list_1",
        )
        assert result.page_start is None
        assert result.relevance_score == 0.0

    def test_evidence_list_item(self) -> None:
        from apps.litigation_ai.agent.schemas import EvidenceListItem

        item = EvidenceListItem(
            evidence_item_id=1,
            name="Contract",
            ownership="our",
        )
        assert item.evidence_type is None
        assert item.has_content is False

    def test_generate_draft_input(self) -> None:
        from apps.litigation_ai.agent.schemas import GenerateDraftInput

        inp = GenerateDraftInput(
            case_id=1,
            document_type="complaint",
            litigation_goal="请求支付货款",
            evidence_context="相关合同和发票",
        )
        assert inp.case_id == 1

    def test_generate_draft_result(self) -> None:
        from apps.litigation_ai.agent.schemas import GenerateDraftResult

        result = GenerateDraftResult(
            display_text="Draft text",
            draft={"title": "Complaint"},
            model="Qwen/Qwen2.5-7B-Instruct",
        )
        assert result.draft["title"] == "Complaint"


# ============================================================
# litigation_ai/chains/schemas.py
# ============================================================


class TestChainSchemas:
    def test_chain_schemas_import(self) -> None:
        from apps.litigation_ai.chains import schemas

        assert schemas is not None

    def test_goal_schemas_import(self) -> None:
        from apps.litigation_ai.chains import goal_schemas

        assert goal_schemas is not None


# ============================================================
# litigation_ai/models (integration tests)
# ============================================================


@pytest.mark.django_db
class TestLitigationSessionModels:
    def test_session_creation(self) -> None:
        from apps.litigation_ai.models.session import LitigationSession
        from apps.cases.models import Case

        case = Case.objects.create(name="Session Test Case")
        session = LitigationSession.objects.create(
            case=case,
            session_type="litigation",
        )
        assert session.pk is not None
        assert session.case_id == case.pk
