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
# 安全审计（2026Q4）：此处原为硬编码口令 "1234qwer"，任何人可在 DEBUG 实例上
# 免令牌调用 auto_register 抢占超管（口令同时写在公开仓库源码中）。现改为从
# settings.AUTO_REGISTER_BOOTSTRAP_PASSWORD（环境变量注入）读取；未配置时
# auto_register_superadmin 直接拒绝，不再回退到源码内的可用口令。


@dataclass
class RegisterResult:
    user: Lawyer
    # 本次注册是否吃到了「首位用户」名额（系统此前没有任何已激活账号）
    is_first_user: bool = False
    # 本次注册是否被授予律所管理员（首位用户无条件获得）
    granted_admin: bool = False


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
        # 先验型再建会话：避免给非 Lawyer 用户建出半截会话后才报错
        if not isinstance(user, Lawyer):
            raise AuthenticationError(message="用户类型错误", code="INVALID_USER_TYPE")
        login(request, user)
        return user

    def logout(self, request: HttpRequest) -> None:
        logout(request)

    def is_first_user(self) -> bool:  # pragma: no cover
        """系统是否还没有「可用」账号。

        2026-11-25 修正：原实现按「表里有没有 Lawyer 行」判定。历史注册会留下
        is_active=False 的孤儿行（注册成功但无人审批），于是首位名额被这一行永久占死，
        登录页「快速体验」与 /admin/register/ 的 auto_register 分支也一起关死——
        系统再也无法通过注册自举。改为按「有没有已激活账号」判定，那才是
        「这个系统还没有任何人能登录」的真实语义。
        """
        return not Lawyer.objects.filter(is_active=True).exists()

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
        """注册账号。

        产品语义（2026-11-25 恢复）：
        - **首位用户**（系统尚无已激活账号）注册即成为律所管理员，并触发系统初始化；
        - **后续用户**注册后为待审批状态（is_active=False），由管理员审批激活
          （见 ``apps.organization.services.lawyer.approval.LawyerApprovalService``）。

        为什么要拆开：``is_active`` 原先绑定在 ``ALLOW_FIRST_USER_SUPERUSER`` 上，
        而该开关默认 False，于是**任何**注册产出的账号都永远登不上，响应却谎称
        「请等待管理员审批」——而系统里根本没有审批入口。现在把
        「激活 + 律所管理员」与「平台超级管理员」解耦：

        - ``is_admin`` / ``is_staff`` / ``is_active`` ← 首位用户无条件获得（本方法负责）；
        - ``is_superuser`` ← 仍受 ``ALLOW_FIRST_USER_SUPERUSER`` 与 ``BOOTSTRAP_ADMIN_TOKEN``
          约束（安全审计 C-02：防公开实例上零凭证抢占超管）。
        """
        is_first_user = self.is_first_user()

        grant_superuser = is_first_user and bool(getattr(settings, "ALLOW_FIRST_USER_SUPERUSER", False))
        # 部署方配置了引导令牌就必须提供；未配置视为「不要求令牌」的自托管口径
        expected_token = str(getattr(settings, "BOOTSTRAP_ADMIN_TOKEN", "") or "").strip()
        if grant_superuser and expected_token and not bool(getattr(settings, "DEBUG", False)):
            if not bootstrap_token or not compare_digest(str(bootstrap_token), expected_token):
                raise PermissionDenied(
                    message="首位管理员注册需要有效引导令牌",
                    code="BOOTSTRAP_FORBIDDEN",
                )

        # 首位用户 = 律所管理员：必须激活，否则系统将不存在任何可登录账号
        grant_admin = is_first_user

        # 注意：real_name 列是 NOT NULL + default=''，模型层不会把 None 转成 ''。
        # 显式传 None（注册表单不填真实姓名就是这个情况）会直接 IntegrityError，
        # 再被 API 层的 except 吞成「注册失败，请稍后重试」——用户完全无从下手。
        user = Lawyer.objects.create_user(
            username=username,
            password=password,
            email=None,
            real_name=real_name or "",
            phone=phone,
            is_superuser=grant_superuser,
            is_staff=grant_admin,
            is_admin=grant_admin,
            is_active=grant_admin,
        )

        # 首位用户注册时自动初始化系统（默认律所 / 团队 / SystemConfig / 文书模板）
        if grant_admin:
            FirstUserSetupService().execute(user)

        return RegisterResult(user=user, is_first_user=is_first_user, granted_admin=grant_admin)

    @transaction.atomic
    def auto_register_superadmin(self) -> RegisterResult:
        """首用户引导：自动创建超级管理员。

        安全审计（2026Q4）：原实现只检查「系统无任何用户」，既不受
        ALLOW_FIRST_USER_SUPERUSER 约束，口令又硬编码在源码中，导致 DEBUG
        实例上任何人可零凭证接管超管。现按 register() 同口径补齐两道闸门：

        1. ALLOW_FIRST_USER_SUPERUSER 必须显式开启（默认 False，fail-closed）；
        2. 口令必须由 settings.AUTO_REGISTER_BOOTSTRAP_PASSWORD 注入，
           源码不再保留任何可用口令。
        """
        if not self.should_show_auto_register():
            raise PermissionDenied(
                message="自动注册仅在系统初始化时可用",
                code="AUTO_REGISTER_UNAVAILABLE",
            )

        if not bool(getattr(settings, "ALLOW_FIRST_USER_SUPERUSER", False)):
            raise PermissionDenied(
                message="自动注册未开放（ALLOW_FIRST_USER_SUPERUSER 未启用）",
                code="AUTO_REGISTER_DISABLED",
            )

        bootstrap_password = str(getattr(settings, "AUTO_REGISTER_BOOTSTRAP_PASSWORD", "") or "").strip()
        if not bootstrap_password:
            raise PermissionDenied(
                message="自动注册需要配置 AUTO_REGISTER_BOOTSTRAP_PASSWORD",
                code="AUTO_REGISTER_PASSWORD_MISSING",
            )

        user = Lawyer.objects.create_user(
            username=AUTO_REGISTER_BOOTSTRAP_USERNAME,
            password=bootstrap_password,
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
