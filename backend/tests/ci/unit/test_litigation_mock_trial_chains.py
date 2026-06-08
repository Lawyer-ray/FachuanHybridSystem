"""litigation_ai/chains/mock_trial_chains.py 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.litigation_ai.chains.mock_trial_chains import (
    CAUSE_SPECIFIC_KNOWLEDGE,
    CrossExamChain,
    CrossExamResult,
    DebateChain,
    DebateResult,
    DisputeFocusChain,
    DisputeFocusResult,
    JudgePerspectiveChain,
    JudgePerspectiveResult,
    _get_cause_knowledge,
)


class TestCauseSpecificKnowledge:
    """CAUSE_SPECIFIC_KNOWLEDGE 常量测试。"""

    def test_contains_civil_lending(self) -> None:
        assert "民间借贷" in CAUSE_SPECIFIC_KNOWLEDGE

    def test_contains_sales_contract(self) -> None:
        assert "买卖合同" in CAUSE_SPECIFIC_KNOWLEDGE

    def test_contains_labor_dispute(self) -> None:
        assert "劳动争议" in CAUSE_SPECIFIC_KNOWLEDGE

    def test_is_dict(self) -> None:
        assert isinstance(CAUSE_SPECIFIC_KNOWLEDGE, dict)


class TestGetCauseKnowledge:
    """_get_cause_knowledge 函数测试。"""

    def test_exact_match(self) -> None:
        result = _get_cause_knowledge("民间借贷")
        assert "借贷合意" in result
        assert "砍头息" in result

    def test_partial_match(self) -> None:
        result = _get_cause_knowledge("民间借贷纠纷")
        assert "借贷合意" in result

    def test_sales_contract(self) -> None:
        result = _get_cause_knowledge("买卖合同纠纷")
        assert "标的物" in result

    def test_labor_dispute(self) -> None:
        result = _get_cause_knowledge("劳动争议")
        assert "劳动关系" in result

    def test_unknown_cause(self) -> None:
        result = _get_cause_knowledge("知识产权纠纷")
        assert result == ""

    def test_empty_string(self) -> None:
        assert _get_cause_knowledge("") == ""

    def test_none_input(self) -> None:
        assert _get_cause_knowledge(None) == ""  # type: ignore[arg-type]


class TestJudgePerspectiveResult:
    """JudgePerspectiveResult 数据类测试。"""

    def test_init(self) -> None:
        r = JudgePerspectiveResult(
            report={"focuses": []},
            model="gpt-4",
            token_usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )
        assert r.report == {"focuses": []}
        assert r.model == "gpt-4"
        assert r.token_usage["total_tokens"] == 150


class TestCrossExamResult:
    """CrossExamResult 数据类测试。"""

    def test_init(self) -> None:
        r = CrossExamResult(
            opinion={"authenticity": "strong"},
            model="gpt-4",
            token_usage={"total_tokens": 200},
        )
        assert r.opinion["authenticity"] == "strong"


class TestDisputeFocusResult:
    """DisputeFocusResult 数据类测试。"""

    def test_init(self) -> None:
        r = DisputeFocusResult(focuses=[{"desc": "test"}], model="gpt-4")
        assert len(r.focuses) == 1


class TestDebateResult:
    """DebateResult 数据类测试。"""

    def test_init(self) -> None:
        r = DebateResult(rebuttal="反驳内容", model="gpt-4")
        assert r.rebuttal == "反驳内容"


class TestJudgePerspectiveChainBuildMessages:
    """JudgePerspectiveChain._build_messages 测试。"""

    def test_basic_structure(self) -> None:
        chain = JudgePerspectiveChain()
        case_info = {
            "case_name": "测试案",
            "cause_of_action": "民间借贷纠纷",
            "target_amount": 100000,
            "case_stage": "一审",
            "parties": [
                {"name": "原告", "legal_status": "原告", "is_our_side": True},
                {"name": "被告", "legal_status": "被告", "is_our_side": False},
            ],
        }
        messages = chain._build_messages(case_info, "证据文本")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "资深法官" in messages[0]["content"]
        assert "测试案" in messages[1]["content"]
        assert "民间借贷" in messages[0]["content"]

    def test_unknown_cause_no_knowledge(self) -> None:
        chain = JudgePerspectiveChain()
        case_info = {
            "case_name": "test",
            "cause_of_action": "未知案由",
            "parties": [],
        }
        messages = chain._build_messages(case_info, "")
        assert "本案由特定关注点" not in messages[0]["content"]

    def test_parties_text(self) -> None:
        chain = JudgePerspectiveChain()
        case_info = {
            "case_name": "test",
            "cause_of_action": "",
            "parties": [
                {"name": "A公司", "legal_status": "原告", "is_our_side": True},
                {"name": "B公司", "legal_status": "被告", "is_our_side": False},
            ],
        }
        messages = chain._build_messages(case_info, "")
        user_content = messages[1]["content"]
        assert "A公司" in user_content
        assert "B公司" in user_content
        assert "我方" in user_content
        assert "对方" in user_content

    def test_no_parties(self) -> None:
        chain = JudgePerspectiveChain()
        case_info = {"case_name": "test", "cause_of_action": "", "parties": []}
        messages = chain._build_messages(case_info, "")
        assert "无" in messages[1]["content"]


class TestJudgePerspectiveChainInit:
    def test_default_model(self) -> None:
        chain = JudgePerspectiveChain()
        assert chain._model is None

    def test_custom_model(self) -> None:
        chain = JudgePerspectiveChain(model="gpt-4o")
        assert chain._model == "gpt-4o"


class TestCrossExamChainInit:
    def test_default(self) -> None:
        chain = CrossExamChain()
        assert chain._model is None

    def test_custom_model(self) -> None:
        chain = CrossExamChain(model="gpt-4o")
        assert chain._model == "gpt-4o"


class TestDisputeFocusChainInit:
    def test_default(self) -> None:
        chain = DisputeFocusChain()
        assert chain._model is None


class TestDebateChainInit:
    def test_default(self) -> None:
        chain = DebateChain()
        assert chain._model is None
        assert chain._difficulty == "medium"

    def test_custom_difficulty(self) -> None:
        chain = DebateChain(difficulty="hard")
        assert chain._difficulty == "hard"
