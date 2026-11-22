"""元典（yuandian）接入配置的唯一读取口径。

## 只有 API Key 是可配的

元典的接入面是**稳定常量**，不随部署变，因此直接写死在本模块：

- 平台地址 ``YUANDIAN_MCP_BASE_URL``（5 个 MCP Server 都在它下面）
- 要挂进 agent 的 MCP Server 清单 ``YUANDIAN_MCP_SERVERS``
- 每把 key 的并发上限 ``YUANDIAN_CONCURRENCY_PER_KEY``（REST 检索适配器用）

放进 ``SystemConfig`` 的代价是「没点过初始化默认配置的环境里它们是空的」，
而用户对这三次填空没有任何决策价值。真正随客户变、且必须加密落库的只有
``YUANDIAN_API_KEYS``（支持多把轮换），它仍从系统配置读。

读取走 :meth:`SystemConfigService.get_value`（按 key 取，和
``apps/enterprise_data/services/provider_registry.py`` 同口径）：分类
``enterprise_data`` 只是这些键的归属，**不参与读取**——按分类整包读出会把同分类
下别的 provider 的密钥一并解密进内存。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from django.db import DatabaseError

from apps.core.services.system_config_service import SystemConfigService

logger = logging.getLogger(__name__)

CONFIG_CATEGORY = "enterprise_data"

API_KEYS_CONFIG_KEY = "YUANDIAN_API_KEYS"  # pragma: allowlist secret
#: 库里没填时回落到同名环境变量（开发机/容器用，与 ``provider_registry``
#: 「先读库、再回落 env」口径一致）。两者是同一个名字，刻意不做区分。
API_KEYS_ENV_KEY = API_KEYS_CONFIG_KEY

#: 元典开放平台地址。MCP Server 地址为 ``<base>/mcp/<名称>/stream``。
YUANDIAN_MCP_BASE_URL = "https://open.chineselaw.com"

#: 要挂进 pi ``mcp.json`` 的元典 MCP Server（工具数：law 5 / case 4 / company 26 / securities 6）。
#:
#: **不要往里加 ``hallucination``**：那个 server 仅 VIP 账号可用，非 VIP 挂上去
#: 只会让每条 ``tools/list`` 都认证失败，给模型凭空造出一批查不了的工具。
YUANDIAN_MCP_SERVERS: tuple[str, ...] = ("law", "case", "company", "securities")

#: 元典按 key 限流（实测并发超限回 429）。REST 检索适配器按此上限开并发槽位。
YUANDIAN_CONCURRENCY_PER_KEY = 2


def split_api_keys(raw_value: str) -> tuple[str, ...]:
    """多行 key 文本 → 去空行、去重保序的元组。每行一把 key（用户明确要求换行分隔，不用 JSON）。

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
class YuandianSettings:
    """元典接入里**唯一**可配的东西：API Key 池。

    ``api_keys`` 不参与 repr，避免 key 进日志/异常栈。
    """

    api_keys: tuple[str, ...] = field(default=(), repr=False)


def load_yuandian_settings(*, config_service: SystemConfigService | None = None) -> YuandianSettings:
    """读一次（不缓存）：管理后台改完 key，下一次调用就生效。

    读库失败一律降级成「没有 key」，**不抛**——典型失败包括在 async 上下文直接
    调用（``SynchronousOnlyOperation``）、库未迁移、连接不通。key 缺失只应导致
    元典工具/数据源不可用，不该弄死调用方的会话。
    """
    return YuandianSettings(api_keys=_read_api_keys(config_service or SystemConfigService()))


def _read_api_keys(service: SystemConfigService) -> tuple[str, ...]:
    stored = split_api_keys(_read_stored_value(service))
    if stored:
        return stored
    return split_api_keys(os.environ.get(API_KEYS_ENV_KEY, "") or "")


def _read_stored_value(service: SystemConfigService) -> str:
    """读库；日志只记键名与异常类型——key 真实值（含密文）不流入日志。"""
    try:
        return str(service.get_value(API_KEYS_CONFIG_KEY, "") or "").strip()
    except (DatabaseError, ValueError, TypeError, AttributeError) as exc:
        logger.warning(
            "读取元典系统配置失败，按未配置处理",
            extra={"config_key": API_KEYS_CONFIG_KEY, "error_type": type(exc).__name__},
        )
        return ""
