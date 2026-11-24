"""元典（yuandian）接入配置的唯一读取口径。

## 可配的只有两项

元典的接入面是**稳定常量**，不随部署变，因此直接写死在本模块：

- 平台地址 ``YUANDIAN_MCP_BASE_URL``（5 个 MCP Server 都在它下面）
- 要挂进 agent 的 MCP Server 清单 ``YUANDIAN_MCP_SERVERS``
- 每把 key 的并发上限 ``YUANDIAN_CONCURRENCY_PER_KEY``（REST 检索适配器用）

放进 ``SystemConfig`` 的代价是「没点过初始化默认配置的环境里它们是空的」，
而用户对这三次填空没有任何决策价值。从系统配置读的只有：

- ``YUANDIAN_API_KEYS``：随客户变、必须加密落库（支持多把轮换）；
- ``YUANDIAN_MCP_ENABLED``：agent 侧元典 MCP 工具的总开关（工具调用会把案情发给
  外部的元典服务，律所可能要先过合规）。缺省 / 读不到都按**开启**，与「配了 key
  就挂」的既有行为一致。它只管 agent 的 MCP 工具，不管元典 REST 案例检索数据源
  ——那是律师在检索任务里显式选的 ``source``，选了就是要用。

读取走 :meth:`SystemConfigService.get_value`（按 key 取，和
``apps/enterprise_data/services/provider_registry.py`` 同口径）：分类
``enterprise_data`` 只是这些键的归属，**不参与读取**——按分类整包读出会把同分类
下别的 provider 的密钥一并解密进内存。
"""

from __future__ import annotations

import itertools
import logging
import os
import threading
from dataclasses import dataclass, field

from django.core.exceptions import SynchronousOnlyOperation
from django.db import DatabaseError

from apps.core.infrastructure.cache import CACHE_ERRORS
from apps.core.security.secret_codec import SecretCodec
from apps.core.services.system_config_service import SystemConfigService

logger = logging.getLogger(__name__)

CONFIG_CATEGORY = "enterprise_data"

API_KEYS_CONFIG_KEY = "YUANDIAN_API_KEYS"  # pragma: allowlist secret
#: 库里没填时回落到同名环境变量（开发机/容器用，与 ``provider_registry``
#: 「先读库、再回落 env」口径一致）。两者是同一个名字，刻意不做区分。
API_KEYS_ENV_KEY = API_KEYS_CONFIG_KEY

#: agent 侧元典 MCP 工具的总开关（非 secret）。取值见 :func:`yuandian_mcp_enabled`。
MCP_ENABLED_CONFIG_KEY = "YUANDIAN_MCP_ENABLED"

#: 视为「关闭」的取值（去空白、小写后比较）。其余非空值与缺省一律视为开启。
_DISABLED_VALUES = frozenset({"false", "0", "no", "off"})

#: 读系统配置时按「未配置」降级的失败类型。``get_value`` 先查缓存再查库：
#:
#: - ``CACHE_ERRORS``：缓存层的已知失败（Redis 断连、反序列化、cache 未就绪等，含
#:   ``RuntimeError``——pytest-django 拦截未授权的数据库访问也是这个类型）；
#: - ``DatabaseError``：库未迁移、连接不通；
#: - ``SynchronousOnlyOperation``：在 async 上下文里直接调用了同步 ORM。
#:
#: 不用宽口径捕获（异常棘轮门禁：全库 ``Exception`` 捕获数有上限）；
#: ``CancelledError`` 等控制流异常不在其中。注：写棘轮日志时不要把这四个词原样
#: 写进注释——它在全库数数，连注释一起算（本条就踩过）。
_READ_ERRORS: tuple[type[BaseException], ...] = (DatabaseError, SynchronousOnlyOperation, *CACHE_ERRORS)

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
    """读元典 key 池。

    本函数自己不缓存；底层 :meth:`SystemConfigService.get_value` 有 300 秒缓存。
    经管理后台保存配置时会立即清掉对应缓存，所以后台改完 key 下一次调用就生效；
    绕过后台直接改库的，最长 300 秒后生效。

    读取失败一律降级成「没有 key」，**不抛**（失败类型见 :data:`_READ_ERRORS`）；
    密文解不开（加密密钥轮换后）同样按没有 key 处理。key 缺失只应导致元典工具/
    数据源不可用，不该弄死调用方的会话。
    """
    return YuandianSettings(api_keys=_read_api_keys(config_service or SystemConfigService()))


