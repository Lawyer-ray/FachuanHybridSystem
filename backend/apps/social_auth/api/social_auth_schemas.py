from __future__ import annotations

from ninja import Schema


class ProviderOut(Schema):
    name: str
    display_name: str
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
