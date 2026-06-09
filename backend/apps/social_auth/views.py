"""通用社交登录 Django View — 处理 Provider 授权跳转和回调。"""

from __future__ import annotations

import logging
import secrets
import time

from django.conf import settings
from django.http import (
    HttpResponse,
    HttpRequest,
    HttpResponseBadRequest,
    HttpResponseRedirect,
)
from django.shortcuts import redirect
from django.views import View

from apps.social_auth.models import TempAuth
from apps.social_auth.providers import ProviderRegistry

from .services import link_or_create_user

logger = logging.getLogger(__name__)

_STATE_TTL_SECONDS = 300
_SAFE_REDIRECT_PATTERN = __import__("re").compile(r"^/[a-zA-Z0-9/_\-.?=&%+]*$")


class SocialLoginView(View):
    """GET /social/{provider}/login/ — 重定向到 Provider 授权页"""

    def get(self, request: HttpRequest, provider: str) -> HttpResponse:
        if not ProviderRegistry._configs:
            ProviderRegistry.load_configs(
                getattr(settings, "SOCIAL_AUTH_PROVIDERS", {})
            )

        try:
            provider_cls = ProviderRegistry.get(provider)
            config = ProviderRegistry.get_config(provider)
        except KeyError:
            return HttpResponseBadRequest(f"未知的登录方式: {provider}")

        if not config.is_enabled:
            return HttpResponseBadRequest(f"该登录方式暂未启用: {provider}")

        instance = provider_cls(config)

        state = secrets.token_urlsafe(32)
        next_url = request.GET.get("redirect", "/")
        # 防止开放重定向：只允许相对路径，且不能包含协议（如 //evil.com）
        if not _SAFE_REDIRECT_PATTERN.match(next_url) or next_url.startswith("//"):
            next_url = "/"
        request.session["oauth"] = {
            "provider": provider,
            "state": state,
            "created_at": time.time(),
            "next_url": next_url,
        }
        request.session.modified = True

        auth_url = instance.get_authorization_url(state)
        return redirect(auth_url)


class SocialCallbackView(View):
    """GET /social/{provider}/callback/ — 接收 Provider 回调"""

    def get(self, request: HttpRequest, provider: str) -> HttpResponse:
        frontend_base = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:5173")

        session_data = request.session.get("oauth", {})
        if not session_data:
            return HttpResponseRedirect(f"{frontend_base}/social-callback?error=no_session")

        if session_data.get("provider") != provider:
            return HttpResponseRedirect(f"{frontend_base}/social-callback?error=provider_mismatch")

        state = request.GET.get("state", "")
        if session_data.get("state") != state:
            return HttpResponseRedirect(f"{frontend_base}/social-callback?error=invalid_state")

        created_at = session_data.get("created_at", 0)
        if time.time() - created_at > _STATE_TTL_SECONDS:
            return HttpResponseRedirect(f"{frontend_base}/social-callback?error=state_expired")

        wx_error = request.GET.get("errcode")
        if wx_error:
            return HttpResponseRedirect(
                f"{frontend_base}/social-callback?error=provider_denied&detail={wx_error}"
            )

        try:
            provider_cls = ProviderRegistry.get(provider)
            config = ProviderRegistry.get_config(provider)
        except KeyError:
            return HttpResponseRedirect(f"{frontend_base}/social-callback?error=unknown_provider")

        instance = provider_cls(config)

        code = request.GET.get("code", "")
        if not code:
            return HttpResponseRedirect(f"{frontend_base}/social-callback?error=no_code")

        try:
            token_response = instance.exchange_code(code, state)
        except Exception as exc:
            logger.warning("Social auth exchange failed for %s: %s", provider, exc)
            return HttpResponseRedirect(
                f"{frontend_base}/social-callback?error=exchange_failed"
            )

        try:
            profile = instance.get_profile(token_response)
        except Exception as exc:
            logger.warning("Social auth profile fetch failed for %s: %s", provider, exc)
            return HttpResponseRedirect(
                f"{frontend_base}/social-callback?error=profile_failed"
            )

        try:
            user = link_or_create_user(profile)
        except Exception as exc:
            logger.error("Social auth user creation failed for %s: %s", provider, exc)
            return HttpResponseRedirect(
                f"{frontend_base}/social-callback?error=user_creation_failed"
            )

        temp = TempAuth.objects.create(user=user)

        if "oauth" in request.session:
            del request.session["oauth"]
            request.session.modified = True

        next_url = session_data.get("next_url", "/")
        # 二次校验：防止 session 被篡改后构造恶意重定向
        if not _SAFE_REDIRECT_PATTERN.match(next_url) or next_url.startswith("//"):
            next_url = "/"
        return HttpResponseRedirect(
            f"{frontend_base}/social-callback?code={temp.token}&redirect={next_url}"
        )
