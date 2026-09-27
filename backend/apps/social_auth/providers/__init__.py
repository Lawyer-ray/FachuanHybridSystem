"""Provider 注册表与配置解析。

配置来源为 SystemConfig(加密存储、admin 可改)，而非 Django settings：
密钥不落环境变量，改完不用重启；上线后换域名只需 admin 改
``SOCIAL_AUTH_FEISHU_REDIRECT_URI``。

为了让新平台接入只加代码不加判断，这里用一张「适配表」把
SystemConfig 键名映射到 ProviderConfig。
"""

from __future__ import annotations

import logging
from typing import Any

from apps.core.models import SystemConfig

from .base import ProviderConfig

logger = logging.getLogger(__name__)

# SystemConfig 分类名
CATEGORY = "social_auth"

# 每个 Provider 在 SystemConfig 中的键名前缀与字段映射。
# 新增 Provider 只在这里加一行 + 一个 provider 文件，无需改动其它代码。
PROVIDER_SPECS: dict[str, dict[str, Any]] = {
    "feishu": {
        "display_name": "飞书",
        "prefix": "SOCIAL_AUTH_FEISHU_",
        "enabled_key": "SOCIAL_AUTH_FEISHU_ENABLED",
        "extra_keys": ("REDIRECT_URI", "SCOPE"),
    },
    "wechat": {
        "display_name": "微信",
        "prefix": "SOCIAL_AUTH_WECHAT_",
        "enabled_key": "SOCIAL_AUTH_WECHAT_ENABLED",
        "extra_keys": ("REDIRECT_URI",),
    },
}


def get_provider_spec(name: str) -> dict[str, Any] | None:
    """返回 Provider 的配置描述；未登记返回 None。"""
    return PROVIDER_SPECS.get(name)


class ProviderRegistry:
    """Provider 注册表。通过 @ProviderRegistry.register("name") 注册。"""

    _providers: dict[str, type[Any]] = {}

    # 配置缓存：provider 名 → ProviderConfig。
    # 由 load_configs() 填充，SystemConfig 保存时由外部调用 clear_configs() 失效。
    _configs: dict[str, ProviderConfig] = {}

    @classmethod
    def register(cls, name: str) -> Any:
        def decorator(provider_cls: type[Any]) -> type[Any]:
            cls._providers[name] = provider_cls
            return provider_cls

        return decorator

    @classmethod
    def names(cls) -> list[str]:
        return list(cls._providers)

    @classmethod
    def get(cls, name: str) -> type[Any]:
        if name not in cls._providers:
            raise KeyError(f"Unknown provider: {name}")
        return cls._providers[name]

    @classmethod
    def has(cls, name: str) -> bool:
        return name in cls._providers

    @classmethod
    def clear_configs(cls, name: str | None = None) -> None:
        """清除配置缓存。admin 改完 SystemConfig 后调用。"""
        if name is None:
            cls._configs.clear()
            return
        cls._configs.pop(name, None)

    @classmethod
    def load_configs(cls, provider_configs: dict[str, dict] | None = None) -> None:
        """从 SystemConfig 读取全部 Provider 配置。

        ``provider_configs`` 参数已废弃（保留以兼容旧调用方），
        传了会记一条 warning 并忽略——真实来源只有 SystemConfig，
        否则会出现「admin 改了一份、settings 里还有一份」的双源不一致。
        """
        if provider_configs:
            logger.warning("ProviderRegistry.load_configs 的 provider_configs 参数已废弃，配置请从 SystemConfig 读取")

        cls._configs.clear()
        for name in list(cls._providers):
            config = cls._build_config(name)
            if config is not None and config.is_enabled:
                cls._configs[name] = config

    @classmethod
    def _build_config(cls, name: str) -> ProviderConfig | None:
        """用分类查询一次性取回该 Provider 全部配置，拼成 ProviderConfig。"""
        spec = PROVIDER_SPECS.get(name)
        if spec is None:
            return None

        prefix: str = spec["prefix"]
        rows = {
            str(row.key): str(row.value or "")
            for row in SystemConfig.objects.filter(category=CATEGORY, is_active=True, key__startswith=prefix)
        }
        if not rows:
            return None

        client_id = rows.get(f"{prefix}APP_ID", "")
        client_secret = rows.get(f"{prefix}APP_SECRET", "")

        # enabled 显式配成 false 才下线，缺失视为启用
        enabled_raw = rows.get(spec["enabled_key"], "true").strip().lower()
        is_enabled = enabled_raw not in ("false", "0", "no", "off")

        extra = {
            suffix.lower(): rows[f"{prefix}{suffix}"] for suffix in spec["extra_keys"] if rows.get(f"{prefix}{suffix}")
        }

        # 缺 app_id 视为未配置完成，从前端列表隐藏（is_enabled=False 也能隐藏，
        # 但那样 admin 里看不出是「没填」还是「主动关掉」）
        return ProviderConfig(
            name=name,
            display_name=str(spec["display_name"]),
            client_id=client_id,
            client_secret=client_secret,
            is_enabled=is_enabled and bool(client_id),
            extra=extra,
        )

    @classmethod
    def get_config(cls, name: str) -> ProviderConfig:
        if name not in cls._configs:
            # 允许运行中新增配置（例如刚跑完「初始化默认配置」）而无需重启
            config = cls._build_config(name)
            if config is None:
                raise KeyError(f"No config for provider: {name}")
            if not config.is_enabled:
                raise KeyError(f"Provider not enabled: {name}")
            cls._configs[name] = config
        return cls._configs[name]

    @classmethod
    def enabled_list(cls) -> list[dict[str, Any]]:
        """返回已启用的 Provider 列表（供前端渲染）。"""
        if not cls._configs:
            cls.load_configs()

        result: list[dict[str, Any]] = []
        for name in cls._providers:
            config = cls._configs.get(name)
            if not (config and config.is_enabled):
                continue
            instance = cls._providers[name](config)
            client_config = instance.get_client_config() or {}
            client_config["login_mode"] = instance.login_mode.value
            result.append(
                {
                    "name": name,
                    "display_name": config.display_name,
                    "client_config": client_config,
                }
            )
        return result


# 导入所有 Provider 以触发 @register 装饰器。
from . import feishu, wechat
