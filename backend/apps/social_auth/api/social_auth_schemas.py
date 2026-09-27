from __future__ import annotations

from ninja import Schema


class ProviderOut(Schema):
    name: str
    display_name: str
    # redirect：前端跳转到授权页；embedded_qr：前端用 JS SDK 内嵌渲染二维码
    login_mode: str = "redirect"
    # 渲染所需公开信息（app_id / authorize_url / 二维码尺寸等），不含密钥
    client_config: dict[str, str] | None = None


class ProvidersListOut(Schema):
    providers: list[ProviderOut]


class SessionOut(Schema):
    success: bool = True
    # 授权页地址；前端拼上 tmp_code 后整页导航过去
    goto: str = ""
    state: str = ""
    expires_in: int = 300
    message: str = ""


class TokenExchangeIn(Schema):
    code: str


class TokenExchangeOut(Schema):
    success: bool
    access: str = ""
    refresh: str = ""
    user_id: int | None = None
    username: str = ""
    message: str = ""


class BoundAccountOut(Schema):
    """当前用户已绑定的一个社交账号，供「个人设置 → 账号绑定」页展示。"""

    provider: str
    display_name: str
    avatar_url: str = ""
    bound_at: str = ""


class BoundAccountsOut(Schema):
    accounts: list[BoundAccountOut]


class UnbindOut(Schema):
    success: bool
    message: str = ""
