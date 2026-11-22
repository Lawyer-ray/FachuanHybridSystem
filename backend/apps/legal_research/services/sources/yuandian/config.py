"""元典（yuandian）案例数据源的配置。

**key 的唯一读取口径是** :mod:`apps.core.services.yuandian_settings`：本模块只把那里
的 :class:`~apps.core.services.yuandian_settings.YuandianSettings` 转成检索适配器要的
形状（:class:`YuandianConfig`），并保留 ``client.py`` 与测试引用的既有符号名。

平台地址与并发上限已提为代码常量（``YUANDIAN_MCP_BASE_URL`` /
``YUANDIAN_CONCURRENCY_PER_KEY``）：它们不随部署变，历史实现从 SystemConfig 读，
结果多出一个「没初始化就是空」的失败面。分类 ``CONFIG_CATEGORY`` 仍保留——
``YUANDIAN_API_KEYS`` 的默认项挂在这个分类下。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from apps.core.services.system_config_service import SystemConfigService
from apps.core.services.yuandian_settings import (
    API_KEYS_CONFIG_KEY,
    API_KEYS_ENV_KEY,
    CONFIG_CATEGORY,
    YUANDIAN_CONCURRENCY_PER_KEY,
    YUANDIAN_MCP_BASE_URL,
    load_yuandian_settings,
    split_api_keys,
)

__all__ = [
    "API_KEYS_CONFIG_KEY",
    "API_KEYS_ENV_KEY",
    "CONFIG_CATEGORY",
    "YuandianConfig",
    "YuandianConfigError",
    "key_label",
    "load_yuandian_config",
    "split_secret_values",
]


class YuandianConfigError(RuntimeError):
    """元典数据源配置不可用（目前只有「一把 key 都没有」这一种）。"""


_ALIASES: dict[str, str] = {}
_ALIAS_LOCK = threading.Lock()


def key_label(api_key: str) -> str:
    """key 的短标签（可安全进日志）。空 key 给 ``(empty)``。

    返回形如 ``key-1`` 的**进程内别名**：同一把 key 同一标签，标签本身不携带 key 的
    任何信息。与 ``apps/agent/backends/key_scheduler.fingerprint`` 同口径——这里刻意
    不用哈希，因为「快速哈希 + 敏感数据」会被安全扫描判为不安全的秘密派生（CodeQL
    ``py/weak-sensitive-data-hashing``），而别名既过静态检查也留不下可离线爆破的材料。
    """
    text = (api_key or "").strip()
    if not text:
        return "(empty)"
    with _ALIAS_LOCK:
        alias = _ALIASES.get(text)
        if alias is None:
            alias = f"key-{len(_ALIASES) + 1}"
            _ALIASES[text] = alias
        return alias


def split_secret_values(raw_value: str) -> tuple[str, ...]:
    """历史名（本模块与既有测试在用）；实现见 :func:`yuandian_settings.split_api_keys`。"""
    return split_api_keys(raw_value)


@dataclass(frozen=True)
class YuandianConfig:
    """元典数据源的连接配置。``api_keys`` 不参与 repr，避免 key 进日志/异常栈。"""

    base_url: str = YUANDIAN_MCP_BASE_URL
    api_keys: tuple[str, ...] = field(default=(), repr=False)
    concurrency_per_key: int = YUANDIAN_CONCURRENCY_PER_KEY


def load_yuandian_config(*, config_service: SystemConfigService | None = None) -> YuandianConfig:
    """读一次（不缓存）：管理后台改完 key，下一次 ``open_session`` 就生效。

    key 来自 :func:`load_yuandian_settings`（读库失败降级成空 key，交给
    ``open_session`` 抛 :class:`YuandianConfigError` 说清「没配 key」）；
    地址与并发上限取上面两个常量的默认值。
    """
    settings = load_yuandian_settings(config_service=config_service)
    return YuandianConfig(api_keys=settings.api_keys)