def yuandian_mcp_enabled(*, config_service: SystemConfigService | None = None) -> bool:
    """agent 侧元典 MCP 工具是否启用（:data:`MCP_ENABLED_CONFIG_KEY`）。

    ``false`` / ``0`` / ``no`` / ``off`` 为关闭；缺省、空值、其它取值为开启。

    **读取失败按开启处理**，与 key 读失败的口径一致：开关只是「允许挂」，真正挂不挂
    还要看有没有 key；而读不到 key 时本来就不挂。缓存同 :func:`load_yuandian_settings`。
    """
    raw = _read_stored_value(config_service or SystemConfigService(), MCP_ENABLED_CONFIG_KEY)
    return raw.strip().lower() not in _DISABLED_VALUES


#: :func:`pick_api_key` 的进程内轮转计数。
#:
#: 不复用 ``apps.core.llm.key_selector.select_key``：那个计数器被所有 LLM key 选择
#: 共享，中间插进一次 LLM 选 key，两把元典 key 就可能连续两次选中同一把；元典 key
#: 也没有跨进程健康记账可供它过滤。
_ROTATION = itertools.count()
_ROTATION_LOCK = threading.Lock()


def pick_api_key(api_keys: tuple[str, ...]) -> str:
    """按进程内轮转挑一把 key（线程安全）；``api_keys`` 为空时返回空串。"""
    if not api_keys:
        return ""
    with _ROTATION_LOCK:
        index = next(_ROTATION)
    return api_keys[index % len(api_keys)]


def _read_api_keys(service: SystemConfigService) -> tuple[str, ...]:
    stored = split_api_keys(_read_stored_value(service, API_KEYS_CONFIG_KEY))
    if stored:
        return stored
    return split_api_keys(os.environ.get(API_KEYS_ENV_KEY, "") or "")


def _read_stored_value(service: SystemConfigService, config_key: str) -> str:
    """读一项系统配置；失败返回空串。日志只记键名与异常类型——配置值（含密文）不进日志。"""
    try:
        value = str(service.get_value(config_key, "") or "").strip()
    except _READ_ERRORS as exc:
        # 不记 ``config_key`` 原值：它在 CodeQL 眼里属敏感数据源
        # （py/clear-text-logging-sensitive-data，本仓库门禁阈值 0）。改记一个**布尔标记**
        # ——"这次失败的是不是 API keys 那一项"是排障时真正需要的信息，其余键靠调用栈定位。
        logger.warning(
            "读取元典系统配置失败，按未配置处理",
            extra={
                "is_api_keys": config_key == API_KEYS_CONFIG_KEY,
                "error_type": type(exc).__name__,
            },
        )
        return ""
    # ``get_value`` 解密失败时不抛，而是原样返回密文（见 ``system_config_service._maybe_decrypt``）。
    # 不拦下来，密文会被当成一把 key 发给元典，换来一条看不懂的 401。
    if SecretCodec().is_encrypted(value):
        # 同上：不带 ``config_key`` 原值（敏感数据源），改记布尔标记 + 固定分类。
        logger.warning(
            "元典系统配置解密失败（加密密钥可能已轮换），按未配置处理；请在管理后台重新保存该配置",
            extra={"is_api_keys": config_key == API_KEYS_CONFIG_KEY, "error_type": "DecryptFailed"},
        )
        return ""
    return value
