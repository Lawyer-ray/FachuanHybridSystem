"""社交登录 API 端点 — 供前端 SPA 调用。"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import HttpRequest
from ninja import Router

from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.social_auth.models import TempAuth
from apps.social_auth.providers import ProviderRegistry

from .social_auth_schemas import (
    ProvidersListOut,
    ProviderOut,
    TokenExchangeIn,
    TokenExchangeOut,
)

logger = logging.getLogger(__name__)

router = Router()

_loaded = False


def _ensure_loaded() -> None:
    global _loaded
    if not _loaded:
        ProviderRegistry.load_configs(
            getattr(settings, "SOCIAL_AUTH_PROVIDERS", {})
        )
        _loaded = True


@router.get("/providers", response=ProvidersListOut, auth=None)
def list_providers(request: HttpRequest) -> ProvidersListOut:
    _ensure_loaded()
    items = ProviderRegistry.enabled_list()
    providers = []
    for p in items:
        providers.append(
            ProviderOut(
                name=str(p["name"]),
                display_name=str(p["display_name"]),
                client_config=p["client_config"],  # type: ignore[arg-type]
            )
        )
    return ProvidersListOut(providers=providers)


@router.post("/token-exchange", response=TokenExchangeOut, auth=None)
@rate_limit_from_settings("AUTH")
def token_exchange(request: HttpRequest, payload: TokenExchangeIn) -> TokenExchangeOut:
    try:
        temp = TempAuth.objects.select_related("user").get(token=payload.code)
    except TempAuth.DoesNotExist:
        return TokenExchangeOut(success=False, message="授权码无效或已过期")

    if temp.is_expired:
        temp.delete()
        return TokenExchangeOut(success=False, message="授权码已过期，请重新扫码")

    user = temp.user
    if not user.is_active:
        temp.delete()
        return TokenExchangeOut(success=False, message="账号未激活，请联系管理员")

    from ninja_jwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(user)

    temp.delete()

    return TokenExchangeOut(
        success=True,
        access=str(refresh.access_token),  # type: ignore[attr-defined]
        refresh=str(refresh),
        user_id=user.id,
        username=user.username,
    )
