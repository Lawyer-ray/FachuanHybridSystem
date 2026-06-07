"""流程状态机单元测试。"""
from __future__ import annotations

import pytest

from apps.litigation_ai.services.flow.flow_state_machine import FlowStateMachine
from apps.litigation_ai.services.flow.types import ConversationStep


@pytest.fixture
def fsm() -> FlowStateMachine:
    return FlowStateMachine()


# ── parse_step ─────────────────────────────────────────────────────────────

def test_parse_step_none(fsm: FlowStateMachine) -> None:
    """None 返回 INIT。"""
    assert fsm.parse_step(None) == ConversationStep.INIT


def test_parse_step_empty(fsm: FlowStateMachine) -> None:
    """空字符串返回 INIT。"""
    assert fsm.parse_step("") == ConversationStep.INIT


def test_parse_step_valid(fsm: FlowStateMachine) -> None:
    """有效步骤返回对应枚举。"""
    assert fsm.parse_step("document_type") == ConversationStep.DOCUMENT_TYPE
    assert fsm.parse_step("generating") == ConversationStep.GENERATING
    assert fsm.parse_step("completed") == ConversationStep.COMPLETED


def test_parse_step_invalid(fsm: FlowStateMachine) -> None:
    """无效步骤返回 INIT。"""
    assert fsm.parse_step("nonexistent_step") == ConversationStep.INIT


def test_parse_step_all_valid_values(fsm: FlowStateMachine) -> None:
    """所有枚举值都可解析。"""
    for step in ConversationStep:
        assert fsm.parse_step(step.value) == step


# ── choose_primary_document_type ───────────────────────────────────────────

def test_choose_primary_none_list(fsm: FlowStateMachine) -> None:
    """空列表返回 None。"""
    assert fsm.choose_primary_document_type(None) is None
    assert fsm.choose_primary_document_type([]) is None


def test_choose_primary_priority_complaint(fsm: FlowStateMachine) -> None:
    """complaint 优先级最高。"""
    result = fsm.choose_primary_document_type(["defense", "complaint", "counterclaim"])
    assert result == "complaint"


def test_choose_primary_priority_defense(fsm: FlowStateMachine) -> None:
    """defense 优先于 counterclaim。"""
    result = fsm.choose_primary_document_type(["counterclaim_defense", "defense", "counterclaim"])
    assert result == "defense"


def test_choose_primary_priority_counterclaim(fsm: FlowStateMachine) -> None:
    """counterclaim 优先于 counterclaim_defense。"""
    result = fsm.choose_primary_document_type(["counterclaim_defense", "counterclaim"])
    assert result == "counterclaim"


def test_choose_primary_fallback_first(fsm: FlowStateMachine) -> None:
    """不在优先列表中时返回第一个。"""
    result = fsm.choose_primary_document_type(["other_type", "another"])
    assert result == "other_type"


# ── need_doc_plan ──────────────────────────────────────────────────────────

def test_need_doc_plan_true(fsm: FlowStateMachine) -> None:
    """complaint + counterclaim_defense 需要文书计划。"""
    assert fsm.need_doc_plan("complaint", ["complaint", "counterclaim_defense"]) is True


def test_need_doc_plan_false_no_counterclaim_defense(fsm: FlowStateMachine) -> None:
    """无 counterclaim_defense 不需要文书计划。"""
    assert fsm.need_doc_plan("complaint", ["complaint", "defense"]) is False


def test_need_doc_plan_false_not_complaint(fsm: FlowStateMachine) -> None:
    """非 complaint 文书类型不需要文书计划。"""
    assert fsm.need_doc_plan("defense", ["defense", "counterclaim_defense"]) is False


def test_need_doc_plan_false_none_types(fsm: FlowStateMachine) -> None:
    """推荐类型为 None 不需要文书计划。"""
    assert fsm.need_doc_plan("complaint", None) is False


def test_need_doc_plan_false_none_primary(fsm: FlowStateMachine) -> None:
    """主文书类型为 None 不需要文书计划。"""
    assert fsm.need_doc_plan(None, ["counterclaim_defense"]) is False
