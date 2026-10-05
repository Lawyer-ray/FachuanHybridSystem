"""通行密钥（Passkey/WebAuthn）注册与登录 ceremony。

安全设计：
- 挑战存 Django session、读即删（单次使用）+ 300s TTL；session key 与 OAuth
  流程的 ``oauth`` 单槽隔离，同一浏览器并行的社交登录互不踩踏。
- rp_id 从页面 Origin 推导；Origin 必须命中 CORS_ALLOWED_ORIGINS /
  CSRF_TRUSTED_ORIGINS / FRONTEND_BASE_URL 白名单（与 Django 自身的 CSRF
  信任面同口径），DEBUG 下额外放行回环地址任意端口——vite strictPort=false
  被占用时会自动换端口，按端口枚举白名单会误伤。
- 登录用可发现凭据（allowCredentials 为空），浏览器弹出本域全部通行密钥，
  服务端不提供用户列表，无用户枚举面。
- sign_count 必须单调不减（计数器型认证器），回退即判定凭据被克隆并拒绝。
- token 铸造与 token_exchange_service 同口径（bind_password_claim）：
  改密后签发的 refresh 一并失效；通行密钥本身不含秘密，无密码可泄露。

同步实现说明：ceremony 是低频的人机交互（每次数秒的 Touch ID 节奏），
Ninja 同步 op 跑线程池完全够用；坚持同步还避免了「Django session 懒加载
是同步 ORM」在异步上下文里的整类坑（社交登录的 Django View 曾为此踩过）。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from django.conf import settings
from django.db import IntegrityError
from django.http import HttpRequest
from django.utils import timezone
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from apps.social_auth.models import PasskeyCredential
from apps.social_auth.services.token_exchange_service import TokenExchangeResult

if TYPE_CHECKING:
    from apps.organization.models import Lawyer

logger = logging.getLogger(__name__)

RP_NAME = "法穿 SI Copilot"
CHALLENGE_TTL_SECONDS = 300
_REGISTER_KEY = "webauthn_register"
_LOGIN_KEY = "webauthn_login"
# WebAuthn 安全上下文豁免：http 仅回环可用（W3C Secure Contexts 规范）
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class PasskeyError(Exception):
    """ceremony 失败；API 层捕获后转 success=False + message 响应。"""


@dataclass
class RpContext:
    """一次 ceremony 生效的 WebAuthn 环境。"""

    rp_id: str
    origin: str


def _origin_parts(origin: str) -> tuple[str, str, int | None]:
    """拆出 (scheme, hostname, port)；http:80 / https:443 默认端口归一为 None。"""
    parts = urlsplit(origin.strip())
    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError:
        port = None
    if scheme == "http" and port == 80:
        port = None
    if scheme == "https" and port == 443:
        port = None
    return scheme, hostname, port


def _canonical_origin(scheme: str, hostname: str, port: int | None) -> str:
    host = f"[{hostname}]" if ":" in hostname else hostname
    suffix = f":{port}" if port else ""
    return f"{scheme}://{host}{suffix}"


def resolve_rp_context(origin: str) -> RpContext:
    """校验页面 Origin 并推导 rp_id；不通过抛 PasskeyError。

    DEBUG 下回环地址任意端口直通（本地开发端口会漂移）；其余 origin 一律
    逐字比对白名单，且 http 仅回环可用（WebAuthn 要求安全上下文）。
    """
    scheme, hostname, port = _origin_parts(origin)
    if scheme not in ("http", "https") or not hostname:
        raise PasskeyError("Origin 非法，无法校验通行密钥环境")
    if scheme == "http" and hostname not in _LOOPBACK_HOSTS:
        raise PasskeyError("通行密钥要求 HTTPS 或 localhost 环境")

    if settings.DEBUG and hostname in _LOOPBACK_HOSTS:
        return RpContext(rp_id=hostname, origin=_canonical_origin(scheme, hostname, port))

    allowlist = {
        *getattr(settings, "CORS_ALLOWED_ORIGINS", []),
        *getattr(settings, "CSRF_TRUSTED_ORIGINS", []),
        getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5090"),
    }
    for candidate in allowlist:
        if not candidate:
            continue
        c_scheme, c_host, c_port = _origin_parts(str(candidate))
        if (scheme, hostname, port) == (c_scheme, c_host, c_port):
            return RpContext(rp_id=hostname, origin=_canonical_origin(scheme, hostname, port))
    raise PasskeyError("当前访问域名未加入通行密钥白名单，请联系管理员")


def _same_environment(stored: dict[str, Any], ctx: RpContext) -> bool:
    return ctx.rp_id == stored.get("rp_id") and ctx.origin == stored.get("origin")


def _store_challenge(
    request: HttpRequest,
    key: str,
    ctx: RpContext,
    challenge: bytes,
    user_id: int | None,
) -> None:
    request.session[key] = {
        "challenge": bytes_to_base64url(challenge),
        "rp_id": ctx.rp_id,
        "origin": ctx.origin,
        "user_id": user_id,
        "created_at": time.time(),
    }


def _pop_challenge(request: HttpRequest, key: str) -> dict[str, Any]:
    """取出挑战（读即删：单次使用，重放直接失败）。"""
    stored = request.session.pop(key, None)
    if not isinstance(stored, dict):
        raise PasskeyError("通行密钥会话已过期，请重新操作")
    if time.time() - float(stored.get("created_at") or 0) > CHALLENGE_TTL_SECONDS:
        raise PasskeyError("通行密钥会话已过期，请重新操作")
    return stored


def build_registration_options(request: HttpRequest, user: Lawyer) -> dict[str, Any]:
    """生成注册选项并把挑战存进 session。"""
    ctx = resolve_rp_context(request.headers.get("Origin", ""))
    exclude = [
        PublicKeyCredentialDescriptor(id=base64url_to_bytes(row.credential_id))
        for row in PasskeyCredential.objects.filter(user=user)
    ]
    options = generate_registration_options(
        rp_id=ctx.rp_id,
        rp_name=RP_NAME,
        user_id=str(user.id).encode(),
        user_name=user.username,
        user_display_name=user.real_name or user.username,
        exclude_credentials=exclude,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    _store_challenge(request, _REGISTER_KEY, ctx, options.challenge, user.id)
    return {"public_key": json.loads(options_to_json(options))}


def verify_registration(
    request: HttpRequest,
    user: Lawyer,
    *,
    name: str,
    credential: dict[str, Any],
) -> PasskeyCredential:
    """校验注册响应并落库。挑战已在上一步绑定用户，防止跨账号重放。"""
    stored = _pop_challenge(request, _REGISTER_KEY)
    if stored.get("user_id") != user.id:
        raise PasskeyError("注册会话与当前用户不匹配，请重新操作")
    ctx = resolve_rp_context(request.headers.get("Origin", ""))
    if not _same_environment(stored, ctx):
        raise PasskeyError("访问环境发生变化，请重新操作")

    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(str(stored["challenge"])),
            expected_rp_id=str(stored["rp_id"]),
            expected_origin=str(stored["origin"]),
            require_user_verification=False,
        )
    except (WebAuthnException, ValueError) as exc:
        logger.info("通行密钥注册校验失败 user=%s: %s", user.id, exc)
        raise PasskeyError("通行密钥校验失败，请重试") from None

    try:
        return PasskeyCredential.objects.create(
            user=user,
            name=name.strip()[:100] or "通行密钥",
            credential_id=bytes_to_base64url(verified.credential_id),
            public_key=bytes_to_base64url(verified.credential_public_key),
            sign_count=verified.sign_count,
            rp_id=str(stored["rp_id"]),
            backed_up=verified.credential_backed_up,
        )
    except IntegrityError:
        raise PasskeyError("该通行密钥已经注册过") from None


def build_login_options(request: HttpRequest) -> dict[str, Any]:
    """生成登录选项：allowCredentials 为空 = 可发现凭据，浏览器自行列出本域密钥。"""
    ctx = resolve_rp_context(request.headers.get("Origin", ""))
    options = generate_authentication_options(rp_id=ctx.rp_id)
    _store_challenge(request, _LOGIN_KEY, ctx, options.challenge, user_id=None)
    return {"public_key": json.loads(options_to_json(options))}


def verify_login(request: HttpRequest, credential: dict[str, Any]) -> TokenExchangeResult:
    """校验登录断言 → 命中凭据 → 铸 token。失败统一泛化文案，不区分具体原因。"""
    stored = _pop_challenge(request, _LOGIN_KEY)
    ctx = resolve_rp_context(request.headers.get("Origin", ""))
    if not _same_environment(stored, ctx):
        raise PasskeyError("访问环境发生变化，请重新操作")

    credential_id = str(credential.get("id") or credential.get("rawId") or "")
    if not credential_id:
        raise PasskeyError("通行密钥校验失败，请重试")
    try:
        row = PasskeyCredential.objects.select_related("user").get(credential_id=credential_id)
    except PasskeyCredential.DoesNotExist:
        raise PasskeyError("未找到匹配的通行密钥") from None

    user = row.user
    if not user.is_active:
        raise PasskeyError("账号未激活，请联系管理员")

    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(str(stored["challenge"])),
            expected_rp_id=str(stored["rp_id"]),
            expected_origin=str(stored["origin"]),
            credential_public_key=base64url_to_bytes(row.public_key),
            credential_current_sign_count=row.sign_count,
            require_user_verification=False,
        )
    except (WebAuthnException, ValueError) as exc:
        logger.info("通行密钥登录校验失败 credential=%s…: %s", row.credential_id[:16], exc)
        raise PasskeyError("通行密钥校验失败，请重试") from None

    # 计数器型认证器：new_sign_count 必须严格递增；恒为 0 的免计数认证器跳过
    if verified.new_sign_count or row.sign_count:
        if verified.new_sign_count <= row.sign_count:
            logger.warning(
                "通行密钥签名计数回退（疑似克隆）credential=%s… %s → %s",
                row.credential_id[:16],
                row.sign_count,
                verified.new_sign_count,
            )
            raise PasskeyError("通行密钥校验失败，请重试")
    PasskeyCredential.objects.filter(pk=row.pk).update(
        sign_count=verified.new_sign_count,
        last_used_at=timezone.now(),
    )

    from ninja_jwt.tokens import RefreshToken

    from apps.core.security.jwt_password_binding import bind_password_claim

    # 与 token_exchange_service 同口径：refresh 绑定密码指纹，改密即失效
    refresh = bind_password_claim(RefreshToken.for_user(user), user)  # type: ignore[misc,arg-type]

    return TokenExchangeResult(
        success=True,
        access=str(refresh.access_token),
        refresh=str(refresh),
        user_id=user.id,
        username=user.username,
    )


# ============================================================
# 凭据管理（四层架构：ORM 只在 Service 层，API 层不碰 Model.objects）
# ============================================================


def list_user_credentials(user: Lawyer) -> list[PasskeyCredential]:
    """当前用户已注册的通行密钥（新→旧）。"""
    return list(PasskeyCredential.objects.filter(user=user))


def rename_user_credential(user: Lawyer, credential_id: int, name: str) -> PasskeyCredential | None:
    """重命名本人凭据；跨用户/不存在的 id 返回 None（防 IDOR 的属主过滤）。"""
    try:
        row = PasskeyCredential.objects.get(user=user, pk=credential_id)
    except PasskeyCredential.DoesNotExist:
        return None
    row.name = name
    row.save(update_fields=["name"])
    return row


def delete_user_credential(user: Lawyer, credential_id: int) -> bool:
    """删除 = 吊销；只允许操作本人凭据。"""
    deleted, _ = PasskeyCredential.objects.filter(user=user, pk=credential_id).delete()
    return bool(deleted)
