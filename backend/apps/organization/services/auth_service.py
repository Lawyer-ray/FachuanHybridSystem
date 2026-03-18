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
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.core.exceptions import AuthenticationError, PermissionDenied
from apps.core.services.system_config_service import SystemConfigService
from apps.organization.models import Lawyer

AUTO_REGISTER_BOOTSTRAP_USED_KEY = "ADMIN_REGISTER_AUTO_BOOTSTRAP_USED"
AUTO_REGISTER_BOOTSTRAP_USERNAME = "法穿"
AUTO_REGISTER_BOOTSTRAP_PASSWORD = "1234qwer"


@dataclass
class RegisterResult:
    user: Lawyer


class AuthService:
    def __init__(self, *, config_service: SystemConfigService | None = None) -> None:
        self._config_service = config_service or SystemConfigService()

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

    def should_show_auto_register(self) -> bool:
        return self.is_first_user() and not self._is_auto_register_consumed()

    @transaction.atomic
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
        self._mark_auto_register_consumed()
        return RegisterResult(user=user)

    @transaction.atomic
    def auto_register_superadmin(self) -> RegisterResult:
        if not self.should_show_auto_register():
            raise PermissionDenied(
                message=_("自动注册仅在系统初始化时可用"),
                code="AUTO_REGISTER_UNAVAILABLE",
            )

        user = Lawyer.objects.create_user(
            username=AUTO_REGISTER_BOOTSTRAP_USERNAME,
            password=AUTO_REGISTER_BOOTSTRAP_PASSWORD,
            real_name=AUTO_REGISTER_BOOTSTRAP_USERNAME,
            is_superuser=True,
            is_staff=True,
            is_admin=True,
            is_active=True,
        )
        self._mark_auto_register_consumed()
        return RegisterResult(user=user)

    def _is_auto_register_consumed(self) -> bool:
        raw = str(self._config_service.get_value(AUTO_REGISTER_BOOTSTRAP_USED_KEY, "false") or "").strip().lower()
        return raw in {"true", "1", "yes", "y", "on"}

    def _mark_auto_register_consumed(self) -> None:
        self._config_service.set_value(
            AUTO_REGISTER_BOOTSTRAP_USED_KEY,
            "true",
            category="general",
            description="管理员注册页自动注册入口是否已被消费",
            is_secret=False,
        )
