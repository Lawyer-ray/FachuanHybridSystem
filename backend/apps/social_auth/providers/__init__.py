from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import ProviderConfig, SocialProvider


class ProviderRegistry:
    """Provider 注册表。通过 @ProviderRegistry.register("name") 注册。"""

    _providers: dict[str, type[SocialProvider]] = {}
    _configs: dict[str, ProviderConfig] = {}

    @classmethod
    def register(cls, name: str):  # type: ignore[no-untyped-def]
        def decorator(provider_cls: type[SocialProvider]) -> type[SocialProvider]:
            cls._providers[name] = provider_cls
            return provider_cls
        return decorator

    @classmethod
    def get(cls, name: str) -> type[SocialProvider]:
        if name not in cls._providers:
            raise KeyError(f"Unknown provider: {name}")
        return cls._providers[name]

    @classmethod
    def load_configs(cls, provider_configs: dict[str, dict]) -> None:
        """从 settings.SOCIAL_AUTH_PROVIDERS 加载配置"""
        for name, cfg in provider_configs.items():
            if name not in cls._providers:
                continue
            from .base import ProviderConfig

            cls._configs[name] = ProviderConfig(
                name=name,
                display_name=cfg["display_name"],
                client_id=cfg.get("client_id", ""),
                client_secret=cfg.get("client_secret", ""),
                is_enabled=cfg.get("is_enabled", True),
                extra=cfg.get("extra", {}),
            )

    @classmethod
    def get_config(cls, name: str) -> ProviderConfig:
        if name not in cls._configs:
            raise KeyError(f"No config for provider: {name}")
        return cls._configs[name]

    @classmethod
    def enabled_list(cls) -> list[dict[str, str | dict | None]]:
        """返回已启用的 Provider 列表（供前端渲染）"""
        result = []
        for name, provider_cls in cls._providers.items():
            config = cls._configs.get(name)
            if config and config.is_enabled:
                instance = provider_cls(config)
                result.append({
                    "name": name,
                    "display_name": config.display_name,
                    "client_config": instance.get_client_config(),
                })
        return result


# 导入所有 Provider 以触发 @register 装饰器
from . import wechat
