"""社交登录 token 交换与绑定列表服务。

承载 social_auth_api 下沉的业务：一次性授权码（TempAuth）换取 JWT、
当前用户已绑定社交账号的查询。

失败语义沿用 API 时期的约定——不抛异常，返回 ``success=False`` +
用户可读 message（HTTP 200），由 API 层原样组装响应 Schema。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from apps.social_auth.models import SocialAccount, TempAuth

if TYPE_CHECKING:
    from uuid import UUID

    from apps.organization.models import Lawyer


@dataclass
class TokenExchangeResult:
    """token 交换结果（API 层据此组装 TokenExchangeOut）。"""

    success: bool
    message: str = ""
    access: str = ""
    refresh: str = ""
    user_id: int | None = None
    username: str = ""


@dataclass
class BoundAccountRow:
    """已绑定社交账号的一行展示数据。"""

    provider: str
    display_name: str
    avatar_url: str
    bound_at: str


async def exchange_temp_code_for_jwt(code: UUID | str) -> TokenExchangeResult:
    """用回调页拿到的一次性码（TempAuth UUID）换取 JWT。

    code 是 TempAuth 的 UUID（不是 Provider 的授权码）——Provider 授权码
    已在回调时用过并作废。失败（无效 / 过期 / 账号未激活）均返回
    success=False + message，不抛异常。
    """
    try:
        temp = await TempAuth.objects.select_related("user").aget(token=code)
    except TempAuth.DoesNotExist:
        return TokenExchangeResult(success=False, message="授权码无效或已过期")

    if temp.is_expired:
        await temp.adelete()
        return TokenExchangeResult(success=False, message="授权码已过期，请重新扫码")

    user = temp.user
    if not user.is_active:
        await temp.adelete()
        return TokenExchangeResult(success=False, message="账号未激活，请联系管理员")

    from ninja_jwt.tokens import RefreshToken

    from apps.core.security.jwt_password_binding import bind_password_claim

    # 安全审计 C-14/E-07：扫码登录签发的 token 同样绑定密码指纹，改密后失效
    refresh = bind_password_claim(RefreshToken.for_user(user), user)  # type: ignore[misc,arg-type]

    await temp.adelete()

    return TokenExchangeResult(
        success=True,
        access=str(refresh.access_token),
        refresh=str(refresh),
        user_id=user.id,
        username=user.username,
    )


async def list_bound_accounts(user: Lawyer) -> list[BoundAccountRow]:
    """列出当前用户已绑定的社交账号（按 provider 排序）。"""
    return [
        BoundAccountRow(
            provider=row.provider,
            display_name=row.display_name,
            avatar_url=row.avatar_url,
            bound_at=row.created_at.isoformat(),
        )
        async for row in SocialAccount.objects.filter(user=user).order_by("provider")
    ]
