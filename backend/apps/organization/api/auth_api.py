"""
认证 API 模块
提供用户登录、登出和当前用户信息接口
"""

from typing import cast

from django.http import HttpRequest
from ninja import Router

from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.core.security.auth import JWTOrSessionAuth
from apps.organization.schemas import (
    LawyerOut,
    LoginIn,
    LoginOut,
    PasswordResetConfirmIn,
    PasswordResetOut,
    PasswordResetRequestIn,
    PasswordResetVerifyIn,
)
from apps.organization.services import AuthService
from apps.organization.services.auth.password_reset_service import PasswordResetService

router = Router()


def _get_auth_service() -> AuthService:
    """工厂函数：获取认证服务实例"""
    return AuthService()


_auth_service = _get_auth_service()


@router.post("/login", response=LoginOut, auth=None)
@rate_limit_from_settings("AUTH")
def login_view(request: HttpRequest, payload: LoginIn) -> LoginOut:
    user = _auth_service.login(request, payload.username, payload.password)
    user_out = LawyerOut.from_orm(user)
    return LoginOut(success=True, user=user_out)


@router.post("/logout", auth=None)
def logout_view(request: HttpRequest) -> dict[str, bool]:
    _auth_service.logout(request)
    return {"success": True}


@router.get("/me", response=LawyerOut, auth=JWTOrSessionAuth())
def me_view(request: HttpRequest) -> LawyerOut:
    return LawyerOut.from_orm(request.user)


# ============================================================
# 密码重置端点
# ============================================================


@router.post("/password-reset/request", response=PasswordResetOut, auth=None)
@rate_limit_from_settings("AUTH")
def request_password_reset(request: HttpRequest, payload: PasswordResetRequestIn) -> PasswordResetOut:
    """
    请求密码重置

    发送重置链接到用户邮箱
    """
    # 参数验证
    if not payload.email or "@" not in payload.email:
        return PasswordResetOut(success=False, message="请输入有效的邮箱地址")

    # 调用服务
    success, message = PasswordResetService.request_password_reset(payload.email)

    return PasswordResetOut(success=success, message=message)


@router.post("/password-reset/verify", response=PasswordResetOut, auth=None)
@rate_limit_from_settings("AUTH")
def verify_reset_token(request: HttpRequest, payload: PasswordResetVerifyIn) -> PasswordResetOut:
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
def confirm_password_reset(request: HttpRequest, payload: PasswordResetConfirmIn) -> PasswordResetOut:
    """
    确认密码重置

    使用 token 重置密码
    """
    # 密码验证
    if len(payload.new_password) < 8:
        return PasswordResetOut(success=False, message="密码长度不能少于 8 位")

    if payload.new_password != payload.confirm_password:
        return PasswordResetOut(success=False, message="两次输入的密码不一致")

    # 调用服务
    success, message = PasswordResetService.reset_password(payload.uid, payload.token, payload.new_password)

    return PasswordResetOut(success=success, message=message)
