"""模板匹配策略单元测试。"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.cases.services.template.template_match_policy import CaseTemplateMatchInput, CaseTemplateMatchPolicy


@pytest.fixture
def policy() -> CaseTemplateMatchPolicy:
    return CaseTemplateMatchPolicy()


def _template(**kwargs) -> SimpleNamespace:
    defaults = {
        "case_types": ["civil"],
        "case_stages": ["first_instance"],
        "legal_statuses": ["plaintiff"],
        "legal_status_match_mode": "any",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _input(**kwargs) -> CaseTemplateMatchInput:
    defaults = CaseTemplateMatchInput(
        case_type="civil",
        case_stage="first_instance",
        legal_statuses={"plaintiff"},
    )
    if kwargs:
        defaults = CaseTemplateMatchInput(**kwargs)
    return defaults


# ── is_match ───────────────────────────────────────────────────────────────

def test_match_exact(policy: CaseTemplateMatchPolicy) -> None:
    """完全匹配。"""
    assert policy.is_match(_template(), _input()) is True


def test_match_case_type_mismatch(policy: CaseTemplateMatchPolicy) -> None:
    """案件类型不匹配。"""
    assert policy.is_match(_template(case_types=["criminal"]), _input()) is False


def test_match_case_type_all(policy: CaseTemplateMatchPolicy) -> None:
    """模板 case_types 包含 "all" 匹配任何类型。"""
    assert policy.is_match(_template(case_types=["all"]), _input()) is True


def test_match_case_type_empty(policy: CaseTemplateMatchPolicy) -> None:
    """模板无 case_types 限制匹配所有。"""
    assert policy.is_match(_template(case_types=[]), _input()) is True


def test_match_case_type_none_input(policy: CaseTemplateMatchPolicy) -> None:
    """输入 case_type 为 None 时不匹配具体类型。"""
    assert policy.is_match(
        _template(case_types=["civil"]),
        CaseTemplateMatchInput(case_type=None, case_stage="first_instance", legal_statuses={"plaintiff"}),
    ) is False


def test_match_stage_mismatch(policy: CaseTemplateMatchPolicy) -> None:
    """案件阶段不匹配。"""
    assert policy.is_match(_template(case_stages=["second_instance"]), _input()) is False


def test_match_stage_all(policy: CaseTemplateMatchPolicy) -> None:
    """模板 case_stages 包含 "all" 匹配任何阶段。"""
    assert policy.is_match(_template(case_stages=["all"]), _input()) is True


def test_match_stage_empty(policy: CaseTemplateMatchPolicy) -> None:
    """模板无 case_stages 限制匹配所有。"""
    assert policy.is_match(_template(case_stages=[]), _input()) is True


def test_legal_status_any_mode_match(policy: CaseTemplateMatchPolicy) -> None:
    """any 模式下有交集即匹配。"""
    assert policy.is_match(
        _template(legal_statuses=["plaintiff", "defendant"], legal_status_match_mode="any"),
        CaseTemplateMatchInput(case_type="civil", case_stage="first_instance", legal_statuses={"plaintiff"}),
    ) is True


def test_legal_status_any_mode_no_intersection(policy: CaseTemplateMatchPolicy) -> None:
    """any 模式下无交集不匹配。"""
    assert policy.is_match(
        _template(legal_statuses=["defendant"], legal_status_match_mode="any"),
        CaseTemplateMatchInput(case_type="civil", case_stage="first_instance", legal_statuses={"plaintiff"}),
    ) is False


def test_legal_status_all_mode_match(policy: CaseTemplateMatchPolicy) -> None:
    """all 模式下输入包含模板所有状态。"""
    assert policy.is_match(
        _template(legal_statuses=["plaintiff", "defendant"], legal_status_match_mode="all"),
        CaseTemplateMatchInput(case_type="civil", case_stage="first_instance", legal_statuses={"plaintiff", "defendant", "third_party"}),
    ) is True


def test_legal_status_all_mode_no_match(policy: CaseTemplateMatchPolicy) -> None:
    """all 模式下输入缺少模板要求的状态。"""
    assert policy.is_match(
        _template(legal_statuses=["plaintiff", "defendant"], legal_status_match_mode="all"),
        CaseTemplateMatchInput(case_type="civil", case_stage="first_instance", legal_statuses={"plaintiff"}),
    ) is False


def test_legal_status_exact_mode_match(policy: CaseTemplateMatchPolicy) -> None:
    """exact 模式下完全相等。"""
    assert policy.is_match(
        _template(legal_statuses=["plaintiff"], legal_status_match_mode="exact"),
        CaseTemplateMatchInput(case_type="civil", case_stage="first_instance", legal_statuses={"plaintiff"}),
    ) is True


def test_legal_status_exact_mode_no_match(policy: CaseTemplateMatchPolicy) -> None:
    """exact 模式下不完全相等。"""
    assert policy.is_match(
        _template(legal_statuses=["plaintiff"], legal_status_match_mode="exact"),
        CaseTemplateMatchInput(case_type="civil", case_stage="first_instance", legal_statuses={"plaintiff", "defendant"}),
    ) is False


def test_legal_status_empty_template(policy: CaseTemplateMatchPolicy) -> None:
    """模板无 legal_statuses 限制匹配所有。"""
    assert policy.is_match(
        _template(legal_statuses=[]),
        CaseTemplateMatchInput(case_type="civil", case_stage="first_instance", legal_statuses={"plaintiff"}),
    ) is True


def test_legal_status_any_empty_input(policy: CaseTemplateMatchPolicy) -> None:
    """any 模式下输入为空返回 True。"""
    assert policy.is_match(
        _template(legal_statuses=["plaintiff"], legal_status_match_mode="any"),
        CaseTemplateMatchInput(case_type="civil", case_stage="first_instance", legal_statuses=set()),
    ) is True


def test_legal_status_unknown_mode_defaults_to_any(policy: CaseTemplateMatchPolicy) -> None:
    """未知匹配模式默认走 any 逻辑。"""
    assert policy.is_match(
        _template(legal_statuses=["plaintiff"], legal_status_match_mode="unknown"),
        CaseTemplateMatchInput(case_type="civil", case_stage="first_instance", legal_statuses=set()),
    ) is True


# ── filter ─────────────────────────────────────────────────────────────────

def test_filter_returns_matching(policy: CaseTemplateMatchPolicy) -> None:
    """filter 返回匹配的模板。"""
    t1 = _template(case_types=["civil"])
    t2 = _template(case_types=["criminal"])
    result = policy.filter([t1, t2], _input())
    assert t1 in result
    assert t2 not in result


def test_filter_empty_templates(policy: CaseTemplateMatchPolicy) -> None:
    """空模板列表返回空。"""
    assert policy.filter([], _input()) == []
