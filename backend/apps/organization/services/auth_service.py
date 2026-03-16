"""
认证服务模块
封装用户认证相关的业务逻辑
"""

from __future__ import annotations

from dataclasses import dataclass
from hmac import compare_digest

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import AuthenticationError, PermissionDenied
from apps.organization.models import Lawyer


@dataclass
class RegisterResult:
    user: Lawyer


class AuthService:
    def login(self, request: HttpRequest, username: str, password: str) -> Lawyer:
        """
        Raises:
            AuthenticationError: 认证失败时抛出
        """
        user = authenticate(request, username=username, password=password)
        if not user:
            raise AuthenticationError(message=_("用户名或密码错误"), code="INVALID_CREDENTIALS")
        login(request, user)
        if not isinstance(user, Lawyer):
            raise AuthenticationError(message=_("用户类型错误"), code="INVALID_USER_TYPE")
        return user

    def logout(self, request: HttpRequest) -> None:
        logout(request)

    def is_first_user(self) -> bool:
        return not Lawyer.objects.exists()

    def register(
        self,
        username: str,
        password: str,
        real_name: str,
        bootstrap_token: str | None = None,
    ) -> RegisterResult:
        is_first_user = not Lawyer.objects.exists()
        allow_first_superuser = bool(getattr(settings, "ALLOW_FIRST_USER_SUPERUSER", False))
        should_grant_admin = is_first_user and allow_first_superuser

        # Production requires an explicit bootstrap token before granting first-user admin.
        if should_grant_admin and not bool(getattr(settings, "DEBUG", False)):
            expected_token = str(getattr(settings, "BOOTSTRAP_ADMIN_TOKEN", "") or "").strip()
            if not expected_token or not bootstrap_token or not compare_digest(str(bootstrap_token), expected_token):
                raise PermissionDenied(
                    message=_("首位管理员注册需要有效引导令牌"),
                    code="BOOTSTRAP_FORBIDDEN",
                )

        user = Lawyer.objects.create_user(
            username=username,
            password=password,
            real_name=real_name,
            is_superuser=should_grant_admin,
            is_staff=should_grant_admin,
            is_admin=should_grant_admin,
            is_active=should_grant_admin,
        )
        return RegisterResult(user=user)
