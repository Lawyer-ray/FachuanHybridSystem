"""
认证 API 模块
提供用户登录、登出和当前用户信息接口
"""

import logging
from typing import Any, cast

from asgiref.sync import sync_to_async
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpRequest
from ninja import Router

from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.core.security.auth import JWTOrSessionAuth
from apps.organization.models import Lawyer
from apps.organization.schemas import (
    LawyerOut,
    LoginIn,
    LoginOut,
    PasswordResetConfirmIn,
    PasswordResetOut,
    PasswordResetRequestIn,
    PasswordResetVerifyIn,
    RegisterIn,
    RegisterOut,
)
from apps.organization.services import AuthService
from apps.organization.services.auth.password_reset_service import PasswordResetService

logger = logging.getLogger("apps.organization.auth")

router = Router()


def _get_auth_service() -> AuthService:
    """工厂函数：获取认证服务实例"""
    return AuthService()


_auth_service = _get_auth_service()


def _password_policy_error(password: str | None) -> str | None:
    """按 AUTH_PASSWORD_VALIDATORS 校验密码（安全审计：密码策略统一）。

    Returns:
        校验失败时返回用户可读错误信息；通过时返回 None。
    """
    if not password:
        return "密码不能为空"
    try:
        password_validation.validate_password(password)
    except DjangoValidationError as exc:
        return "密码不符合安全要求：" + "；".join(exc.messages)
    return None


@router.post("/login", response=LoginOut, auth=None)
@rate_limit_from_settings("AUTH")
async def login_view(request: HttpRequest, payload: LoginIn) -> LoginOut:  # pragma: no cover
    def _do() -> Any:
        user = _auth_service.login(request, payload.username, payload.password)
        user_out = LawyerOut.from_orm(user)
        return LoginOut(success=True, user=user_out).model_dump()

    return cast(LoginOut, await sync_to_async(_do)())


@router.post("/logout")  # 安全审计 D-08：纳入认证，session 登出走 CSRF 校验
def logout_view(request: HttpRequest) -> dict[str, bool]:  # pragma: no cover
    _auth_service.logout(request)
    return {"success": True}


@router.post("/register", response=RegisterOut, auth=None)
@rate_limit_from_settings("AUTH")
async def register_view(request: HttpRequest, payload: RegisterIn) -> RegisterOut:  # pragma: no cover
    """
    用户注册

    首位用户自动成为管理员并触发系统初始化，后续用户需要管理员审批。
    """
    # 参数验证
    if not payload.username or len(payload.username) < 3:
        return RegisterOut(success=False, message="用户名至少3个字符")
    password_error = _password_policy_error(payload.password)
    if password_error:
        return RegisterOut(success=False, message=password_error)

    # 检查用户名是否已存在（安全审计防枚举：与登录错误同口径，模糊文案
    # 不向外部确认用户名存在性）
    if await sync_to_async(_auth_service.username_exists)(payload.username):
        return RegisterOut(success=False, message="注册信息无效或用户名已存在")

    try:

        def _do() -> Any:
            result = _auth_service.register(
                username=payload.username,
                password=payload.password,
                real_name=payload.real_name,
                phone=payload.phone,
            )
            user = result.user
            is_first = user.is_active  # 首位用户自动激活
            return RegisterOut(
                success=True,
                user=LawyerOut.from_orm(user),
                requires_approval=not is_first,
                setup_in_progress=is_first,
                message="注册成功，系统正在初始化..." if is_first else "注册成功，请等待管理员审批",
            ).model_dump()

        return cast(RegisterOut, await sync_to_async(_do)())
    except Exception:
        # 安全审计：内部异常不回显 str(e)，固定文案 + 完整堆栈进日志
        logger.exception("注册处理失败 username=%s", payload.username)
        return RegisterOut(success=False, message="注册失败，请稍后重试或联系管理员")


@router.get("/me", response=LawyerOut, auth=JWTOrSessionAuth())
def me_view(request: HttpRequest) -> LawyerOut:  # pragma: no cover
    return LawyerOut.from_orm(request.user)


# ============================================================
# 密码重置端点
# ============================================================


@router.post("/password-reset/request", response=PasswordResetOut, auth=None)
@rate_limit_from_settings("AUTH")
async def request_password_reset(
    request: HttpRequest, payload: PasswordResetRequestIn
) -> PasswordResetOut:  # pragma: no cover
    """
    请求密码重置

    发送重置链接到用户邮箱
    """
    # 参数验证
    if not payload.email or "@" not in payload.email:
        return PasswordResetOut(success=False, message="请输入有效的邮箱地址")

    # 调用服务（含邮件发送 IO）
    success, message = await sync_to_async(PasswordResetService.request_password_reset)(payload.email)

    return PasswordResetOut(success=success, message=message)


@router.post("/password-reset/verify", response=PasswordResetOut, auth=None)
@rate_limit_from_settings("AUTH")
def verify_reset_token(request: HttpRequest, payload: PasswordResetVerifyIn) -> PasswordResetOut:  # pragma: no cover
    """
    验证重置 token

    用于前端页面加载时验证链接有效性
    """
    is_valid, user, message = PasswordResetService.verify_reset_token(payload.uid, payload.token)

    return PasswordResetOut(
        success=is_valid,
        message=message,
        data={
            "is_valid": is_valid,
            "username": user.username if user else None,
        },
    )


@router.post("/password-reset/confirm", response=PasswordResetOut, auth=None)
@rate_limit_from_settings("AUTH")
def confirm_password_reset(
    request: HttpRequest, payload: PasswordResetConfirmIn
) -> PasswordResetOut:  # pragma: no cover
    """
    确认密码重置

    使用 token 重置密码
    """
    # 密码验证（安全审计：统一走 AUTH_PASSWORD_VALIDATORS，替代手写 8 位长度校验）
    password_error = _password_policy_error(payload.new_password)
    if password_error:
        return PasswordResetOut(success=False, message=password_error)

    if payload.new_password != payload.confirm_password:
        return PasswordResetOut(success=False, message="两次输入的密码不一致")

    # 调用服务
    success, message = PasswordResetService.reset_password(payload.uid, payload.token, payload.new_password)

    return PasswordResetOut(success=success, message=message)
