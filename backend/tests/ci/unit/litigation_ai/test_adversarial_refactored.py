"""Tests for adversarial service pure functions and config parsing."""

from __future__ import annotations

from apps.litigation_ai.services.mock_trial.mock_trial_flow_service import MockTrialFlowService


class TestParseAdversarialConfig:
    """Test the _parse_adversarial_config method which is a pure config parser."""

    def setup_method(self) -> None:
        self.service = MockTrialFlowService()
        self.models = ["model_a", "model_b", "model_c", "model_d", "model_e"]

    def test_default_config(self) -> None:
        config = self.service._parse_adversarial_config("", self.models)
        assert config.plaintiff_model == ""
        assert config.defendant_model == ""

    def test_plaintiff_model_by_index(self) -> None:
        config = self.service._parse_adversarial_config("原告模型: 1", self.models)
        assert config.plaintiff_model == "model_a"

    def test_defendant_model_by_index(self) -> None:
        config = self.service._parse_adversarial_config("被告模型: 3", self.models)
        assert config.defendant_model == "model_c"

    def test_judge_model_by_name(self) -> None:
        config = self.service._parse_adversarial_config("法官模型: model_b", self.models)
        assert config.judge_model == "model_b"

    def test_debate_rounds(self) -> None:
        config = self.service._parse_adversarial_config("辩论轮数: 10", self.models)
        assert config.debate_rounds == 10

    def test_debate_rounds_minimum(self) -> None:
        config = self.service._parse_adversarial_config("辩论轮数: 1", self.models)
        assert config.debate_rounds >= 3

    def test_user_role(self) -> None:
        config = self.service._parse_adversarial_config("我的角色: 原告", self.models)
        assert config.user_role == "plaintiff"

    def test_user_role_defendant(self) -> None:
        config = self.service._parse_adversarial_config("我的角色: 被告", self.models)
        assert config.user_role == "defendant"

    def test_trial_level(self) -> None:
        config = self.service._parse_adversarial_config("审级: 二审", self.models)
        assert config.trial_level == "second"

    def test_multi_line_config(self) -> None:
        text = "原告模型: 1\n被告模型: 2\n法官模型: 3\n辩论轮数: 8\n审级: 一审\n我的角色: 观看"
        config = self.service._parse_adversarial_config(text, self.models)
        assert config.plaintiff_model == "model_a"
        assert config.defendant_model == "model_b"
        assert config.judge_model == "model_c"
        assert config.debate_rounds == 8
        assert config.trial_level == "first"
        assert config.user_role == "observer"

    def test_invalid_rounds_ignored(self) -> None:
        config = self.service._parse_adversarial_config("辩论轮数: abc", self.models)
        assert config.debate_rounds >= 3  # default

    def test_chinese_colon(self) -> None:
        config = self.service._parse_adversarial_config("原告模型：2", self.models)
        assert config.plaintiff_model == "model_b"

    def test_model_partial_match(self) -> None:
        config = self.service._parse_adversarial_config("原告模型: model", self.models)
        assert "model" in config.plaintiff_model.lower()

    def test_unknown_role_default_observer(self) -> None:
        config = self.service._parse_adversarial_config("我的角色: 未知", self.models)
        assert config.user_role == "observer"
