"""通行密钥（Passkey/WebAuthn）端点 — 挂载于 /api/v1/social/passkey/*。

沿用 social_auth_api 的约定：全部走 Ninja（operation 默认 csrf_exempt），
业务失败返回 success=False + message（HTTP 200），不抛 HTTP 异常。

挑战放在 Django session，前端请求必须带同源 cookie（与社交登录流程同一
约束，vite 代理同源转发天然满足）。login/* 无需登录态（auth=None），
register/* 与凭据管理要求 JWTOrSessionAuth。

同步实现：session 懒加载是同步 ORM，同步 op（线程池执行）回避了整类
async 上下文访问 session 的坑，ceremony 低频场景没有性能顾虑。
ORM 只在 Service 层（四层架构门禁），本文件不 import Model。
"""

from __future__ import annotations

import logging

from django.http import HttpRequest
from ninja import Router

from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.core.security.auth import JWTOrSessionAuth
from apps.organization.models import Lawyer
from apps.social_auth.services import PasskeyError
from apps.social_auth.services.passkey_service import (
    build_login_options,
    build_registration_options,
    delete_user_credential,
    list_user_credentials,
    rename_user_credential,
    verify_login,
    verify_registration,
)

from .passkey_schemas import (
    PasskeyAssertionIn,
    PasskeyCredentialOut,
    PasskeyCredentialsOut,
    PasskeyMutationOut,
    PasskeyOptionsOut,
    PasskeyRegisterVerifyIn,
    PasskeyRegisterVerifyOut,
    PasskeyRenameIn,
)
from .social_auth_schemas import TokenExchangeOut

logger = logging.getLogger(__name__)

router = Router()


# ============================================================
# 凭据管理（个人设置 → 账号绑定 → 通行密钥）
# ============================================================


@router.get("/credentials", response=PasskeyCredentialsOut, auth=JWTOrSessionAuth())
def list_credentials(request: HttpRequest) -> PasskeyCredentialsOut:
    """列出当前用户已注册的通行密钥。"""
    user: Lawyer = request.auth  # type: ignore[attr-defined]
    rows = [
        PasskeyCredentialOut(
            id=row.id,
            name=row.name,
            rp_id=row.rp_id,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
        )
        for row in list_user_credentials(user)
    ]
    return PasskeyCredentialsOut(credentials=rows)


@router.patch("/credentials/{credential_id}", response=PasskeyMutationOut, auth=JWTOrSessionAuth())
def rename_credential(
    request: HttpRequest,
    credential_id: int,
    payload: PasskeyRenameIn,
) -> PasskeyMutationOut:
    """重命名通行密钥（只允许操作自己的凭据，跨用户的 id 一律查不到）。"""
    user: Lawyer = request.auth  # type: ignore[attr-defined]
    name = payload.name.strip()[:100]
    if not name:
        return PasskeyMutationOut(success=False, message="名称不能为空")
    row = rename_user_credential(user, credential_id, name)
    if row is None:
        return PasskeyMutationOut(success=False, message="未找到该通行密钥")
    return PasskeyMutationOut(success=True)


@router.delete("/credentials/{credential_id}", response=PasskeyMutationOut, auth=JWTOrSessionAuth())
def delete_credential(request: HttpRequest, credential_id: int) -> PasskeyMutationOut:
    """删除通行密钥 = 吊销：该设备之后无法再登录本账号。"""
    user: Lawyer = request.auth  # type: ignore[attr-defined]
    if not delete_user_credential(user, credential_id):
        return PasskeyMutationOut(success=False, message="未找到该通行密钥")
    logger.info("通行密钥已删除 user=%s credential_id=%s", user.id, credential_id)
    return PasskeyMutationOut(success=True)


# ============================================================
# 登录 ceremony（无需登录态）
# ============================================================


@router.post("/login/options", response=PasskeyOptionsOut, auth=None)
@rate_limit_from_settings("AUTH")
def login_options(request: HttpRequest) -> PasskeyOptionsOut:
    """下发登录挑战（可发现凭据，浏览器自行列出本域全部通行密钥）。"""
    try:
        options = build_login_options(request)
    except PasskeyError as exc:
        return PasskeyOptionsOut(success=False, message=str(exc))
    return PasskeyOptionsOut(success=True, public_key=options["public_key"])


@router.post("/login/verify", response=TokenExchangeOut, auth=None)
@rate_limit_from_settings("AUTH")
def login_verify(request: HttpRequest, payload: PasskeyAssertionIn) -> TokenExchangeOut:
    """校验登录断言并签发 JWT（响应结构与 /social/token-exchange 完全一致）。"""
    try:
        result = verify_login(request, payload.credential)
    except PasskeyError as exc:
        return TokenExchangeOut(success=False, message=str(exc))
    if not result.success:
        return TokenExchangeOut(success=False, message=result.message)
    return TokenExchangeOut(
        success=True,
        access=result.access,
        refresh=result.refresh,
        user_id=result.user_id,
        username=result.username,
    )


# ============================================================
# 注册 ceremony（需登录：给当前账号添加一把新密钥）
# ============================================================


@router.post("/register/options", response=PasskeyOptionsOut, auth=JWTOrSessionAuth())
@rate_limit_from_settings("AUTH")
def register_options(request: HttpRequest) -> PasskeyOptionsOut:
    """下发注册挑战（excludeCredentials 已含本用户全部已有凭据）。"""
    user: Lawyer = request.auth  # type: ignore[attr-defined]
    try:
        options = build_registration_options(request, user)
    except PasskeyError as exc:
        return PasskeyOptionsOut(success=False, message=str(exc))
    return PasskeyOptionsOut(success=True, public_key=options["public_key"])


@router.post("/register/verify", response=PasskeyRegisterVerifyOut, auth=JWTOrSessionAuth())
@rate_limit_from_settings("AUTH")
def register_verify(request: HttpRequest, payload: PasskeyRegisterVerifyIn) -> PasskeyRegisterVerifyOut:
    """校验注册响应并落库，返回新凭据的展示信息。"""
    user: Lawyer = request.auth  # type: ignore[attr-defined]
    try:
        row = verify_registration(request, user, name=payload.name, credential=payload.credential)
    except PasskeyError as exc:
        return PasskeyRegisterVerifyOut(success=False, message=str(exc))
    return PasskeyRegisterVerifyOut(
        success=True,
        credential=PasskeyCredentialOut(
            id=row.id,
            name=row.name,
            rp_id=row.rp_id,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
        ),
    )
