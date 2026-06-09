from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProviderConfig:
    """单个 Provider 的配置"""

    name: str
    display_name: str
    client_id: str
    client_secret: str
    is_enabled: bool = True
    extra: dict[str, str] = field(default_factory=dict)


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
    """所有 Provider 的基类。实现三个方法即可接入新平台。"""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    @abstractmethod
    def get_authorization_url(self, state: str) -> str:
        """返回 Provider 授权页 URL"""

    @abstractmethod
    def exchange_code(self, code: str, state: str) -> TokenResponse:
        """用授权码换 access_token"""

    @abstractmethod
    def get_profile(self, token_response: TokenResponse) -> SocialProfile:
        """获取用户信息"""

    def get_client_config(self) -> dict[str, str] | None:
        """返回前端渲染二维码需要的配置。默认 None 表示无需前端配置。"""
        return None
