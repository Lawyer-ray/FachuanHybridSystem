"""社交登录 API 端点 — 供前端 SPA 调用。

全部走 Ninja（而非 Django View）：Ninja 的 operation 默认 csrf_exempt，
与 /social/providers、/social/token-exchange 行为一致。若混用 Django View，
同一个 /api/v1/social 前缀下会出现「有的要 CSRF token、有的不要」的分裂，
前端难以统一处理。
"""

from __future__ import annotations

import logging

from django.http import HttpRequest
from ninja import Router

from apps.core.infrastructure.throttling import rate_limit_from_settings
from apps.core.security.auth import JWTOrSessionAuth
from apps.organization.models import Lawyer
from apps.social_auth.models import SocialAccount, TempAuth
from apps.social_auth.providers import ProviderRegistry, get_provider_spec
from apps.social_auth.services import SocialAccountNotFoundError, unbind_social_account
from apps.social_auth.views import STATE_TTL_SECONDS, build_authorization_session, sanitize_next_url

from .social_auth_schemas import (
    BoundAccountOut,
    BoundAccountsOut,
    ProviderOut,
    ProvidersListOut,
    SessionOut,
    TokenExchangeIn,
    TokenExchangeOut,
    UnbindOut,
)

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


@router.post("/{provider}/session", response=SessionOut, auth=None)
# 用 EXPORT 档而非 AUTH 档：AUTH 是 5 次/60 秒，按「账密登录防爆破」设的，
# 而本端点只发放授权 URL、不校验任何凭据，正常用户也会因二维码过期反复刷新，
# 套 AUTH 档会把真人挡在门外。20 次/60 秒仍能拦住脚本刷授权 URL。
@rate_limit_from_settings("EXPORT")
def create_session(
    request: HttpRequest,
    provider: str,
    redirect: str = "/",
) -> SessionOut:  # pragma: no cover
    """为内嵌二维码登录生成授权 URL。

    前端拿到 goto 后交给 JS SDK 渲染二维码，不跳页；扫码后由前端拼上 tmp_code
    再整页导航到 goto，飞书 302 打回 redirect_uri 完成授权。

    ``redirect`` 用 query 参数且不要求 body：这个端点只需要 provider 名和
    跳转意图，让前端裸 POST 即可。若声明 Schema 参数（哪怕是空 Schema），
    Ninja 也会要求 body 必须存在，导致无 body 的请求 422。
    """
    if not ProviderRegistry._configs:
        ProviderRegistry.load_configs()

    session = build_authorization_session(
        request,
        provider,
        next_url=sanitize_next_url(redirect),
    )
    if session is None:
        return SessionOut(success=False, message="该登录方式暂不可用，请刷新页面后重试")

    return SessionOut(
        success=True,
        goto=session.goto,
        state=session.state,
        expires_in=STATE_TTL_SECONDS,
    )


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

    refresh = RefreshToken.for_user(user)  # type: ignore[misc]

    await temp.adelete()

    return TokenExchangeOut(
        success=True,
        access=str(refresh.access_token),
        refresh=str(refresh),
        user_id=user.id,
        username=user.username,
    )


# ============================================================
# 账号绑定（个人设置 → 账号绑定）
#
# 与上面的登录端点不同：这几个端点要求已登录（JWTOrSessionAuth），
# 用来把当前用户和某个 Provider 身份关联/解除关联，不涉及新建账号。
# ============================================================


@router.get("/bindings", response=BoundAccountsOut, auth=JWTOrSessionAuth())
async def list_bindings(request: HttpRequest) -> BoundAccountsOut:  # pragma: no cover
    """列出当前用户已绑定的社交账号，供个人设置页展示。"""
    accounts = [
        BoundAccountOut(
            provider=row.provider,
            display_name=row.display_name,
            avatar_url=row.avatar_url,
            bound_at=row.created_at.isoformat(),
        )
        async for row in SocialAccount.objects.filter(user=request.auth).order_by("provider")  # type: ignore[attr-defined]
    ]
    return BoundAccountsOut(accounts=accounts)


@router.post("/{provider}/bind-session", response=SessionOut, auth=JWTOrSessionAuth())
@rate_limit_from_settings("EXPORT")
def create_bind_session(
    request: HttpRequest,
    provider: str,
    redirect: str = "/",
) -> SessionOut:  # pragma: no cover
    """为「个人设置 → 绑定账号」发起一次授权会话。

    与 ``create_session`` 共用同一套 build_authorization_session，唯一区别是
    带上 ``bind_user_id``：回调时据此把 Provider 身份关联到当前用户，
    而不是走登录/自动建号逻辑。
    """
    if not ProviderRegistry._configs:
        ProviderRegistry.load_configs()

    user: Lawyer = request.auth  # type: ignore[attr-defined]
    session = build_authorization_session(
        request,
        provider,
        next_url=sanitize_next_url(redirect),
        bind_user_id=user.id,
    )
    if session is None:
        return SessionOut(success=False, message="该登录方式暂不可用，请刷新页面后重试")

    return SessionOut(
        success=True,
        goto=session.goto,
        state=session.state,
        expires_in=STATE_TTL_SECONDS,
    )


@router.delete("/{provider}/bind", response=UnbindOut, auth=JWTOrSessionAuth())
async def unbind_provider(request: HttpRequest, provider: str) -> UnbindOut:  # pragma: no cover
    """解除当前用户与某个 Provider 的绑定。"""
    try:
        await unbind_social_account(request.auth, provider)  # type: ignore[attr-defined]
    except SocialAccountNotFoundError:
        return UnbindOut(success=False, message="未找到绑定记录")
    return UnbindOut(success=True)


@router.get("/provider-catalog", response=ProvidersListOut, auth=JWTOrSessionAuth())
def list_provider_catalog(request: HttpRequest) -> ProvidersListOut:  # pragma: no cover
    """列出全部已知 Provider（含未启用），供绑定页展示「暂未开放」的占位入口。

    与 ``/providers`` 的区别：那个只给登录页用、只返回已启用的，这里给已登录用户
    看「还能绑定哪些平台」，未配置的也要显示（灰态），所以不能复用同一份数据源。
    """
    if not ProviderRegistry._configs:
        ProviderRegistry.load_configs()

    providers = []
    for name in ProviderRegistry.names():
        spec = get_provider_spec(name) or {}
        config = ProviderRegistry._configs.get(name)
        if config and config.is_enabled:
            provider_cls = ProviderRegistry.get(name)
            client_config = provider_cls(config).get_client_config() or {}
            providers.append(
                ProviderOut(
                    name=name,
                    display_name=config.display_name,
                    login_mode=str(client_config.get("login_mode", provider_cls.login_mode.value)),
                    client_config={k: v for k, v in client_config.items() if k != "login_mode"},
                )
            )
        else:
            providers.append(
                ProviderOut(
                    name=name,
                    display_name=str(spec.get("display_name", name)),
                    login_mode="redirect",
                    client_config=None,
                )
            )
    return ProvidersListOut(providers=providers)
