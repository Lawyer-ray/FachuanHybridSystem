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


class TokenExchangeIn(Schema):
    code: str


class TokenExchangeOut(Schema):
    success: bool
    access: str = ""
    refresh: str = ""
    user_id: int | None = None
    username: str = ""
    message: str = ""
