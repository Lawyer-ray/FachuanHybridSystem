"""Admin-facing helpers for system config defaults.

This compatibility service keeps legacy import paths working while delegating
to the current admin data provider.

它同时是「界面上那句配置说明从哪来」的唯一权威：`code_description_of()` 读**代码**里
登记的默认说明；`SystemConfig.description` 那列只在「代码里没有这个键」时兜底。
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from apps.core.admin._system_config_data import get_default_configs


@lru_cache(maxsize=1)
def _code_descriptions() -> dict[str, str]:
    """key → 代码里登记的说明。

    全量默认配置在进程内只遍历一次：这个索引每个 changelist / change 请求都要用，
    而 `get_default_configs()` 会把 9 个分类的列表全部重新构造一遍。
    """
    return {str(item["key"]): str(item.get("description") or "") for item in get_default_configs() if item.get("key")}


def clear_code_description_cache() -> None:
    """丢掉索引缓存。

    只有测试需要（它们用 monkeypatch 改种子数据来验证「代码文案变了界面跟着变」）；
    运行时种子是常量，天然不需要清。
    """
    _code_descriptions.cache_clear()


def code_description_of(key: str) -> str | None:
    """代码里登记的默认说明；该键不在代码里时返回 None。

    为什么以代码为准：`init_defaults_view` 用 `get_or_create(key=..., defaults=...)`，
    **已存在的行一个字段都不会更新**。所以库里的 `SystemConfig.description` 随时可能
    是旧文案（dev/线上那份不会被代码改动刷新，甚至可能被手改过），只能当兜底。
    """
    return _code_descriptions().get(str(key or "")) or None


class SystemConfigAdminService:
    """Service facade used by tests/admin callers for default config payloads."""

    def get_default_configs(self) -> list[dict[str, Any]]:
        defaults = get_default_configs()
        sanitized: list[dict[str, Any]] = []
        for item in defaults:
            copied = dict(item)
            key = str(copied.get("key") or "")
            is_secret = bool(copied.get("is_secret", False))
            if is_secret or re.search(r"(API_KEY|APP_SECRET|SECRET|TOKEN|PASSWORD)$", key):
                copied["value"] = ""
            sanitized.append(copied)
        return sanitized
