"""通行密钥端点的请求/响应 Schema。

与 social_auth_schemas 同一约定：业务失败不抛 HTTP 异常，响应里带
``success=False`` + 用户可读 message（HTTP 200）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ninja import Schema


class PasskeyCredentialOut(Schema):
    """一条已注册通行密钥的展示信息（不含公钥/计数器等内部字段）。"""

    id: int
    name: str
    rp_id: str
    created_at: datetime
    last_used_at: datetime | None = None


class PasskeyCredentialsOut(Schema):
    credentials: list[PasskeyCredentialOut]


class PasskeyOptionsOut(Schema):
    """ceremony 选项。``public_key`` 内为浏览器可直用的 WebAuthn Options JSON。"""

    success: bool
    message: str = ""
    public_key: dict[str, Any] | None = None


class PasskeyRegisterVerifyIn(Schema):
    name: str = ""
    credential: dict[str, Any]


class PasskeyAssertionIn(Schema):
    credential: dict[str, Any]


class PasskeyRenameIn(Schema):
    name: str


class PasskeyRegisterVerifyOut(Schema):
    success: bool
    message: str = ""
    credential: PasskeyCredentialOut | None = None


class PasskeyMutationOut(Schema):
    """重命名 / 删除等变更操作的统一响应。"""

    success: bool
    message: str = ""
