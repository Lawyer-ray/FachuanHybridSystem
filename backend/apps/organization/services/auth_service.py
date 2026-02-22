"""
认证服务模块
封装用户认证相关的业务逻辑
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import authenticate, login, logout
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import AuthenticationError, PermissionDenied
from apps.organization.models import Lawyer


@dataclass
class RegisterResult:
    user: Lawyer


class AuthService:
    """
    认证服务 - 封装认证相关业务逻辑

    职责：
    - 用户登录认证
    - 用户登出
    - 用户注册
    - 认证失败时抛出 AuthenticationError
    """

    def login(self, request: HttpRequest, username: str, password: str) -> Lawyer:
        """
        用户登录

        Args:
            request: Django 请求对象
            username: 用户名
            password: 密码

        Returns:
            Lawyer: 认证成功的用户对象

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
        """
        用户登出

        Args:
            request: Django 请求对象
        """
        logout(request)

    def is_first_user(self) -> bool:
        """
        判断当前是否为首个用户注册

        Returns:
            bool: 如果系统中尚无用户则返回 True
        """
        return not Lawyer.objects.exists()


    def register(
        self,
        username: str,
        password: str,
        real_name: str,
        bootstrap_token: str | None = None,
    ) -> RegisterResult:
        """
        用户注册

        Args:
            username: 用户名
            password: 密码
            real_name: 真实姓名
            bootstrap_token: 引导令牌（第一个管理员注册时需要）

        Returns:
            RegisterResult: 包含 user 属性的注册结果

        Raises:
            PermissionDenied: 生产环境注册第一个用户时未提供正确的 bootstrap_token
        """
        from django.conf import settings

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
