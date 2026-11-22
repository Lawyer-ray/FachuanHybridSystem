"""元典（yuandian）案例数据源的配置读取。

只认三个键，默认项落在 SystemConfig 的 ``enterprise_data`` 分类下（YU2 lane 按同一份
键名写默认项，本地不改名）：

``YUANDIAN_BASE_URL`` · ``YUANDIAN_API_KEYS`` · ``YUANDIAN_CONCURRENCY_PER_KEY``

读取走 :meth:`SystemConfigService.get_value`（按 key 取，和
``apps/enterprise_data/services/provider_registry.py`` 同口径），分类只是这些键的归属，
不参与读取——按分类整包读出会把同分类下别的 provider 的密钥一并解密进内存。
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field

from django.db import DatabaseError

from apps.core.services.system_config_service import SystemConfigService

logger = logging.getLogger(__name__)

CONFIG_CATEGORY = "enterprise_data"
BASE_URL_CONFIG_KEY = "YUANDIAN_BASE_URL"
API_KEYS_CONFIG_KEY = "YUANDIAN_API_KEYS"  # pragma: allowlist secret
CONCURRENCY_CONFIG_KEY = "YUANDIAN_CONCURRENCY_PER_KEY"

#: 库里没填时回落到同名环境变量（开发机/容器用，与 provider_registry 的「先读库、再回落 env」一致）。
API_KEYS_ENV_KEY = "YUANDIAN_API_KEYS"  # pragma: allowlist secret

DEFAULT_BASE_URL = "https://open.chineselaw.com"
DEFAULT_CONCURRENCY_PER_KEY = 2


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
    """多行 secret → 去空行、去重保序的元组。每行一把 key（用户明确要求换行分隔，不用 JSON）。

    与 ``provider_registry._split_secret_values`` 的去重保序口径一致；区别是本包只按行切：
    key 里可能出现逗号/分号，多切一刀就把一把 key 切成两把废 key。
    """
    if not raw_value:
        return ()
    values: list[str] = []
    seen: set[str] = set()
    for line in raw_value.splitlines():
        normalized = line.strip()
        if not normalized or normalized in seen:
            continue
        values.append(normalized)
        seen.add(normalized)
    return tuple(values)


@dataclass(frozen=True)
class YuandianConfig:
    """元典数据源的连接配置。``api_keys`` 不参与 repr，避免 key 进日志/异常栈。"""

    base_url: str = DEFAULT_BASE_URL
    api_keys: tuple[str, ...] = field(default=(), repr=False)
    concurrency_per_key: int = DEFAULT_CONCURRENCY_PER_KEY


def load_yuandian_config(*, config_service: SystemConfigService | None = None) -> YuandianConfig:
    """读一次（不缓存）：管理后台改完 key，下一次 ``open_session`` 就生效。"""
    service = config_service or SystemConfigService()
    base_url = _read_config_value(service, BASE_URL_CONFIG_KEY).rstrip("/") or DEFAULT_BASE_URL
    return YuandianConfig(
        base_url=base_url,
        api_keys=_read_api_keys(service),
        concurrency_per_key=_read_positive_int(service, CONCURRENCY_CONFIG_KEY, DEFAULT_CONCURRENCY_PER_KEY),
    )


def _read_api_keys(service: SystemConfigService) -> tuple[str, ...]:
    stored = split_secret_values(_read_config_value(service, API_KEYS_CONFIG_KEY))
    if stored:
        return stored
    return split_secret_values(os.environ.get(API_KEYS_ENV_KEY, "") or "")


def _read_positive_int(service: SystemConfigService, config_key: str, default: int) -> int:
    raw = _read_config_value(service, config_key)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "元典系统配置不是整数，使用默认值",
            extra={"config_key": config_key, "default": default},
        )
        return default
    return value if value > 0 else default


def _read_config_value(service: SystemConfigService, config_key: str) -> str:
    """读库；异常只记键名与异常类型——key 真实值不流入日志。"""
    try:
        return str(service.get_value(config_key, "") or "").strip()
    except (DatabaseError, ValueError, TypeError, AttributeError) as exc:
        logger.warning(
            "读取元典系统配置失败，使用默认值",
            extra={"config_key": config_key, "error_type": type(exc).__name__},
        )
        return ""
