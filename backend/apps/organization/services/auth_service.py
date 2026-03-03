"""
认证服务模块
封装用户认证相关的业务逻辑
"""

from __future__ import annotations

from dataclasses import dataclass

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
        """
        Raises:
            PermissionDenied: 生产环境注册第一个用户时未提供正确的 bootstrap_token
        """
        is_first_user = not Lawyer.objects.exists()
        allow_first_superuser = getattr(settings, "ALLOW_FIRST_USER_SUPERUSER", False)

        if is_first_user and allow_first_superuser:
            # 生产环境需要 bootstrap token
            if not getattr(settings, "DEBUG", True):
                expected_token = getattr(settings, "BOOTSTRAP_ADMIN_TOKEN", None)
                if not bootstrap_token or bootstrap_token != expected_token:
                    raise PermissionDenied(
                        message=_("需要 Bootstrap Token 才能注册第一个管理员"),
                        code="BOOTSTRAP_FORBIDDEN",
                    )
            user = Lawyer.objects.create_user(
                username=username,
                password=password,
                real_name=real_name,
                is_superuser=True,
                is_admin=True,
                is_active=True,
            )
        else:
            user = Lawyer.objects.create_user(
                username=username,
                password=password,
                real_name=real_name,
                is_superuser=False,
                is_admin=False,
                is_active=False,
            )
        return RegisterResult(user=user)
