"""
认证服务模块
封装用户认证相关的业务逻辑
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import authenticate, login, logout
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import AuthenticationError
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
    ) -> RegisterResult:
        is_first_user = not Lawyer.objects.exists()
        user = Lawyer.objects.create_user(
            username=username,
            password=password,
            real_name=real_name,
            is_superuser=is_first_user,
            is_staff=is_first_user,
            is_admin=is_first_user,
            is_active=is_first_user,
        )
        return RegisterResult(user=user)
