"""通用社交登录 Django View — 处理 Provider 授权跳转和回调。

只有 REDIRECT 型 Provider（微信等）需要整页跳转，走 Django View；
EMBEDDED_QR 型（飞书）由前端拿 Ninja 下发的授权 URL 渲染二维码，见 api/。

这里的授权请求构建逻辑同时被 api/ 复用，因此抽成模块级函数。
"""

from __future__ import annotations

import logging
import re
import secrets
import time
from dataclasses import dataclass

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.views import View

from apps.social_auth.models import TempAuth
from apps.social_auth.providers import ProviderRegistry
from apps.social_auth.providers.base import AuthorizationRequest

from .services import link_or_create_user

logger = logging.getLogger(__name__)

# oauth state 有效期（秒）。与飞书授权码 5 分钟有效期对齐，取更短的一方。
STATE_TTL_SECONDS = 300

_SAFE_REDIRECT_PATTERN = re.compile(r"^/[a-zA-Z0-9/_\-.?=&%+]*$")

# 只放行已知 Provider 的错误参数名，避免把任意 query 透给前端跳转链接
_PROVIDER_ERROR_PARAMS = ("error", "error_code", "error_description", "errmsg")


def sanitize_next_url(next_url: str | None) -> str:
    """只允许站内相对路径，拒绝 ``//evil.com`` 这类开放重定向。"""
    if not next_url or not _SAFE_REDIRECT_PATTERN.match(next_url) or next_url.startswith("//"):
        return "/"
    return next_url


def _frontend_callback_url(message: str) -> str:
    frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173")
    return f"{frontend_base}/social-callback?error={message}"


@dataclass(frozen=True)
class AuthorizationSession:
    """一次成功创建的授权会话。"""

    goto: str
    state: str
    auth_request: AuthorizationRequest


def build_authorization_session(
    request: HttpRequest,
    provider: str,
    *,
    next_url: str = "/",
) -> AuthorizationSession | None:
    """生成授权 URL 并把 state 写入 session。

    返回 None 表示该登录方式不可用（未注册、未配置、未启用或缺少回调地址）。
    调用方应把 None 当成「不给用户看细节」的通用失败处理，具体原因记在日志里。
    """
    try:
        provider_cls = ProviderRegistry.get(provider)
        config = ProviderRegistry.get_config(provider)
    except KeyError:
        logger.info("社交登录请求了不可用的 provider: %s", provider)
        return None

    # redirect_uri 用 Provider 配置里的值（SystemConfig 维护），
    # 不回落到当前请求 host——否则后台配的地址与飞书登记的不一致必然 unmatch。
    redirect_uri = config.extra.get("redirect_uri", "")
    if not redirect_uri:
        logger.warning("社交登录 provider %s 未配置回调地址", provider)
        return None

    auth_request = AuthorizationRequest(
        provider=provider,
        state=secrets.token_urlsafe(32),
        redirect_uri=redirect_uri,
        next_url=next_url,
        created_at=time.time(),
    )

    request.session["oauth"] = auth_request.to_session()
    request.session.modified = True

    return AuthorizationSession(
        goto=provider_cls(config).get_authorization_url(auth_request),
        state=auth_request.state,
        auth_request=auth_request,
    )


class SocialLoginView(View):
    """GET /social/{provider}/login/ — 重定向到 Provider 授权页（REDIRECT 型）。"""

    def get(self, request: HttpRequest, provider: str) -> HttpResponse:  # pragma: no cover
        if not ProviderRegistry._configs:
            ProviderRegistry.load_configs()

        session = build_authorization_session(
            request,
            provider,
            next_url=sanitize_next_url(request.GET.get("redirect")),
        )
        if session is None:
            return HttpResponseRedirect(_frontend_callback_url("unknown_provider"))

        return redirect(session.goto)


class SocialCallbackView(View):
    """GET /social/{provider}/callback/ — 接收 Provider 回调（302 落点）。"""

    async def get(self, request: HttpRequest, provider: str) -> HttpResponse:  # pragma: no cover
        saved = AuthorizationRequest.from_session(request.session.get("oauth", {}))
        if saved is None or saved.provider != provider:
            return HttpResponseRedirect(_frontend_callback_url("invalid_session"))

        if saved.state != request.GET.get("state", ""):
            return HttpResponseRedirect(_frontend_callback_url("invalid_state"))

        if saved.age_seconds() > STATE_TTL_SECONDS:
            return HttpResponseRedirect(_frontend_callback_url("state_expired"))

        try:
            provider_cls = ProviderRegistry.get(provider)
            config = ProviderRegistry.get_config(provider)
        except KeyError:
            return HttpResponseRedirect(_frontend_callback_url("unknown_provider"))

        instance = provider_cls(config)

        # 用户拒绝授权：不同平台错误参数名不同，逐个取
        for key in _PROVIDER_ERROR_PARAMS:
            if request.GET.get(key):
                return HttpResponseRedirect(_frontend_callback_url("provider_denied"))

        code = request.GET.get("code", "")
        if not code:
            return HttpResponseRedirect(_frontend_callback_url("no_code"))

        try:
            token_response = await instance.aexchange_code(code, saved)
            profile = await instance.aget_profile(token_response)
            user = await link_or_create_user(profile)
        except Exception as exc:
            logger.warning("Social auth failed for %s: %s", provider, exc)
            return HttpResponseRedirect(_frontend_callback_url("exchange_failed"))

        temp = await TempAuth.objects.acreate(user=user)

        if "oauth" in request.session:
            del request.session["oauth"]
            request.session.modified = True

        frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173")
        return HttpResponseRedirect(f"{frontend_base}/social-callback?code={temp.token}&redirect={saved.next_url}")
