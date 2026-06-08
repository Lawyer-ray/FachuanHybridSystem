"""Coverage tests for litigation_ai: mock_trial types, agents, mock_trial_report, chains schemas, evidence_digest_service, session_message_service, litigation_goal_intake_chain."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestMockTrialTypes:
    def test_mock_trial_step_values(self):
        from apps.litigation_ai.services.mock_trial.types import MockTrialStep
        assert MockTrialStep.INIT.value == "mt_init"
        assert MockTrialStep.MODE_SELECT.value == "mt_mode_select"
        assert MockTrialStep.SIMULATION.value == "mt_simulation"
        assert MockTrialStep.COURT_OPENING.value == "mt_court_opening"

    def test_trial_level_values(self):
        from apps.litigation_ai.services.mock_trial.types import TrialLevel
        assert TrialLevel.FIRST.value == "first"
        assert TrialLevel.SECOND.value == "second"

    def test_mock_trial_context_defaults(self):
        from apps.litigation_ai.services.mock_trial.types import MockTrialContext, MockTrialStep
        ctx = MockTrialContext(session_id="s1", case_id=1, user_id=2, current_step=MockTrialStep.INIT)
        assert ctx.session_id == "s1"
        assert ctx.mode is None
        assert ctx.metadata == {}

    def test_adversarial_config_defaults(self):
        from apps.litigation_ai.services.mock_trial.types import AdversarialConfig
        cfg = AdversarialConfig()
        assert cfg.debate_rounds == 10
        assert cfg.user_role == "observer"
        assert cfg.trial_level == "first"


class TestMockTrialAgents:
    def test_role_constants(self):
        from apps.litigation_ai.services.mock_trial.agents import PLAINTIFF, DEFENDANT, JUDGE, CLERK
        assert PLAINTIFF == "plaintiff"
        assert DEFENDANT == "defendant"
        assert JUDGE == "judge"
        assert CLERK == "clerk"

    def test_role_labels(self):
        from apps.litigation_ai.services.mock_trial.agents import ROLE_LABELS
        assert "plaintiff" in ROLE_LABELS
        assert "defendant" in ROLE_LABELS

    def test_judge_prompts_exist(self):
        from apps.litigation_ai.services.mock_trial.agents import (
            JUDGE_OPEN_FIRST, JUDGE_OPEN_SECOND, JUDGE_IDENTITY_CHECK,
            JUDGE_RIGHTS_NOTICE, JUDGE_CROSS_EXAM, JUDGE_DEBATE_START,
            JUDGE_FINAL_STATEMENT, JUDGE_CLOSING, CLERK_ANNOUNCE,
        )
        for prompt in [JUDGE_OPEN_FIRST, JUDGE_OPEN_SECOND, JUDGE_IDENTITY_CHECK,
                       JUDGE_RIGHTS_NOTICE, JUDGE_CROSS_EXAM, JUDGE_DEBATE_START,
                       JUDGE_FINAL_STATEMENT, JUDGE_CLOSING, CLERK_ANNOUNCE]:
            assert isinstance(prompt, str)
            assert len(prompt) > 10

    def test_system_prompts_exist(self):
        from apps.litigation_ai.services.mock_trial.agents import (
            PLAINTIFF_SYSTEM, DEFENDANT_SYSTEM, JUDGE_SYSTEM, JUDGE_SUMMARY_SYSTEM
        )
        for p in [PLAINTIFF_SYSTEM, DEFENDANT_SYSTEM, JUDGE_SYSTEM, JUDGE_SUMMARY_SYSTEM]:
            assert len(p) > 50

    def test_agent_dataclass(self):
        from apps.litigation_ai.services.mock_trial.agents import Agent
        agent = Agent(role="plaintiff", model="gpt-4", system_prompt="test prompt")
        assert agent.role == "plaintiff"


class TestMockTrialSchemas:
    def test_dispute_focus(self):
        from apps.litigation_ai.chains.mock_trial_schemas import DisputeFocus
        focus = DisputeFocus(
            description="借贷关系是否成立",
            focus_type="事实争议",
            plaintiff_position="原告主张成立",
            defendant_position="被告否认",
            burden_of_proof="原告",
        )
        assert focus.description == "借贷关系是否成立"

    def test_evidence_strength_item(self):
        from apps.litigation_ai.chains.mock_trial_schemas import EvidenceStrengthItem
        item = EvidenceStrengthItem(
            focus="借款交付",
            plaintiff_strength="strong",
            defendant_strength="weak",
            analysis="原告证据充分",
        )
        assert item.plaintiff_strength == "strong"

    def test_judge_perspective_report(self):
        from apps.litigation_ai.chains.mock_trial_schemas import JudgePerspectiveReport
        report = JudgePerspectiveReport(
            dispute_focuses=[],
            evidence_strength_comparison=[],
            risk_assessment="中等风险",
            judge_questions=["借款是否实际交付？"],
            overall_win_probability="60%-70%",
            recommended_strategy="重点准备交付证据",
        )
        assert report.risk_assessment == "中等风险"

    def test_cross_exam_opinion(self):
        from apps.litigation_ai.chains.mock_trial_schemas import CrossExamOpinion, EvidenceExamItem
        opinion = CrossExamOpinion(
            evidence_name="借条",
            authenticity=EvidenceExamItem(opinion="认可", challenge_strength="weak"),
            legality=EvidenceExamItem(opinion="认可", challenge_strength="weak"),
            relevance=EvidenceExamItem(opinion="认可", challenge_strength="moderate"),
            proof_power=EvidenceExamItem(opinion="较强", challenge_strength="weak"),
            suggested_response="认可真实性",
            risk_level="low",
        )
        assert opinion.evidence_name == "借条"


class TestMockTrialReportPlaceholder:
    def test_generate_with_data(self):
        from apps.litigation_ai.placeholders.mock_trial_report import MockTrialReportPlaceholderService
        svc = MockTrialReportPlaceholderService()
        context = {
            "case_info": {"case_name": "张三诉李四", "cause_of_action": "借贷纠纷"},
            "report_data": {
                "mode": "judge",
                "report": {
                    "dispute_focuses": [{"description": "借贷关系", "plaintiff_position": "成立"}],
                    "evidence_strength_comparison": [{"focus": "借款交付", "plaintiff_strength": "strong", "defendant_strength": "weak", "analysis": "充分"}],
                    "risk_assessment": "中等",
                    "overall_win_probability": "70%",
                    "recommended_strategy": "准备充分证据",
                },
            },
        }
        result = svc.generate(context)
        assert "模拟庭审_案件名称" in result
        assert result["模拟庭审_案件名称"] == "张三诉李四"
        assert result["模拟庭审_模式"] == "法官视角分析"

    def test_format_focuses_empty(self):
        from apps.litigation_ai.placeholders.mock_trial_report import MockTrialReportPlaceholderService
        svc = MockTrialReportPlaceholderService()
        assert svc._format_focuses([]) == "无"

    def test_format_evidence_empty(self):
        from apps.litigation_ai.placeholders.mock_trial_report import MockTrialReportPlaceholderService
        svc = MockTrialReportPlaceholderService()
        assert svc._format_evidence_analysis([]) == "无"


class TestEvidenceDigestService:
    def test_search_evidence_empty_ids(self):
        from apps.litigation_ai.services.evidence.evidence_digest_service import EvidenceDigestService
        svc = EvidenceDigestService()
        result = svc.search_evidence_for_agent("test query", [])
        assert result == []


class TestLitigationGoalIntakeChain:
    def test_fallback_intake_empty(self):
        from apps.litigation_ai.chains.litigation_goal_intake_chain import LitigationGoalIntakeChain
        chain = LitigationGoalIntakeChain()
        result = chain._fallback_intake(document_type="complaint", user_input="", notes="test")
        assert result.need_clarification is True
        assert len(result.clarifying_question) > 0

    def test_fallback_intake_short_input(self):
        from apps.litigation_ai.chains.litigation_goal_intake_chain import LitigationGoalIntakeChain
        chain = LitigationGoalIntakeChain()
        result = chain._fallback_intake(document_type="complaint", user_input="abc", notes="test")
        assert result.need_clarification is True

    def test_fallback_intake_good_input(self):
        from apps.litigation_ai.chains.litigation_goal_intake_chain import LitigationGoalIntakeChain
        chain = LitigationGoalIntakeChain()
        result = chain._fallback_intake(document_type="complaint", user_input="请求被告偿还借款本金100万元及利息", notes="test")
        assert result.need_clarification is False
        assert result.goal_text == "请求被告偿还借款本金100万元及利息"

    def test_default_prompt(self):
        from apps.litigation_ai.chains.litigation_goal_intake_chain import LitigationGoalIntakeChain
        chain = LitigationGoalIntakeChain()
        prompt = chain._default_prompt()
        assert "诉讼" in prompt
