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
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.views import View

from apps.organization.models import Lawyer
from apps.social_auth.models import TempAuth
from apps.social_auth.providers import ProviderRegistry
from apps.social_auth.providers.base import AuthorizationRequest

from .services import (
    SocialAccountConflictError,
    SocialAccountNotBoundError,
    SocialAccountProviderOccupiedError,
    bind_social_account_to_user,
    resolve_user_by_social_profile,
)

logger = logging.getLogger(__name__)

# oauth state 有效期（秒）。与飞书授权码 5 分钟有效期对齐，取更短的一方。
STATE_TTL_SECONDS = 300

_SAFE_REDIRECT_PATTERN = re.compile(r"^/[a-zA-Z0-9/_\-.?=&%+]*$")

# 只放行已知 Provider 的错误参数名，避免把任意 query 透给前端跳转链接
_PROVIDER_ERROR_PARAMS = ("error", "error_code", "error_description", "errmsg")

# 发起「个人设置 → 绑定账号」流程时，写进 AuthorizationRequest.extra 的键名，
# 用来在回调时判断这是登录流程还是绑定流程（不能新建 Lawyer）。
_BIND_USER_ID_KEY = "bind_user_id"


def sanitize_next_url(next_url: str | None) -> str:
    """只允许站内相对路径，拒绝 ``//evil.com`` 这类开放重定向。"""
    if not next_url or not _SAFE_REDIRECT_PATTERN.match(next_url) or next_url.startswith("//"):
        return "/"
    return next_url


# provider 直接取自 URL 路径，属用户可控。不转义时攻击者可以塞入 \n 在日志里
# 伪造额外行（log injection）；CodeQL 的 py/log-injection 规则也会报这一点。
_LOG_UNSAFE_CHARS = str.maketrans({"\n": "\\n", "\r": "\\r", "\t": "\\t"})


def safe_for_log(value: object) -> str:
    """转义日志值里的换行与制表符。

    只转义、不截断——日志仍保留完整内容，排查时不丢信息。
    """
    return str(value).translate(_LOG_UNSAFE_CHARS)


def _frontend_redirect_url(next_url: str, **params: str) -> str:
    """拼出跳回前端 ``/social-callback`` 的 URL，附带任意查询参数。"""
    frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5090")
    query = urlencode({**params, "redirect": next_url})
    return f"{frontend_base}/social-callback?{query}"


def _frontend_callback_url(message: str) -> str:
    return _frontend_redirect_url("/", error=message)


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
    bind_user_id: int | None = None,
) -> AuthorizationSession | None:
    """生成授权 URL 并把 state 写入 session。

    返回 None 表示该登录方式不可用（未注册、未配置、未启用或缺少回调地址）。
    调用方应把 None 当成「不给用户看细节」的通用失败处理，具体原因记在日志里。

    ``bind_user_id``：仅「个人设置 → 绑定账号」流程传入，标记这次授权完成后
    要把 Provider 身份关联到这个已登录用户，而不是走登录逻辑。
    """
    try:
        provider_cls = ProviderRegistry.get(provider)
        config = ProviderRegistry.get_config(provider)
    except KeyError:
        logger.info("社交登录请求了不可用的 provider: %s", safe_for_log(provider))
        return None

    # redirect_uri 用 Provider 配置里的值（SystemConfig 维护），
    # 不回落到当前请求 host——否则后台配的地址与飞书登记的不一致必然 unmatch。
    redirect_uri = config.extra.get("redirect_uri", "")
    if not redirect_uri:
        logger.warning("社交登录 provider %s 未配置回调地址", safe_for_log(provider))
        return None

    extra: dict[str, str] = {}
    if bind_user_id is not None:
        extra[_BIND_USER_ID_KEY] = str(bind_user_id)

    auth_request = AuthorizationRequest(
        provider=provider,
        state=secrets.token_urlsafe(32),
        redirect_uri=redirect_uri,
        next_url=next_url,
        created_at=time.time(),
        extra=extra,
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
        except Exception as exc:
            logger.warning("Social auth failed for %s: %s", safe_for_log(provider), safe_for_log(exc))
            return HttpResponseRedirect(_frontend_callback_url("exchange_failed"))

        bind_user_id_raw = saved.extra.get(_BIND_USER_ID_KEY, "")

        if "oauth" in request.session:
            del request.session["oauth"]
            request.session.modified = True

        # 绑定流程：只关联到已登录用户，绝不新建 Lawyer
        if bind_user_id_raw:
            try:
                bind_user = await Lawyer.objects.aget(pk=int(bind_user_id_raw))
            except (Lawyer.DoesNotExist, ValueError):
                return HttpResponseRedirect(_frontend_redirect_url(saved.next_url, error="not_bound"))

            try:
                await bind_social_account_to_user(profile, bind_user)
            except SocialAccountConflictError:
                return HttpResponseRedirect(_frontend_redirect_url(saved.next_url, error="already_bound"))
            except SocialAccountProviderOccupiedError:
                return HttpResponseRedirect(_frontend_redirect_url(saved.next_url, error="provider_occupied"))
            except Exception as exc:
                logger.warning("Social bind failed for %s: %s", safe_for_log(provider), safe_for_log(exc))
                return HttpResponseRedirect(_frontend_redirect_url(saved.next_url, error="exchange_failed"))

            return HttpResponseRedirect(_frontend_redirect_url(saved.next_url, bound=provider))

        # 登录流程：只放行已绑定的社交身份。未绑定就拒绝，不再自动建号——
        # 自动建出的 soc_xxx 账号对应不上真实律师，后台无法判断是谁。
        try:
            user = await resolve_user_by_social_profile(profile)
        except SocialAccountNotBoundError:
            return HttpResponseRedirect(_frontend_redirect_url(saved.next_url, error="unbound"))
        except Exception as exc:
            logger.warning("Social auth failed for %s: %s", safe_for_log(provider), safe_for_log(exc))
            return HttpResponseRedirect(_frontend_callback_url("exchange_failed"))

        temp = await TempAuth.objects.acreate(user=user)
        return HttpResponseRedirect(_frontend_redirect_url(saved.next_url, code=str(temp.token)))
