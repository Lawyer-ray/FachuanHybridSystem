"""案件访问策略单元测试。"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock

import pytest

from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.core.exceptions import ForbiddenError


@pytest.fixture
def policy() -> CaseAccessPolicy:
    mock_repo = MagicMock()
    return CaseAccessPolicy(case_assignment_repo=mock_repo)


def _user(**kwargs) -> SimpleNamespace:
    defaults = {"id": 1, "is_authenticated": True, "is_admin": False}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── has_access ─────────────────────────────────────────────────────────────

def test_has_access_open_perm(policy: CaseAccessPolicy) -> None:
    """开放权限直接通过。"""
    assert policy.has_access(1, None, None, perm_open_access=True) is True


def test_has_access_unauthenticated(policy: CaseAccessPolicy) -> None:
    """未认证用户无权限。"""
    assert policy.has_access(1, _user(is_authenticated=False), None) is False


def test_has_access_none_user(policy: CaseAccessPolicy) -> None:
    """无用户对象无权限。"""
    assert policy.has_access(1, None, None) is False


def test_has_access_admin(policy: CaseAccessPolicy) -> None:
    """管理员直接通过。"""
    assert policy.has_access(1, _user(is_admin=True), None) is True


def test_has_access_extra_cases(policy: CaseAccessPolicy) -> None:
    """在 extra_cases 集合中的案件通过。"""
    org_access = {"extra_cases": {42, 99}}
    assert policy.has_access(42, _user(), org_access) is True


def test_has_access_extra_cases_not_in_set(policy: CaseAccessPolicy) -> None:
    """不在 extra_cases 集合中的案件不通过。"""
    policy.get_allowed_lawyer_ids = MagicMock(return_value=set())
    policy._case_assignment_repo.has_case_access.return_value = False
    org_access = {"extra_cases": {42, 99}}
    assert policy.has_access(100, _user(), org_access) is False


def test_has_access_extra_cases_list(policy: CaseAccessPolicy) -> None:
    """extra_cases 为列表时也能工作。"""
    org_access = {"extra_cases": [42, 99]}
    assert policy.has_access(42, _user(), org_access) is True


def test_has_access_no_allowed_lawyers(policy: CaseAccessPolicy) -> None:
    """无允许律师且无 extra_cases 时无权限。"""
    policy.get_allowed_lawyer_ids = MagicMock(return_value=set())
    assert policy.has_access(1, _user(), {}) is False


def test_has_access_case_object_check(policy: CaseAccessPolicy) -> None:
    """通过 case 对象检查 assignments。"""
    policy.get_allowed_lawyer_ids = MagicMock(return_value={10})
    mock_case = MagicMock()
    mock_case.assignments.filter.return_value.exists.return_value = True
    assert policy.has_access(1, _user(), {}, case=mock_case) is True


def test_has_access_repo_check(policy: CaseAccessPolicy) -> None:
    """通过 repo 检查案件访问。"""
    policy.get_allowed_lawyer_ids = MagicMock(return_value={10})
    policy._case_assignment_repo.has_case_access.return_value = True
    assert policy.has_access(1, _user(), {}, case=None) is True


# ── ensure_access ──────────────────────────────────────────────────────────

def test_ensure_access_raises_on_no_access(policy: CaseAccessPolicy) -> None:
    """无权限时抛出 ForbiddenError。"""
    with pytest.raises(ForbiddenError):
        policy.ensure_access(case_id=1, user=None, org_access=None)


def test_ensure_access_passes_on_access(policy: CaseAccessPolicy) -> None:
    """有权限时不抛出异常。"""
    policy.ensure_access(case_id=1, user=None, org_access=None, perm_open_access=True)


# ── can_access ─────────────────────────────────────────────────────────────

def test_can_access_authenticated(policy: CaseAccessPolicy) -> None:
    """认证用户返回 True。"""
    assert policy.can_access(_user()) is True


def test_can_access_unauthenticated(policy: CaseAccessPolicy) -> None:
    """未认证用户返回 False。"""
    assert policy.can_access(_user(is_authenticated=False)) is False


def test_can_access_none(policy: CaseAccessPolicy) -> None:
    """None 用户返回 False。"""
    assert policy.can_access(None) is False


# ── filter_queryset ────────────────────────────────────────────────────────

def test_filter_queryset_open_perm(policy: CaseAccessPolicy) -> None:
    """开放权限返回原始 queryset。"""
    qs = MagicMock()
    result = policy.filter_queryset(qs, None, None, perm_open_access=True)
    assert result == qs


def test_filter_queryset_unauthenticated(policy: CaseAccessPolicy) -> None:
    """未认证用户返回空 queryset。"""
    qs = MagicMock()
    policy.filter_queryset(qs, _user(is_authenticated=False), None)
    qs.none.assert_called_once()


def test_filter_queryset_admin(policy: CaseAccessPolicy) -> None:
    """管理员返回原始 queryset。"""
    qs = MagicMock()
    result = policy.filter_queryset(qs, _user(is_admin=True), None)
    assert result == qs


# ── _get_extra_cases ───────────────────────────────────────────────────────

def test_get_extra_cases_none(policy: CaseAccessPolicy) -> None:
    """None org_access 返回空集合。"""
    assert policy._get_extra_cases(None) == set()


def test_get_extra_cases_empty(policy: CaseAccessPolicy) -> None:
    """无 extra_cases key 返回空集合。"""
    assert policy._get_extra_cases({}) == set()


def test_get_extra_cases_set(policy: CaseAccessPolicy) -> None:
    """extra_cases 为 set 类型直接返回。"""
    result = policy._get_extra_cases({"extra_cases": {1, 2}})
    assert result == {1, 2}


def test_get_extra_cases_list(policy: CaseAccessPolicy) -> None:
    """extra_cases 为 list 类型转为 set 返回。"""
    result = policy._get_extra_cases({"extra_cases": [3, 4]})
    assert result == {3, 4}
