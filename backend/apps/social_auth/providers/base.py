from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from asgiref.sync import sync_to_async


class LoginMode(str, Enum):
    """Provider 的登录交互形态。

    前端据此决定渲染逻辑：

    - ``REDIRECT``：整页跳转到 Provider 授权页（微信 PC 扫码、Google、GitHub）。
      前端拿到 authorize_url 后直接 ``location.href = url``。
    - ``EMBEDDED_QR``：在登录页内嵌二维码（飞书）。前端用 JS SDK 在页面内渲染二维码，
      扫码后由 SDK 回传一次性码，再由前端拼到 authorize_url 上完成跳转。
    """

    REDIRECT = "redirect"
    EMBEDDED_QR = "embedded_qr"


@dataclass(frozen=True)
class ProviderConfig:
    """单个 Provider 的配置"""

    name: str
    display_name: str
    client_id: str
    client_secret: str
    is_enabled: bool = True
    # 登录页按钮顺序（来自 SocialAuthProvider.priority，小的在前）
    priority: int = 10
    # 前端渲染二维码 / 按钮所需的最小信息，不含任何密钥
    client_config: dict[str, str] = field(default_factory=dict)
    # Provider 私有附加配置（如 redirect_uri、scope）
    extra: dict[str, str] = field(default_factory=dict)

    def require(self, key: str) -> str:
        """读取必填配置，缺失时抛出可读错误。

        Provider 内部统一走这个方法取 redirect_uri / scope 等，
        避免散落的 ``extra["xxx"]`` KeyError 让前端只看到 500。
        """
        value = self.extra.get(key, "")
        if not value:
            raise ValueError(f"Provider {self.name} 缺少必要配置: {key}")
        return value


@dataclass(frozen=True)
class AuthorizationRequest:
    """一次授权请求的上下文，发起时生成、回调时从 session 还原。

    之所以把 redirection 所需的全部参数收在这里，是为了给 PKCE 这类
    「发起时生成 verifier、回调时必须带回去」的流程预留位置——否则将来接
    Google 时只能改 ``exchange_code`` 签名，把已上线的 Provider 全部返工。
    """

    provider: str
    state: str
    redirect_uri: str
    next_url: str = "/"
    created_at: float = 0.0
    code_verifier: str | None = None  # PKCE (RFC 7636)，Google 等需要
    extra: dict[str, str] = field(default_factory=dict)

    def to_session(self) -> dict[str, Any]:
        """序列化为可写入 Django session 的 dict。"""
        return {
            "provider": self.provider,
            "state": self.state,
            "redirect_uri": self.redirect_uri,
            "next_url": self.next_url,
            "created_at": self.created_at,
            "code_verifier": self.code_verifier,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_session(cls, data: dict[str, Any]) -> AuthorizationRequest | None:
        """从 session 还原；数据不完整时返回 None 而不是抛异常。"""
        provider = data.get("provider")
        state = data.get("state")
        redirect_uri = data.get("redirect_uri")
        if not (isinstance(provider, str) and isinstance(state, str) and isinstance(redirect_uri, str)):
            return None
        extra = data.get("extra")
        return cls(
            provider=provider,
            state=state,
            redirect_uri=redirect_uri,
            next_url=str(data.get("next_url") or "/"),
            created_at=float(data.get("created_at") or 0.0),
            code_verifier=data.get("code_verifier") if isinstance(data.get("code_verifier"), str) else None,
            extra=dict(extra) if isinstance(extra, dict) else {},
        )

    def age_seconds(self, now: float | None = None) -> float:
        """距发起已过多少秒。"""
        current = time.time() if now is None else now
        return max(0.0, current - self.created_at)


@dataclass(frozen=True)
class TokenResponse:
    """Provider 返回的 token"""

    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SocialProfile:
    """所有 Provider 统一输出"""

    provider: str
    provider_user_id: str
    email: str | None
    display_name: str | None
    avatar_url: str | None
    raw_data: dict = field(default_factory=dict)


class SocialProvider(ABC):
    """所有 Provider 的基类。

    接入新平台只需子类化并实现四个成员：

    1. 类属性``ENDPOINTS``：各接口地址。允许声明多个 Host(
       飞书的授权页、令牌、用户信息就在三个不同域名下)，
       所以不能假设只有一个 BASE_URL。
    2.``get_authorization_url``：拼出授权页 URL。
    3.``exchange_code``：授权码换 token。
    4.``get_profile``：取用户信息，映射成统一的 SocialProfile。

    ``login_mode``默认 REDIRECT;内嵌二维码的 Provider(飞书)改为 EMBEDDED_QR。
    """

    ENDPOINTS: dict[str, str] = {}
    login_mode: LoginMode = LoginMode.REDIRECT

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    @abstractmethod
    def get_authorization_url(self, request: AuthorizationRequest) -> str:
        """返回 Provider 授权页 URL。"""

    @abstractmethod
    def exchange_code(self, code: str, request: AuthorizationRequest) -> TokenResponse:
        """用授权码换 access_token。"""

    @abstractmethod
    def get_profile(self, token_response: TokenResponse) -> SocialProfile:
        """获取用户信息。"""

    def get_client_config(self) -> dict[str, str] | None:
        """返回前端渲染二维码 / 按钮所需的配置。

        只能放公开信息(app_id、二维码宽高、authorize 地址等),
        **绝不返回 client_secret**。返回 None 表示前端无需额外配置。
        """
        return None

    # ── async 版本：默认回退到同步方法，Provider 按需覆盖 ──────────
    # Django 侧是 async 视图，直接调同步 httpx 会阻塞事件循环，
    # 所以网络型 Provider 应覆盖这两个方法。

    async def aexchange_code(self, code: str, request: AuthorizationRequest) -> TokenResponse:
        """用授权码换 access_token（async 版本）。"""
        return await sync_to_async(self.exchange_code)(code, request)

    async def aget_profile(self, token_response: TokenResponse) -> SocialProfile:
        """获取用户信息（async 版本）。"""
        return await sync_to_async(self.get_profile)(token_response)

    def endpoint(self, key: str) -> str:
        """读取 ENDPOINTS 中的地址，缺失时报可读错误。"""
        url = self.ENDPOINTS.get(key, "")
        if not url:
            raise ValueError(f"Provider {self.config.name} 未声明接口地址: {key}")
        return url

    @staticmethod
    def _check_api_error(data: dict[str, Any], *, code_key: str = "code", msg_key: str = "msg") -> None:
        """校验飞书风格 ``{"code": 0, "msg": "success"}`` 响应，失败时抛 ValueError。

        飞书把业务错误放在 HTTP 200 里，不检查就会拿错误体当用户信息用。
        """
        code = data.get(code_key)
        if code in (None, 0):
            return
        raise ValueError(f"接口返回错误({code}): {data.get(msg_key, 'unknown')}")
