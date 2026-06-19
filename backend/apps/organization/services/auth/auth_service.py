"""
认证服务模块
封装用户认证相关的业务逻辑
"""

from __future__ import annotations

from dataclasses import dataclass
from hmac import compare_digest

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.http import HttpRequest

from apps.core.exceptions import AuthenticationError, PermissionDenied
from apps.organization.models import Lawyer
from apps.organization.services.setup.first_user_setup_service import FirstUserSetupService

AUTO_REGISTER_BOOTSTRAP_USERNAME = "法穿"
AUTO_REGISTER_BOOTSTRAP_PASSWORD = "1234qwer"  # pragma: allowlist secret


@dataclass
class RegisterResult:
    user: Lawyer


class AuthService:
    def __init__(self) -> None:
        pass

    def login(self, request: HttpRequest, username: str, password: str) -> Lawyer:
        """
        Raises:
            AuthenticationError: 认证失败时抛出
        """
        user = authenticate(request, username=username, password=password)
        if not user:
            raise AuthenticationError(message="用户名或密码错误", code="INVALID_CREDENTIALS")
        login(request, user)
        if not isinstance(user, Lawyer):
            raise AuthenticationError(message="用户类型错误", code="INVALID_USER_TYPE")
        return user

    def logout(self, request: HttpRequest) -> None:
        logout(request)

    def is_first_user(self) -> bool:  # pragma: no cover
        return not Lawyer.objects.exists()

    def username_exists(self, username: str) -> bool:  # pragma: no cover
        return Lawyer.objects.filter(username=username).exists()

    def should_show_auto_register(self) -> bool:
        return self.is_first_user()

    @transaction.atomic
    def register(
        self,
        username: str,
        password: str,
        real_name: str | None = None,
        phone: str | None = None,
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
                    message="首位管理员注册需要有效引导令牌",
                    code="BOOTSTRAP_FORBIDDEN",
                )

        user = Lawyer.objects.create_user(
            username=username,
            password=password,
            email=None,
            real_name=real_name,
            phone=phone,
            is_superuser=should_grant_admin,
            is_staff=should_grant_admin,
            is_admin=should_grant_admin,
            is_active=should_grant_admin,
        )

        # 首位用户注册时自动初始化系统
        if should_grant_admin:
            FirstUserSetupService().execute(user)

        return RegisterResult(user=user)

    @transaction.atomic
    def auto_register_superadmin(self) -> RegisterResult:
        if not self.should_show_auto_register():
            raise PermissionDenied(
                message="自动注册仅在系统初始化时可用",
                code="AUTO_REGISTER_UNAVAILABLE",
            )

        user = Lawyer.objects.create_user(
            username=AUTO_REGISTER_BOOTSTRAP_USERNAME,
            password=AUTO_REGISTER_BOOTSTRAP_PASSWORD,
            email=None,
            real_name=AUTO_REGISTER_BOOTSTRAP_USERNAME,
            is_superuser=True,
            is_staff=True,
            is_admin=True,
            is_active=True,
        )

        # 首位用户注册时自动初始化系统
        FirstUserSetupService().execute(user)

        return RegisterResult(user=user)
