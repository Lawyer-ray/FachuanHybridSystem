"""Tests for organization/views.py (missing: 36 lines).

Covers: register view POST branches (auto_register, form valid, form invalid),
register GET, AuthLoginView.get_context_data, ALLOW_ADMIN_REGISTER gate,
AuthLoginView staff 表单与 admin 登录限流（安全审计）。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client, RequestFactory, override_settings

from apps.organization.models import Lawyer
from apps.organization.views import AuthLoginView, register


@pytest.fixture
def rf() -> RequestFactory:
    return RequestFactory()


class TestRegisterGet:
    @override_settings(ALLOW_ADMIN_REGISTER=True)
    def test_get_renders_form(self, rf: RequestFactory) -> None:
        request = rf.get("/register/")
        with patch("apps.organization.views._auth_service") as mock_svc, patch(
            "apps.organization.views.render"
        ) as mock_render:
            mock_svc.is_first_user.return_value = False
            mock_svc.should_show_auto_register.return_value = False
            mock_render.return_value = MagicMock(status_code=200)
            response = register(request)
            assert response.status_code == 200
            # GET 渲染登录/注册页并注入注册上下文
            mock_render.assert_called_once()
            args, _kwargs = mock_render.call_args
            assert args[1] == "admin/login.html"
            assert args[2]["title"] == "用户注册"
            assert args[2]["show_register"] is True
            assert args[2]["show_auto_register"] is False


class TestRegisterGate:
    """ALLOW_ADMIN_REGISTER（默认 False）接线：表单注册入口直接拒绝。"""

    @override_settings(ALLOW_ADMIN_REGISTER=False)
    def test_get_rejected_when_disabled(self, rf: RequestFactory) -> None:
        request = rf.get("/register/")
        with (
            patch("apps.organization.views._auth_service") as mock_svc,
            patch("apps.organization.views.messages") as mock_messages,
            patch("apps.organization.views.redirect") as mock_redirect,
            patch("apps.organization.views.render") as mock_render,
        ):
            mock_svc.is_first_user.return_value = False
            mock_svc.should_show_auto_register.return_value = False
            response = register(request)
            # 不渲染注册表单，直接提示并跳转登录页
            mock_render.assert_not_called()
            mock_messages.error.assert_called_once()
            mock_redirect.assert_called_once_with("admin:login")

    @override_settings(ALLOW_ADMIN_REGISTER=False)
    def test_form_post_rejected_when_disabled(self, rf: RequestFactory) -> None:
        request = rf.post("/register/", {"username": "someone", "password1": "testpass123", "password2": "testpass123"})
        with (
            patch("apps.organization.views._auth_service") as mock_svc,
            patch("apps.organization.views.messages") as mock_messages,
            patch("apps.organization.views.redirect") as mock_redirect,
            patch("apps.organization.views.LawyerRegistrationForm") as MockForm,
        ):
            mock_svc.is_first_user.return_value = False
            mock_svc.should_show_auto_register.return_value = False
            response = register(request)
            # 表单注册被拒绝，且未实例化注册表单、未调用注册服务
            MockForm.assert_not_called()
            mock_svc.register.assert_not_called()
            mock_messages.error.assert_called_once()
            mock_redirect.assert_called_once_with("admin:login")


class TestRegisterPostAutoRegister:
    """auto_register（BOOTSTRAP 首用户引导）分支不受 ALLOW_ADMIN_REGISTER 影响。"""

    @override_settings(ALLOW_ADMIN_REGISTER=False, DEBUG=False, BOOTSTRAP_ADMIN_TOKEN="tok-123")
    def test_auto_register_success(self, rf: RequestFactory) -> None:
        """生产口径下需携带 BOOTSTRAP_ADMIN_TOKEN（安全审计 C-02）。"""
        request = rf.post("/register/", {"action": "auto_register", "bootstrap_token": "tok-123"})
        with (
            patch("apps.organization.views._auth_service") as mock_svc,
            patch("apps.organization.views.login") as mock_login,
            patch("apps.organization.views.messages") as mock_messages,
            patch("apps.organization.views.redirect") as mock_redirect,
        ):
            mock_svc.is_first_user.return_value = True
            mock_svc.should_show_auto_register.return_value = True
            mock_user = MagicMock()
            mock_user.real_name = "Admin"
            mock_svc.auto_register_superadmin.return_value = SimpleNamespace(user=mock_user)
            mock_redirect.return_value = MagicMock(status_code=302)
            response = register(request)
            mock_login.assert_called_once()

    @override_settings(ALLOW_ADMIN_REGISTER=False, DEBUG=False, BOOTSTRAP_ADMIN_TOKEN="tok-123")
    def test_auto_register_without_token_rejected(self, rf: RequestFactory) -> None:
        """生产口径下无令牌的自动注册被拒绝（安全审计 C-02）。"""
        request = rf.post("/register/", {"action": "auto_register"})
        with (
            patch("apps.organization.views._auth_service") as mock_svc,
            patch("apps.organization.views.login") as mock_login,
            patch("apps.organization.views.messages") as mock_messages,
            patch("apps.organization.views.redirect") as mock_redirect,
        ):
            mock_svc.should_show_auto_register.return_value = True
            mock_redirect.return_value = MagicMock(status_code=302)
            response = register(request)
            mock_login.assert_not_called()
            mock_messages.error.assert_called_once()
            mock_svc.auto_register_superadmin.assert_not_called()

    @override_settings(ALLOW_ADMIN_REGISTER=False)
    def test_auto_register_exception(self, rf: RequestFactory) -> None:
        request = rf.post("/register/", {"action": "auto_register"})
        with (
            patch("apps.organization.views._auth_service") as mock_svc,
            patch("apps.organization.views.messages") as mock_messages,
            patch("apps.organization.views.redirect") as mock_redirect,
        ):
            mock_svc.is_first_user.return_value = True
            mock_svc.should_show_auto_register.return_value = True
            mock_svc.auto_register_superadmin.side_effect = Exception("error")
            mock_redirect.return_value = MagicMock(status_code=302)
            response = register(request)
            mock_messages.error.assert_called()


class TestRegisterPostForm:
    @override_settings(ALLOW_ADMIN_REGISTER=True)
    def test_form_valid_first_user_admin(self, rf: RequestFactory) -> None:
        request = rf.post(
            "/register/",
            {
                "username": "admin",
                "password1": "testpass123",
                "password2": "testpass123",
            },
        )
        with (
            patch("apps.organization.views._auth_service") as mock_svc,
            patch("apps.organization.views.login") as mock_login,
            patch("apps.organization.views.messages") as mock_messages,
            patch("apps.organization.views.redirect") as mock_redirect,
            patch("apps.organization.views.LawyerRegistrationForm") as MockForm,
        ):
            mock_svc.is_first_user.return_value = True
            mock_svc.should_show_auto_register.return_value = True
            form_instance = MockForm.return_value
            form_instance.is_valid.return_value = True
            form_instance.cleaned_data = {"username": "admin", "password1": "testpass123"}
            mock_user = MagicMock()
            mock_user.is_admin = True
            mock_user.real_name = "admin"
            mock_svc.register.return_value = SimpleNamespace(user=mock_user)
            mock_redirect.return_value = MagicMock(status_code=302)
            response = register(request)
            mock_login.assert_called_once()

    @override_settings(ALLOW_ADMIN_REGISTER=True)
    def test_form_valid_non_admin(self, rf: RequestFactory) -> None:
        request = rf.post(
            "/register/",
            {
                "username": "user",
                "password1": "testpass123",
                "password2": "testpass123",
            },
        )
        with (
            patch("apps.organization.views._auth_service") as mock_svc,
            patch("apps.organization.views.login") as mock_login,
            patch("apps.organization.views.messages") as mock_messages,
            patch("apps.organization.views.redirect") as mock_redirect,
            patch("apps.organization.views.LawyerRegistrationForm") as MockForm,
        ):
            mock_svc.is_first_user.return_value = False
            mock_svc.should_show_auto_register.return_value = False
            form_instance = MockForm.return_value
            form_instance.is_valid.return_value = True
            form_instance.cleaned_data = {"username": "user", "password1": "testpass123"}
            mock_user = MagicMock()
            mock_user.is_admin = False
            mock_svc.register.return_value = SimpleNamespace(user=mock_user)
            mock_redirect.return_value = MagicMock(status_code=302)
            response = register(request)
            mock_login.assert_not_called()

    @override_settings(ALLOW_ADMIN_REGISTER=True)
    def test_form_valid_register_exception(self, rf: RequestFactory) -> None:
        request = rf.post(
            "/register/",
            {
                "username": "user",
                "password1": "testpass123",
                "password2": "testpass123",
            },
        )
        with (
            patch("apps.organization.views._auth_service") as mock_svc,
            patch("apps.organization.views.messages") as mock_messages,
            patch("apps.organization.views.redirect") as mock_redirect,
            patch("apps.organization.views.LawyerRegistrationForm") as MockForm,
        ):
            mock_svc.is_first_user.return_value = False
            mock_svc.should_show_auto_register.return_value = False
            form_instance = MockForm.return_value
            form_instance.is_valid.return_value = True
            form_instance.cleaned_data = {"username": "user", "password1": "testpass123"}
            mock_svc.register.side_effect = Exception("register error")
            mock_redirect.return_value = MagicMock(status_code=302)
            response = register(request)
            mock_messages.error.assert_called()

    @override_settings(ALLOW_ADMIN_REGISTER=True)
    def test_form_invalid(self, rf: RequestFactory) -> None:
        request = rf.post(
            "/register/",
            {
                "username": "",
                "password1": "",
                "password2": "",
            },
        )
        with (
            patch("apps.organization.views._auth_service") as mock_svc,
            patch("apps.organization.views.LawyerRegistrationForm") as MockForm,
            patch("apps.organization.views.render") as mock_render,
        ):
            mock_svc.is_first_user.return_value = False
            mock_svc.should_show_auto_register.return_value = False
            form_instance = MockForm.return_value
            form_instance.is_valid.return_value = False
            mock_render.return_value = MagicMock(status_code=200)
            response = register(request)
            assert response.status_code == 200
            # 无效表单应带同一 form 实例回到注册页
            mock_render.assert_called_once()
            args, _kwargs = mock_render.call_args
            assert args[1] == "admin/login.html"
            assert args[2]["reg_form"] is form_instance
            # 未尝试注册
            mock_svc.register.assert_not_called()
            assert response.status_code == 200


class TestAdminLoginFormAndRateLimit:
    """安全审计：/admin/login/ 补 staff 前置校验 + AUTH 限流。"""

    def test_login_view_uses_admin_authentication_form(self) -> None:
        """AuthLoginView 必须用 AdminAuthenticationForm（拒绝非 is_staff）。"""
        from django.contrib.admin.forms import AdminAuthenticationForm

        assert AuthLoginView.authentication_form is AdminAuthenticationForm

    @pytest.mark.django_db
    def test_admin_login_rejects_non_staff(self, client: Client, db: None) -> None:
        """密码正确的非 staff 用户在 admin 登录表单也不得通过（防密码预言机）。"""
        from django.core.cache import cache

        cache.clear()
        Lawyer.objects.create_user(username="plainuser", password="goodpass123")  # pragma: allowlist secret

        resp = client.post(
            "/admin/login/",
            {"username": "plainuser", "password": "goodpass123", "this_is_the_login_form": "1"},  # pragma: allowlist secret
        )
        assert resp.status_code == 200  # 表单校验失败，重新渲染而非登录跳转
        # 表单须带错误信息，且未建立认证会话（防密码预言机）
        assert resp.context["form"].errors
        assert client.session.get("_auth_user_id") is None

    @pytest.mark.django_db
    def test_admin_login_allows_staff(self, client: Client, db: None) -> None:
        from django.core.cache import cache

        cache.clear()
        Lawyer.objects.create_user(username="staffuser", password="goodpass123", is_staff=True)  # pragma: allowlist secret

        resp = client.post(
            "/admin/login/",
            {"username": "staffuser", "password": "goodpass123", "this_is_the_login_form": "1"},  # pragma: allowlist secret
        )
        assert resp.status_code == 302
        # 登录成功须建立会话并跳往 admin 首页
        assert client.session.get("_auth_user_id") is not None
        assert resp["Location"] == "/admin/"

    @pytest.mark.django_db
    def test_admin_login_rate_limited(self, client: Client, db: None) -> None:
        """超过 AUTH 限流阈值后返回 429（普通 Django 视图下不冒泡 500）。"""
        from django.conf import settings as dj_settings
        from django.core.cache import cache

        cache.clear()
        limit = int((getattr(dj_settings, "RATE_LIMIT", {}) or {}).get("AUTH_REQUESTS", 5))

        with patch("apps.core.infrastructure.throttling.time.time", return_value=1_700_000_000):
            for _ in range(limit):
                resp = client.post(
                    "/admin/login/",
                    {"username": "nobody", "password": "wrongpass123"},  # pragma: allowlist secret
                )
                assert resp.status_code == 200, resp.status_code
            limited = client.post(
                "/admin/login/",
                {"username": "nobody", "password": "wrongpass123"},  # pragma: allowlist secret
            )
        assert limited.status_code == 429
        assert "Retry-After" in limited
