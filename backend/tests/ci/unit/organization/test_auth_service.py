"""组织认证服务单元测试。"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import AuthenticationError, PermissionDenied
from apps.organization.services.auth.auth_service import AuthService


@pytest.fixture
def auth_service() -> AuthService:
    return AuthService()


# ── is_first_user ──────────────────────────────────────────────────────────

@patch("apps.organization.services.auth.auth_service.Lawyer")
def test_is_first_user_true(mock_lawyer: MagicMock) -> None:
    """无用户时返回 True。"""
    mock_lawyer.objects.exists.return_value = False
    svc = AuthService()
    assert svc.is_first_user() is True


@patch("apps.organization.services.auth.auth_service.Lawyer")
def test_is_first_user_false(mock_lawyer: MagicMock) -> None:
    """有用户时返回 False。"""
    mock_lawyer.objects.exists.return_value = True
    svc = AuthService()
    assert svc.is_first_user() is False


# ── username_exists ────────────────────────────────────────────────────────

@patch("apps.organization.services.auth.auth_service.Lawyer")
def test_username_exists_true(mock_lawyer: MagicMock) -> None:
    """用户名存在返回 True。"""
    mock_lawyer.objects.filter.return_value.exists.return_value = True
    svc = AuthService()
    assert svc.username_exists("testuser") is True


@patch("apps.organization.services.auth.auth_service.Lawyer")
def test_username_exists_false(mock_lawyer: MagicMock) -> None:
    """用户名不存在返回 False。"""
    mock_lawyer.objects.filter.return_value.exists.return_value = False
    svc = AuthService()
    assert svc.username_exists("nonexistent") is False


# ── should_show_auto_register ──────────────────────────────────────────────

@patch("apps.organization.services.auth.auth_service.Lawyer")
def test_should_show_auto_register(mock_lawyer: MagicMock) -> None:
    """自动注册仅在无用户时显示。"""
    mock_lawyer.objects.exists.return_value = False
    svc = AuthService()
    assert svc.should_show_auto_register() is True


# ── login ──────────────────────────────────────────────────────────────────

@patch("apps.organization.services.auth.auth_service.login")
@patch("apps.organization.services.auth.auth_service.authenticate")
def test_login_success(mock_authenticate: MagicMock, mock_login: MagicMock) -> None:
    """登录成功。"""
    mock_user = MagicMock(spec=[])
    mock_user.__class__ = type("Lawyer", (), {})
    # Make isinstance check work
    from apps.organization.models import Lawyer
    mock_user = MagicMock(spec=Lawyer)
    mock_authenticate.return_value = mock_user
    svc = AuthService()
    mock_request = MagicMock()
    result = svc.login(mock_request, "testuser", "password")
    mock_login.assert_called_once()


@patch("apps.organization.services.auth.auth_service.authenticate")
def test_login_invalid_credentials(mock_authenticate: MagicMock) -> None:
    """认证失败抛出异常。"""
    mock_authenticate.return_value = None
    svc = AuthService()
    with pytest.raises(AuthenticationError, match="用户名或密码错误"):
        svc.login(MagicMock(), "wrong", "wrong")


# ── auto_register_superadmin ───────────────────────────────────────────────

@patch("apps.organization.services.auth.auth_service.Lawyer")
@pytest.mark.django_db
def test_auto_register_superadmin_not_first_user(mock_lawyer: MagicMock) -> None:
    """非首个用户时抛出异常。"""
    mock_lawyer.objects.exists.return_value = True
    svc = AuthService()
    with pytest.raises(PermissionDenied, match="自动注册仅在系统初始化时可用"):
        svc.auto_register_superadmin()


# ── register ───────────────────────────────────────────────────────────────

@patch("apps.organization.services.auth.auth_service.settings")
@patch("apps.organization.services.auth.auth_service.Lawyer")
@pytest.mark.django_db
def test_register_normal_user(mock_lawyer: MagicMock, mock_settings: MagicMock) -> None:
    """普通用户注册。"""
    mock_lawyer.objects.exists.return_value = True  # 非首位用户
    mock_settings.ALLOW_FIRST_USER_SUPERUSER = False
    mock_settings.DEBUG = True
    svc = AuthService()
    result = svc.register("testuser", "password123", real_name="测试")
    mock_lawyer.objects.create_user.assert_called_once()


@patch("apps.organization.services.auth.auth_service.settings")
@patch("apps.organization.services.auth.auth_service.Lawyer")
@pytest.mark.django_db
def test_register_first_user_no_token_prod(mock_lawyer: MagicMock, mock_settings: MagicMock) -> None:
    """生产环境首位用户无 token 拒绝注册。"""
    mock_lawyer.objects.exists.return_value = False  # 首位用户
    mock_settings.ALLOW_FIRST_USER_SUPERUSER = True
    mock_settings.DEBUG = False
    mock_settings.BOOTSTRAP_ADMIN_TOKEN = "secret-token"
    svc = AuthService()
    with pytest.raises(PermissionDenied, match="引导令牌"):
        svc.register("admin", "password123")


@patch("apps.organization.services.auth.auth_service.settings")
@patch("apps.organization.services.auth.auth_service.Lawyer")
@pytest.mark.django_db
def test_register_first_user_with_token_prod(mock_lawyer: MagicMock, mock_settings: MagicMock) -> None:
    """生产环境首位用户有 token 可注册。"""
    mock_lawyer.objects.exists.return_value = False
    mock_settings.ALLOW_FIRST_USER_SUPERUSER = True
    mock_settings.DEBUG = False
    mock_settings.BOOTSTRAP_ADMIN_TOKEN = "secret-token"
    svc = AuthService()
    result = svc.register("admin", "password123", bootstrap_token="secret-token")
    mock_lawyer.objects.create_user.assert_called_once()
    call_kwargs = mock_lawyer.objects.create_user.call_args[1]
    assert call_kwargs["is_superuser"] is True
