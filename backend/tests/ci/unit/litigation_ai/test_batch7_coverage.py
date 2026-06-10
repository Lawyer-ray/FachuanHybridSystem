"""Batch7 coverage tests for apps.litigation_ai."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.litigation_ai.models.choices import (
    DocumentType,
    MessageRole,
    MockTrialMode,
    SessionStatus,
    SessionType,
)
from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys
from apps.litigation_ai.chains.goal_schemas import (
    GoalIntakeResult,
    GoalRequestItem,
    UserChoiceResult,
)
from apps.litigation_ai.chains.mock_trial_schemas import (
    CrossExamOpinion,
    DisputeFocus,
    EvidenceExamItem,
    EvidenceStrengthItem,
    JudgePerspectiveReport,
)
from apps.litigation_ai.services.generation.placeholder_render_service import (
    PlaceholderRenderService,
    RenderStats,
)
from apps.litigation_ai.services.flow.types import ConversationStep, FlowContext
from apps.litigation_ai.services.evidence.evidence_text_extraction_service import (
    EvidenceTextExtractionService,
)


# ── DocumentType ────────────────────────────────────────────────────────────


class TestDocumentType:
    def test_complaint_value(self) -> None:
        assert DocumentType.COMPLAINT == "complaint"

    def test_defense_value(self) -> None:
        assert DocumentType.DEFENSE == "defense"

    def test_counterclaim_value(self) -> None:
        assert DocumentType.COUNTERCLAIM == "counterclaim"

    def test_counterclaim_defense_value(self) -> None:
        assert DocumentType.COUNTERCLAIM_DEFENSE == "counterclaim_defense"

    def test_choices_count(self) -> None:
        assert len(DocumentType.choices) == 4


# ── SessionStatus ───────────────────────────────────────────────────────────


class TestSessionStatus:
    def test_active(self) -> None:
        assert SessionStatus.ACTIVE == "active"

    def test_completed(self) -> None:
        assert SessionStatus.COMPLETED == "completed"

    def test_cancelled(self) -> None:
        assert SessionStatus.CANCELLED == "cancelled"


# ── MessageRole ─────────────────────────────────────────────────────────────


class TestMessageRole:
    def test_user(self) -> None:
        assert MessageRole.USER == "user"

    def test_assistant(self) -> None:
        assert MessageRole.ASSISTANT == "assistant"

    def test_system(self) -> None:
        assert MessageRole.SYSTEM == "system"


# ── SessionType ─────────────────────────────────────────────────────────────


class TestSessionType:
    def test_doc_gen(self) -> None:
        assert SessionType.DOC_GEN == "doc_gen"

    def test_mock_trial(self) -> None:
        assert SessionType.MOCK_TRIAL == "mock_trial"


# ── MockTrialMode ───────────────────────────────────────────────────────────


class TestMockTrialMode:
    def test_judge(self) -> None:
        assert MockTrialMode.JUDGE == "judge"

    def test_cross_exam(self) -> None:
        assert MockTrialMode.CROSS_EXAM == "cross_exam"

    def test_debate(self) -> None:
        assert MockTrialMode.DEBATE == "debate"

    def test_adversarial(self) -> None:
        assert MockTrialMode.ADVERSARIAL == "adversarial"


# ── LitigationPlaceholderKeys ───────────────────────────────────────────────


class TestLitigationPlaceholderKeys:
    def test_plaintiff(self) -> None:
        assert LitigationPlaceholderKeys.PLAINTIFF == "原告"

    def test_defendant(self) -> None:
        assert LitigationPlaceholderKeys.DEFENDANT == "被告"

    def test_cause_of_action(self) -> None:
        assert LitigationPlaceholderKeys.CAUSE_OF_ACTION == "案由"

    def test_date(self) -> None:
        assert LitigationPlaceholderKeys.DATE == "日期"

    def test_court(self) -> None:
        assert LitigationPlaceholderKeys.COURT == "审理机构"

    def test_enforcement_keys(self) -> None:
        assert LitigationPlaceholderKeys.ENFORCEMENT_APPLICANT_NAME == "申请人名称"
        assert LitigationPlaceholderKeys.ENFORCEMENT_RESPONDENT_NAME == "被申请人名称"
        assert LitigationPlaceholderKeys.ENFORCEMENT_CASE_NUMBER == "执行依据案号"

    def test_case_lawyer_keys(self) -> None:
        assert LitigationPlaceholderKeys.CASE_LAWYER_NAME == "案件律师姓名"
        assert LitigationPlaceholderKeys.CASE_LAWYER_PHONE == "案件律师电话"


# ── Goal schemas ────────────────────────────────────────────────────────────


class TestGoalSchemas:
    def test_goal_request_item_defaults(self) -> None:
        item = GoalRequestItem()
        assert item.description == ""
        assert item.amount is None
        assert item.target is None

    def test_goal_request_item_with_data(self) -> None:
        item = GoalRequestItem(description="赔偿", amount="10000", target="被告")
        assert item.description == "赔偿"
        assert item.amount == "10000"

    def test_goal_intake_result_defaults(self) -> None:
        result = GoalIntakeResult()
        assert result.goal_text == ""
        assert result.requests == []
        assert result.need_clarification is False

    def test_user_choice_result_defaults(self) -> None:
        result = UserChoiceResult()
        assert result.primary_document_type == ""
        assert result.pending_document_types == []
        assert result.notes == ""


# ── mock_trial_schemas ──────────────────────────────────────────────────────


class TestMockTrialSchemas:
    def test_dispute_focus_creation(self) -> None:
        focus = DisputeFocus(
            description="借款金额争议",
            focus_type="事实争议",
            plaintiff_position="主张100万",
            defendant_position="只认可50万",
            burden_of_proof="原告",
        )
        assert focus.description == "借款金额争议"
        assert focus.key_evidence == []

    def test_evidence_exam_item_creation(self) -> None:
        item = EvidenceExamItem(opinion="真实性无异议", challenge_strength="weak")
        assert item.opinion == "真实性无异议"

    def test_cross_exam_opinion_creation(self) -> None:
        opinion = CrossExamOpinion(
            evidence_name="借条",
            authenticity=EvidenceExamItem(opinion="真实", challenge_strength="weak"),
            legality=EvidenceExamItem(opinion="合法", challenge_strength="weak"),
            relevance=EvidenceExamItem(opinion="有关", challenge_strength="moderate"),
            proof_power=EvidenceExamItem(opinion="强", challenge_strength="strong"),
            suggested_response="认可",
            risk_level="low",
        )
        assert opinion.evidence_name == "借条"

    def test_evidence_strength_item_creation(self) -> None:
        item = EvidenceStrengthItem(
            focus="借款金额",
            plaintiff_strength="strong",
            defendant_strength="weak",
            analysis="原告证据充分",
        )
        assert item.focus == "借款金额"

    def test_judge_perspective_report_creation(self) -> None:
        report = JudgePerspectiveReport(
            dispute_focuses=[],
            evidence_strength_comparison=[],
            risk_assessment="低风险",
            judge_questions=["借款是否实际交付？"],
            overall_win_probability="60%-70%",
            recommended_strategy="强调借条真实性",
        )
        assert report.risk_assessment == "低风险"
        assert report.overall_win_probability == "60%-70%"


# ── PlaceholderRenderService ────────────────────────────────────────────────


class TestPlaceholderRenderService:
    def test_render_empty_template(self) -> None:
        svc = PlaceholderRenderService()
        result, stats = svc.render("", {})
        assert result == ""

    def test_render_no_placeholders(self) -> None:
        svc = PlaceholderRenderService()
        result, stats = svc.render("hello world", {})
        assert result == "hello world"

    def test_render_single_brace_default(self) -> None:
        svc = PlaceholderRenderService()
        template = "原告：{原告}，被告：{被告}"
        values = {"原告": "张三", "被告": "李四"}
        result, stats = svc.render(template, values)
        assert "张三" in result
        assert "李四" in result

    def test_render_double_brace_syntax(self) -> None:
        svc = PlaceholderRenderService()
        template = "原告：{{原告}}"
        values = {"原告": "张三"}
        result, stats = svc.render(template, values, syntax="double")
        assert "张三" in result

    def test_render_none_template(self) -> None:
        svc = PlaceholderRenderService()
        result, stats = svc.render(None, {})
        assert result == ""

    def test_render_stats_hit_rate(self) -> None:
        svc = PlaceholderRenderService()
        result, stats = svc.render("{a} and {b}", {"a": "1"})
        assert stats.hit_rate == 0.5


# ── RenderStats ─────────────────────────────────────────────────────────────


class TestRenderStats:
    def test_hit_rate_empty(self) -> None:
        stats = RenderStats(placeholders_found=[], placeholders_hit=[], placeholders_missed=[])
        assert stats.hit_rate == 1.0


# ── ConversationStep ────────────────────────────────────────────────────────


class TestConversationStep:
    def test_init(self) -> None:
        assert ConversationStep.INIT.value == "init"

    def test_document_type(self) -> None:
        assert ConversationStep.DOCUMENT_TYPE.value == "document_type"

    def test_completed(self) -> None:
        assert ConversationStep.COMPLETED.value == "completed"

    def test_is_str_enum(self) -> None:
        assert isinstance(ConversationStep.INIT, str)


class TestFlowContext:
    def test_basic_creation(self) -> None:
        ctx = FlowContext(session_id="s1", case_id=1, user_id=1, current_step=ConversationStep.INIT)
        assert ctx.session_id == "s1"
        assert ctx.document_type is None


# ── EvidenceTextExtractionService ───────────────────────────────────────────


class TestEvidenceTextExtraction:
    def test_service_can_be_instantiated(self) -> None:
        svc = EvidenceTextExtractionService()
        assert svc is not None

    def test_has_extract_chunks_method(self) -> None:
        svc = EvidenceTextExtractionService()
        assert hasattr(svc, "extract_chunks")
