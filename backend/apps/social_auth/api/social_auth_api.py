"""社交登录 API 端点 — 供前端 SPA 调用。"""

from __future__ import annotations

import logging

from django.http import HttpRequest
from ninja import Router

from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.social_auth.models import TempAuth
from apps.social_auth.providers import ProviderRegistry

from .social_auth_schemas import ProviderOut, ProvidersListOut, TokenExchangeIn, TokenExchangeOut

logger = logging.getLogger(__name__)

router = Router()


@router.get("/providers", response=ProvidersListOut, auth=None)
def list_providers(request: HttpRequest) -> ProvidersListOut:  # pragma: no cover
    """列出已启用的登录方式，供登录页渲染二维码 / 按钮。"""
    if not ProviderRegistry._configs:
        ProviderRegistry.load_configs()

    providers = []
    for item in ProviderRegistry.enabled_list():
        client_config = item.get("client_config") or {}
        # login_mode 由 registry 注入，前端据此决定跳转还是渲染二维码
        providers.append(
            ProviderOut(
                name=str(item["name"]),
                display_name=str(item["display_name"]),
                login_mode=str(client_config.get("login_mode", "redirect")),
                client_config={k: v for k, v in client_config.items() if k != "login_mode"},
            )
        )
    return ProvidersListOut(providers=providers)


@router.post("/token-exchange", response=TokenExchangeOut, auth=None)
@rate_limit_from_settings("AUTH")
async def token_exchange(request: HttpRequest, payload: TokenExchangeIn) -> TokenExchangeOut:  # pragma: no cover
    """用回调页拿到的一次性码换取 JWT。

    code 是 TempAuth 的 UUID（不是 Provider 的授权码）——Provider 授权码
    已在回调时用过并作废，这里避免把真 token 放进 URL。
    """
    try:
        temp = await TempAuth.objects.select_related("user").aget(token=payload.code)
    except TempAuth.DoesNotExist:
        return TokenExchangeOut(success=False, message="授权码无效或已过期")

    if temp.is_expired:
        await temp.adelete()
        return TokenExchangeOut(success=False, message="授权码已过期，请重新扫码")

    user = temp.user
    if not user.is_active:
        await temp.adelete()
        return TokenExchangeOut(success=False, message="账号未激活，请联系管理员")

    from ninja_jwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(user)

    await temp.adelete()

    return TokenExchangeOut(
        success=True,
        access=str(refresh.access_token),  # type: ignore[attr-defined]
        refresh=str(refresh),
        user_id=user.id,
        username=user.username,
    )
