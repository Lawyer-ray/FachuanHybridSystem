"""当事人权限策略单元测试。"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.client.services.client_access_policy import ClientAccessPolicy
from apps.core.exceptions import PermissionDenied


@pytest.fixture
def policy() -> ClientAccessPolicy:
    return ClientAccessPolicy()


def _user(**kwargs) -> SimpleNamespace:
    defaults = {"id": 1, "is_authenticated": True, "is_superuser": False}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── can_create_client ──────────────────────────────────────────────────────

@patch.object(ClientAccessPolicy, "has_perm", return_value=True)
def test_can_create_client_true(mock_perm, policy: ClientAccessPolicy) -> None:
    """有权限时返回 True。"""
    assert policy.can_create_client(_user()) is True


@patch.object(ClientAccessPolicy, "has_perm", return_value=False)
def test_can_create_client_false(mock_perm, policy: ClientAccessPolicy) -> None:
    """无权限时返回 False。"""
    assert policy.can_create_client(_user()) is False


@patch.object(ClientAccessPolicy, "has_perm", return_value=False)
def test_can_create_client_none_user(mock_perm, policy: ClientAccessPolicy) -> None:
    """None 用户返回 False。"""
    assert policy.can_create_client(None) is False


# ── can_update_client ──────────────────────────────────────────────────────

@patch.object(ClientAccessPolicy, "has_perm", return_value=True)
def test_can_update_client_true(mock_perm, policy: ClientAccessPolicy) -> None:
    """有权限时返回 True。"""
    assert policy.can_update_client(_user()) is True


@patch.object(ClientAccessPolicy, "has_perm", return_value=False)
def test_can_update_client_false(mock_perm, policy: ClientAccessPolicy) -> None:
    """无权限时返回 False。"""
    assert policy.can_update_client(_user()) is False


# ── can_delete_client ──────────────────────────────────────────────────────

@patch.object(ClientAccessPolicy, "has_perm", return_value=True)
def test_can_delete_client_true(mock_perm, policy: ClientAccessPolicy) -> None:
    """有权限时返回 True。"""
    assert policy.can_delete_client(_user()) is True


@patch.object(ClientAccessPolicy, "has_perm", return_value=False)
def test_can_delete_client_false(mock_perm, policy: ClientAccessPolicy) -> None:
    """无权限时返回 False。"""
    assert policy.can_delete_client(_user()) is False


# ── ensure methods ─────────────────────────────────────────────────────────

@patch.object(ClientAccessPolicy, "has_perm", return_value=True)
def test_ensure_can_create_client_passes(mock_perm, policy: ClientAccessPolicy) -> None:
    """有权限时不抛出异常。"""
    policy.ensure_can_create_client(_user())


@patch.object(ClientAccessPolicy, "has_perm", return_value=False)
def test_ensure_can_create_client_raises(mock_perm, policy: ClientAccessPolicy) -> None:
    """无权限时抛出 PermissionDenied。"""
    with pytest.raises(PermissionDenied):
        policy.ensure_can_create_client(_user())


@patch.object(ClientAccessPolicy, "has_perm", return_value=True)
def test_ensure_can_update_client_passes(mock_perm, policy: ClientAccessPolicy) -> None:
    """有权限时不抛出异常。"""
    policy.ensure_can_update_client(_user())


@patch.object(ClientAccessPolicy, "has_perm", return_value=False)
def test_ensure_can_update_client_raises(mock_perm, policy: ClientAccessPolicy) -> None:
    """无权限时抛出 PermissionDenied。"""
    with pytest.raises(PermissionDenied):
        policy.ensure_can_update_client(_user())


@patch.object(ClientAccessPolicy, "has_perm", return_value=True)
def test_ensure_can_delete_client_passes(mock_perm, policy: ClientAccessPolicy) -> None:
    """有权限时不抛出异常。"""
    policy.ensure_can_delete_client(_user())


@patch.object(ClientAccessPolicy, "has_perm", return_value=False)
def test_ensure_can_delete_client_raises(mock_perm, policy: ClientAccessPolicy) -> None:
    """无权限时抛出 PermissionDenied。"""
    with pytest.raises(PermissionDenied):
        policy.ensure_can_delete_client(_user())
