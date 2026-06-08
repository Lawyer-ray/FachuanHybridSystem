"""模拟庭审流程服务测试。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import MockTrialFlowService


class TestMockTrialFlowServiceHelpers:
    """MockTrialFlowService 辅助方法测试。"""

    def _make_service(self):
        return MockTrialFlowService()

    # ── parse_step ──

    def test_parse_step_none(self):
        svc = self._make_service()
        from apps.litigation_ai.services.mock_trial.types import MockTrialStep

        assert svc.parse_step(None) == MockTrialStep.INIT

    def test_parse_step_empty_string(self):
        svc = self._make_service()
        from apps.litigation_ai.services.mock_trial.types import MockTrialStep

        assert svc.parse_step("") == MockTrialStep.INIT

    def test_parse_step_invalid_value(self):
        svc = self._make_service()
        from apps.litigation_ai.services.mock_trial.types import MockTrialStep

        assert svc.parse_step("invalid_step") == MockTrialStep.INIT

    def test_parse_step_valid(self):
        svc = self._make_service()
        from apps.litigation_ai.services.mock_trial.types import MockTrialStep

        # Check that valid step values are parsed correctly
        for step in MockTrialStep:
            result = svc.parse_step(step.value)
            assert result == step

    # ── _parse_mode ──

    def test_parse_mode_judge_by_number(self):
        svc = self._make_service()
        from apps.litigation_ai.models.choices import MockTrialMode

        assert svc._parse_mode("1") == MockTrialMode.JUDGE

    def test_parse_mode_cross_exam_by_number(self):
        svc = self._make_service()
        from apps.litigation_ai.models.choices import MockTrialMode

        assert svc._parse_mode("2") == MockTrialMode.CROSS_EXAM

    def test_parse_mode_debate_by_number(self):
        svc = self._make_service()
        from apps.litigation_ai.models.choices import MockTrialMode

        assert svc._parse_mode("3") == MockTrialMode.DEBATE

    def test_parse_mode_adversarial_by_number(self):
        svc = self._make_service()
        from apps.litigation_ai.models.choices import MockTrialMode

        assert svc._parse_mode("4") == MockTrialMode.ADVERSARIAL

    def test_parse_mode_judge_by_text(self):
        svc = self._make_service()
        from apps.litigation_ai.models.choices import MockTrialMode

        assert svc._parse_mode("法官") == MockTrialMode.JUDGE

    def test_parse_mode_cross_exam_by_text(self):
        svc = self._make_service()
        from apps.litigation_ai.models.choices import MockTrialMode

        assert svc._parse_mode("质证") == MockTrialMode.CROSS_EXAM

    def test_parse_mode_debate_by_text(self):
        svc = self._make_service()
        from apps.litigation_ai.models.choices import MockTrialMode

        assert svc._parse_mode("辩论") == MockTrialMode.DEBATE

    def test_parse_mode_adversarial_by_text(self):
        svc = self._make_service()
        from apps.litigation_ai.models.choices import MockTrialMode

        assert svc._parse_mode("对抗") == MockTrialMode.ADVERSARIAL

    def test_parse_mode_judge_by_full_text(self):
        svc = self._make_service()
        from apps.litigation_ai.models.choices import MockTrialMode

        assert svc._parse_mode("法官视角") == MockTrialMode.JUDGE

    def test_parse_mode_cross_exam_by_full_text(self):
        svc = self._make_service()
        from apps.litigation_ai.models.choices import MockTrialMode

        assert svc._parse_mode("质证模拟") == MockTrialMode.CROSS_EXAM

    def test_parse_mode_debate_by_full_text(self):
        svc = self._make_service()
        from apps.litigation_ai.models.choices import MockTrialMode

        assert svc._parse_mode("辩论模拟") == MockTrialMode.DEBATE

    def test_parse_mode_unknown(self):
        svc = self._make_service()
        assert svc._parse_mode("未知模式") is None

    def test_parse_mode_empty(self):
        svc = self._make_service()
        assert svc._parse_mode("") is None

    def test_parse_mode_whitespace(self):
        svc = self._make_service()
        assert svc._parse_mode("  ") is None

    # ── _format_judge_report ──

    def test_format_judge_report_full(self):
        svc = self._make_service()
        report = {
            "dispute_focuses": [
                {
                    "description": "合同是否有效",
                    "focus_type": "法律关系",
                    "plaintiff_position": "合同有效",
                    "defendant_position": "合同无效",
                    "burden_of_proof": "原告",
                    "key_evidence": ["合同原件", "转账记录"],
                }
            ],
            "evidence_strength_comparison": [
                {
                    "focus": "合同效力",
                    "plaintiff_strength": "强",
                    "defendant_strength": "弱",
                    "analysis": "原告证据充分",
                }
            ],
            "judge_questions": ["请解释合同签订过程"],
            "risk_assessment": "低风险",
            "overall_win_probability": "70%",
            "recommended_strategy": "继续推进",
        }
        result = svc._format_judge_report(report)
        assert "合同是否有效" in result
        assert "原告证据充分" in result
        assert "低风险" in result
        assert "70%" in result

    def test_format_judge_report_empty(self):
        svc = self._make_service()
        report = {}
        result = svc._format_judge_report(report)
        assert "法官视角分析报告" in result

    def test_format_judge_report_no_evidence(self):
        svc = self._make_service()
        report = {
            "dispute_focuses": [{"description": "焦点1"}],
            "evidence_strength_comparison": [],
            "judge_questions": [],
            "risk_assessment": "无",
            "overall_win_probability": "未知",
            "recommended_strategy": "待定",
        }
        result = svc._format_judge_report(report)
        assert "焦点1" in result

    # ── _format_cross_exam_opinion ──

    def test_format_cross_exam_opinion_all_dims(self):
        svc = self._make_service()
        ev = {"name": "合同原件"}
        opinion = {
            "authenticity": {"challenge_strength": "strong", "opinion": "真实性存疑"},
            "legality": {"challenge_strength": "moderate", "opinion": "合法性待确认"},
            "relevance": {"challenge_strength": "weak", "opinion": "关联性强"},
            "proof_power": {"challenge_strength": "strong", "opinion": "证明力弱"},
            "risk_level": "high",
            "suggested_response": "申请鉴定",
        }
        result = svc._format_cross_exam_opinion(ev, opinion)
        assert "合同原件" in result
        assert "真实性存疑" in result
        assert "申请鉴定" in result

    def test_format_cross_exam_opinion_empty(self):
        svc = self._make_service()
        ev = {"name": "证据1"}
        opinion = {}
        result = svc._format_cross_exam_opinion(ev, opinion)
        assert "证据1" in result

    # ── _parse_adversarial_config ──

    def test_parse_adversarial_config_full(self):
        svc = self._make_service()
        text = "原告模型: 1\n被告模型: 3\n法官模型: 5\n辩论轮数: 10\n审级: 一审\n我的角色: 观看"
        models = ["model_a", "model_b", "model_c", "model_d", "model_e"]
        from apps.litigation_ai.services.mock_trial.types import AdversarialConfig

        config = svc._parse_adversarial_config(text, models)
        assert config.plaintiff_model == "model_a"
        assert config.defendant_model == "model_c"
        assert config.judge_model == "model_e"
        assert config.debate_rounds == 10
        assert config.user_role == "observer"
        assert config.trial_level == "first"

    def test_parse_adversarial_config_chinese_colon(self):
        svc = self._make_service()
        text = "原告模型：2\n被告模型：1"
        models = ["model_a", "model_b"]
        from apps.litigation_ai.services.mock_trial.types import AdversarialConfig

        config = svc._parse_adversarial_config(text, models)
        assert config.plaintiff_model == "model_b"
        assert config.defendant_model == "model_a"

    def test_parse_adversarial_config_direct_name(self):
        svc = self._make_service()
        text = "原告模型: gpt-4"
        models = ["gpt-4", "claude-3"]
        from apps.litigation_ai.services.mock_trial.types import AdversarialConfig

        config = svc._parse_adversarial_config(text, models)
        assert config.plaintiff_model == "gpt-4"

    def test_parse_adversarial_config_role_mapping(self):
        svc = self._make_service()
        text = "我的角色: 原告"
        models = ["model_a"]
        from apps.litigation_ai.services.mock_trial.types import AdversarialConfig

        config = svc._parse_adversarial_config(text, models)
        assert config.user_role == "plaintiff"

    def test_parse_adversarial_config_trial_level_second(self):
        svc = self._make_service()
        text = "审级: 二审"
        models = ["model_a"]
        from apps.litigation_ai.services.mock_trial.types import AdversarialConfig

        config = svc._parse_adversarial_config(text, models)
        assert config.trial_level == "second"

    def test_parse_adversarial_config_min_rounds(self):
        svc = self._make_service()
        text = "辩论轮数: 1"
        models = ["model_a"]
        from apps.litigation_ai.services.mock_trial.types import AdversarialConfig

        config = svc._parse_adversarial_config(text, models)
        assert config.debate_rounds == 3  # minimum is 3

    def test_parse_adversarial_config_empty(self):
        svc = self._make_service()
        from apps.litigation_ai.services.mock_trial.types import AdversarialConfig

        config = svc._parse_adversarial_config("", [])
        assert config.debate_rounds == 10  # default
