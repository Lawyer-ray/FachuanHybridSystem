"""
Tests for apps.legal_research.services — 法律研究服务
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestKeywordsService:
    """法律研究关键词服务测试"""

    def test_normalize_keyword_query_basic(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("合同纠纷")
        assert result == "合同纠纷"

    def test_normalize_keyword_query_multiple(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("合同纠纷 民间借贷")
        assert "合同纠纷" in result
        assert "民间借贷" in result

    def test_normalize_keyword_query_comma_separated(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("合同纠纷,民间借贷")
        assert "合同纠纷" in result
        assert "民间借贷" in result

    def test_normalize_keyword_query_chinese_separators(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("合同纠纷；民间借贷、借贷纠纷")
        keywords = result.split()
        assert len(keywords) == 3

    def test_normalize_keyword_query_dedup(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("合同纠纷 合同纠纷 民间借贷")
        keywords = result.split()
        assert keywords.count("合同纠纷") == 1

    def test_normalize_keyword_query_empty(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        assert normalize_keyword_query("") == ""
        assert normalize_keyword_query(None) == ""
        assert normalize_keyword_query("   ") == ""

    def test_normalize_keyword_query_newline_separated(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("合同纠纷\n民间借贷\r\n借贷纠纷")
        keywords = result.split()
        assert len(keywords) == 3

    def test_normalize_keyword_query_tab_separated(self) -> None:
        from apps.legal_research.services.keywords import normalize_keyword_query

        result = normalize_keyword_query("合同纠纷\t民间借贷")
        keywords = result.split()
        assert len(keywords) == 2


# ============================================================
# MockTrial Types 测试
# ============================================================


class TestMockTrialTypes:
    """模拟庭审类型测试"""

    def test_mock_trial_step_values(self) -> None:
        from apps.litigation_ai.services.mock_trial.types import MockTrialStep

        assert MockTrialStep.INIT.value == "mt_init"
        assert MockTrialStep.COURT_OPENING.value == "mt_court_opening"
        assert MockTrialStep.COURT_DEBATE.value == "mt_court_debate"

    def test_trial_level_values(self) -> None:
        from apps.litigation_ai.services.mock_trial.types import TrialLevel

        assert TrialLevel.FIRST.value == "first"
        assert TrialLevel.SECOND.value == "second"

    def test_mock_trial_context(self) -> None:
        from apps.litigation_ai.services.mock_trial.types import MockTrialContext, MockTrialStep

        ctx = MockTrialContext(
            session_id="sess_1",
            case_id=1,
            user_id=1,
            current_step=MockTrialStep.INIT,
        )
        assert ctx.session_id == "sess_1"
        assert ctx.case_id == 1
        assert ctx.metadata == {}

    def test_adversarial_config_defaults(self) -> None:
        from apps.litigation_ai.services.mock_trial.types import AdversarialConfig

        cfg = AdversarialConfig()
        assert cfg.plaintiff_model == ""
        assert cfg.debate_rounds == 10
        assert cfg.user_role == "observer"
        assert cfg.trial_level == "first"

    def test_adversarial_config_custom(self) -> None:
        from apps.litigation_ai.services.mock_trial.types import AdversarialConfig

        cfg = AdversarialConfig(
            plaintiff_model="gpt-4",
            defendant_model="claude-3",
            judge_model="qwen2",
            debate_rounds=5,
            user_role="plaintiff",
            trial_level="second",
        )
        assert cfg.plaintiff_model == "gpt-4"
        assert cfg.debate_rounds == 5
        assert cfg.trial_level == "second"


# ============================================================
# MockTrial 模块导入测试
# ============================================================


class TestMockTrialModules:
    """模拟庭审模块可导入性测试"""

    def test_agents_importable(self) -> None:
        from apps.litigation_ai.services.mock_trial import agents

        assert agents is not None

    def test_types_importable(self) -> None:
        from apps.litigation_ai.services.mock_trial import types

        assert types is not None

    def test_debate_service_importable(self) -> None:
        from apps.litigation_ai.services.mock_trial import debate_service

        assert debate_service is not None

    def test_cross_exam_service_importable(self) -> None:
        from apps.litigation_ai.services.mock_trial import cross_exam_service

        assert cross_exam_service is not None

    def test_adversarial_service_importable(self) -> None:
        from apps.litigation_ai.services.mock_trial import adversarial_service

        assert adversarial_service is not None
