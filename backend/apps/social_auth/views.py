"""通用社交登录 Django View — 处理 Provider 授权跳转和回调。

两类入口共用同一套 session 逻辑：

- ``GET  /social/{provider}/login/``    整页跳转（REDIRECT 型 Provider）
- ``POST /api/v1/social/{provider}/session/``  前端内嵌二维码（EMBEDDED_QR 型）
  拿 goto URL 后由 JS SDK 在页面内渲染二维码，不跳页。
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import time

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
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


def _sanitize_next_url(next_url: str) -> str:
    """只允许站内相对路径，拒绝 ``//evil.com`` 这类开放重定向。"""
    if not next_url or not _SAFE_REDIRECT_PATTERN.match(next_url) or next_url.startswith("//"):
        return "/"
    return next_url


def _frontend_callback_url(message: str) -> str:
    frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173")
    return f"{frontend_base}/social-callback?error={message}"


def _build_authorization_request(
    provider: str, next_url: str
) -> tuple[AuthorizationRequest | None, HttpResponse | None]:
    """生成授权请求并写入 session。

    返回 (request, None) 或 (None, 错误响应)。分离出来是为了让
    整页跳转视图与 API 视图复用同一段 state 生成逻辑。
    """
    try:
        provider_cls = ProviderRegistry.get(provider)
        config = ProviderRegistry.get_config(provider)
    except KeyError:
        return None, HttpResponseBadRequest(f"未知或未启用的登录方式: {provider}")

    instance = provider_cls(config)

    # redirect_uri 用 Provider 配置里的值（SystemConfig 维护），
    # 不回落到当前请求 host——否则后台配的地址与飞书登记的不一致必然 unmatch。
    redirect_uri = config.extra.get("redirect_uri", "")
    if not redirect_uri:
        return None, HttpResponseBadRequest(f"登录方式 {provider} 未配置回调地址，请联系管理员")

    auth_request = AuthorizationRequest(
        provider=provider,
        state=secrets.token_urlsafe(32),
        redirect_uri=redirect_uri,
        next_url=next_url,
        created_at=time.time(),
    )
    return auth_request, None


class SocialLoginView(View):
    """GET /social/{provider}/login/ — 重定向到 Provider 授权页（REDIRECT 型）。"""

    def get(self, request: HttpRequest, provider: str) -> HttpResponse:  # pragma: no cover
        if not ProviderRegistry._configs:
            ProviderRegistry.load_configs()

        auth_request, error = _build_authorization_request(
            provider, _sanitize_next_url(request.GET.get("redirect", "/"))
        )
        if error is not None or auth_request is None:
            return error or HttpResponseBadRequest("登录失败")

        request.session["oauth"] = auth_request.to_session()
        request.session.modified = True

        provider_cls = ProviderRegistry.get(provider)
        config = ProviderRegistry.get_config(provider)
        auth_url = provider_cls(config).get_authorization_url(auth_request)
        return redirect(auth_url)


class SocialSessionView(View):
    """POST /api/v1/social/{provider}/session/ — 为内嵌二维码生成授权 URL。

    前端不跳页，拿到 URL 后交给二维码 SDK 渲染。PUT/DELETE 等一律拒绝。
    """

    def post(self, request: HttpRequest, provider: str) -> HttpResponse:  # pragma: no cover
        if not ProviderRegistry._configs:
            ProviderRegistry.load_configs()

        # 二维码登录同样是登录入口，复用同一套 next_url 安全校验
        next_url = _sanitize_next_url(request.GET.get("redirect", "/"))
        auth_request, error = _build_authorization_request(provider, next_url)
        if error is not None or auth_request is None:
            return error or HttpResponseBadRequest("登录失败")

        provider_cls = ProviderRegistry.get(provider)
        config = ProviderRegistry.get_config(provider)
        instance = provider_cls(config)

        request.session["oauth"] = auth_request.to_session()
        request.session.modified = True

        return HttpResponse(
            json.dumps(
                {
                    "goto": instance.get_authorization_url(auth_request),
                    "state": auth_request.state,
                    "expires_in": STATE_TTL_SECONDS,
                }
            ),
            content_type="application/json",
        )


class SocialCallbackView(View):
    """GET /social/{provider}/callback/ — 接收 Provider 回调（302 落点）。"""

    async def get(self, request: HttpRequest, provider: str) -> HttpResponse:  # pragma: no cover
        raw = request.session.get("oauth", {})
        if not raw:
            return HttpResponseRedirect(_frontend_callback_url("no_session"))

        saved = AuthorizationRequest.from_session(raw)
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
