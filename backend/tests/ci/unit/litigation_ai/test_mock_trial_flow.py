"""Tests for MockTrialFlowService."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import MockTrialFlowService


class TestParseStep:
    def setup_method(self):
        self.service = MockTrialFlowService()

    def test_none_returns_init(self):
        from apps.litigation_ai.services.mock_trial.types import MockTrialStep

        assert self.service.parse_step(None) == MockTrialStep.INIT

    def test_empty_string_returns_init(self):
        from apps.litigation_ai.services.mock_trial.types import MockTrialStep

        assert self.service.parse_step("") == MockTrialStep.INIT

    def test_valid_step(self):
        from apps.litigation_ai.services.mock_trial.types import MockTrialStep

        assert self.service.parse_step("mt_mode_select") == MockTrialStep.MODE_SELECT

    def test_invalid_step_returns_init(self):
        from apps.litigation_ai.services.mock_trial.types import MockTrialStep

        assert self.service.parse_step("invalid_step") == MockTrialStep.INIT


class TestParseMode:
    def setup_method(self):
        self.service = MockTrialFlowService()

    def test_judge_mode_by_number(self):
        assert self.service._parse_mode("1") == "judge"

    def test_cross_exam_mode_by_number(self):
        assert self.service._parse_mode("2") == "cross_exam"

    def test_debate_mode_by_number(self):
        assert self.service._parse_mode("3") == "debate"

    def test_adversarial_mode_by_number(self):
        assert self.service._parse_mode("4") == "adversarial"

    def test_judge_mode_by_name(self):
        assert self.service._parse_mode("法官") == "judge"
        assert self.service._parse_mode("法官视角") == "judge"

    def test_cross_exam_mode_by_name(self):
        assert self.service._parse_mode("质证") == "cross_exam"
        assert self.service._parse_mode("质证模拟") == "cross_exam"

    def test_debate_mode_by_name(self):
        assert self.service._parse_mode("辩论") == "debate"
        assert self.service._parse_mode("辩论模拟") == "debate"

    def test_adversarial_mode_by_name(self):
        assert self.service._parse_mode("对抗") == "adversarial"
        assert self.service._parse_mode("多agent对抗") == "adversarial"
        assert self.service._parse_mode("多agent") == "adversarial"

    def test_unrecognized_returns_none(self):
        assert self.service._parse_mode("unknown") is None

    def test_empty_string_returns_none(self):
        assert self.service._parse_mode("") is None

    def test_whitespace_handling(self):
        assert self.service._parse_mode("  1  ") == "judge"

    def test_none_input(self):
        assert self.service._parse_mode(None) is None


class TestFormatJudgeReport:
    def setup_method(self):
        self.service = MockTrialFlowService()

    def test_full_report(self):
        report = {
            "dispute_focuses": [
                {
                    "description": "借贷关系是否成立",
                    "focus_type": "事实争议",
                    "plaintiff_position": "成立",
                    "defendant_position": "不成立",
                    "burden_of_proof": "原告",
                    "key_evidence": ["借条", "转账记录"],
                }
            ],
            "evidence_strength_comparison": [
                {
                    "focus": "借贷关系",
                    "plaintiff_strength": "强",
                    "defendant_strength": "弱",
                    "analysis": "原告证据充分",
                }
            ],
            "judge_questions": ["请原告补充转账凭证"],
            "risk_assessment": "中等风险",
            "overall_win_probability": "70%",
            "recommended_strategy": "加强证据",
        }
        result = self.service._format_judge_report(report)
        assert "借贷关系是否成立" in result
        assert "借条" in result
        assert "70%" in result

    def test_empty_report(self):
        report = {}
        result = self.service._format_judge_report(report)
        assert "法官视角分析报告" in result

    def test_report_with_no_evidence(self):
        report = {
            "dispute_focuses": [
                {
                    "description": "焦点1",
                    "focus_type": "类型",
                    "plaintiff_position": "立场",
                    "defendant_position": "反对立场",
                    "burden_of_proof": "原告",
                }
            ],
            "risk_assessment": "低",
            "overall_win_probability": "90%",
            "recommended_strategy": "维持现状",
        }
        result = self.service._format_judge_report(report)
        assert "焦点1" in result
        assert "90%" in result


class TestFormatCrossExamOpinion:
    def setup_method(self):
        self.service = MockTrialFlowService()

    def test_full_opinion(self):
        ev = {"name": "借条原件"}
        opinion = {
            "authenticity": {"challenge_strength": "strong", "opinion": "真实性存疑"},
            "legality": {"challenge_strength": "moderate", "opinion": "合法性没问题"},
            "relevance": {"challenge_strength": "weak", "opinion": "关联性强"},
            "proof_power": {"challenge_strength": "moderate", "opinion": "证明力一般"},
            "risk_level": "medium",
            "suggested_response": "准备反驳",
        }
        result = self.service._format_cross_exam_opinion(ev, opinion)
        assert "借条原件" in result
        assert "真实性存疑" in result
        assert "medium" in result

    def test_empty_opinion(self):
        result = self.service._format_cross_exam_opinion({"name": "证据"}, {})
        assert "证据" in result


class TestParseAdversarialConfig:
    def setup_method(self):
        self.service = MockTrialFlowService()

    def test_parse_config(self):
        models = ["gpt-4", "claude-3", "gemini"]
        text = "原告模型: 1\n被告模型: 2\n法官模型: 3\n辩论轮数: 5\n审级: 二审\n角色: 原告"
        config = self.service._parse_adversarial_config(text, models)
        assert config.plaintiff_model == "gpt-4"
        assert config.defendant_model == "claude-3"
        assert config.judge_model == "gemini"
        assert config.debate_rounds == 5
        assert config.trial_level == "second"
        assert config.user_role == "plaintiff"

    def test_parse_config_defaults(self):
        config = self.service._parse_adversarial_config("", ["gpt-4"])
        assert config.debate_rounds >= 3  # default

    def test_parse_config_model_by_name(self):
        models = ["gpt-4-turbo", "claude-3-opus"]
        text = "原告模型: gpt-4"
        config = self.service._parse_adversarial_config(text, models)
        assert config.plaintiff_model == "gpt-4-turbo"

    def test_parse_config_invalid_rounds(self):
        text = "辩论轮数: abc"
        config = self.service._parse_adversarial_config(text, ["gpt-4"])
        assert config.debate_rounds >= 3  # keeps default

    def test_parse_config_chinese_colon(self):
        text = "原告模型：1\n被告模型：2"
        config = self.service._parse_adversarial_config(text, ["gpt-4", "claude-3"])
        assert config.plaintiff_model == "gpt-4"
        assert config.defendant_model == "claude-3"

    def test_parse_config_min_rounds(self):
        text = "辩论轮数: 1"
        config = self.service._parse_adversarial_config(text, [])
        assert config.debate_rounds >= 3  # clamped to min 3

    def test_parse_config_unknown_role(self):
        text = "角色: 未知角色"
        config = self.service._parse_adversarial_config(text, [])
        assert config.user_role == "observer"

    def test_parse_config_unknown_level(self):
        text = "审级: 三审"
        config = self.service._parse_adversarial_config(text, [])
        assert config.trial_level == "first"  # defaults to first


class TestLazyProperties:
    def test_session_repo_lazy(self):
        service = MockTrialFlowService()
        repo = service.session_repo
        assert repo is not None
        assert service.session_repo is repo

    def test_messenger_lazy(self):
        service = MockTrialFlowService()
        messenger = service.messenger
        assert messenger is not None
        assert service.messenger is messenger
