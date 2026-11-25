"""按请求头裁剪 ``tools/list`` —— 给「无法自己做工具分层」的客户端用。

## 为什么需要在服务端裁剪

``mcp_server`` 注册了 434 个工具，全量 ``tools/list`` 实测 **314 KB / 约 10.2 万
token**（2026-11-25 重测；旧「244 KB / 8.3 万」系工具面扩张前的过期数），
而这份 schema 是模型**每一轮请求都要重发的固定前缀**。

pi 侧已有分层（``mcp_server/tool_tiers.py`` 的 ``toolExposure``：直连层声明给
模型，长尾走 ``tool_search`` 按需加载）。但第二个 agent 后端 dsh
（DeepSeek Harness）走不了这条路，**已实测确认**两点：

1. ``@deepseek-ai/dsh-mcp-client`` 没有工具过滤字段——给什么注册什么；
2. dsh 在会话内**不重新同步** ``tools/list``，所以「先给少量、``tool_search``
   之后动态解锁」也不成立。

于是只能在**服务端**按客户端要求裁剪：同一个 MCP 进程，pi 拿全量（它自己要
``tool_search``），dsh 拿直连层（61 个 / 44 KB / 约 1.5 万 token，2026-11-25 重测）。

## 请求头协议

``X-Fachuan-Tool-Tier``：

| 值 | ``tools/list`` 返回 |
|:-|:-|
| 不带头 | **全量**（老客户端零影响，这是兼容底线） |
| ``full`` | 全量 |
| ``lite`` | 只有直连层（``DIRECT_TOOLS`` + ``DIRECT_PATTERNS`` 命中） |
| 其它值 | 全量 + WARNING（**不 fail-closed**） |

**为什么未知值回退全量而不是空集**：拼错一个头（``Lite`` / ``lite `` 之外的
``lit``）就返回空工具集，是能想到的最坏体验——模型一个工具都没有，只会反复说
「我做不到」。全量是安全侧的默认：多花 token 但功能完整。

**为什么 ``tools/call`` 不受影响**：本中间件只改 ``tools/list`` 的返回值。
裁剪层之外的工具照样能被调用（dsh 侧靠 ``lite`` 里的入口工具，
pi 侧靠 ``tool_search``），所以裁剪**不构成权限边界**——审批仍在
``approval-gate`` 按工具全名判定。

## 实现要点（实测踩过）

- 中间件拿到的是 ``ServerRunner._serialize`` **之后**的 wire dict，不是 pydantic
  对象：必须 ``result["tools"] = [...]``；写 ``result.tools = [...]`` 静默无效。
- 请求头在 ``ctx.request.headers``（Starlette ``Request``）；stdio 模式下
  ``ctx.request`` 为 ``None``，直接走全量。
- 注册是**幂等**的：``_shared_profile`` 共享进程里若重复 import 本模块（例如
  ``__main__`` 的 HTTP 与 stdio 两条路径都走一遍），不能把同一个中间件 append
  两次（那会白跑一遍过滤，日志也会翻倍）。

## 回滚

``FACHUAN_MCP_TOOL_TIER_GATE=off`` 让中间件无条件透传全量（不改代码即可回退）。
默认 ``on``：不带头的客户端行为完全不变。
"""

from __future__ import annotations

import fnmatch
import logging
import os
from typing import Any

from mcp.server.context import CallNext, HandlerResult, ServerRequestContext

from mcp_server.tool_tiers import DIRECT_PATTERNS, DIRECT_TOOLS

logger = logging.getLogger(__name__)

#: 请求头名（HTTP 头大小写不敏感，Starlette 的 ``Headers`` 已小写化）。
TOOL_TIER_HEADER = "x-fachuan-tool-tier"

#: 开关：``off`` 时无条件全量透传。
TOOL_TIER_GATE_ENV = "FACHUAN_MCP_TOOL_TIER_GATE"

#: 只给直连层。
TIER_LITE = "lite"
#: 全量（与不带头等价，显式写法便于客户端硬编码）。
TIER_FULL = "full"
#: 支持的口径。
KNOWN_TIERS: frozenset[str] = frozenset({TIER_LITE, TIER_FULL})


def gate_enabled() -> bool:
    """中间件是否生效（默认启用；``off`` 一键回滚到全量透传）。

    与 ``tool_tiers.tiers_enabled`` 同一套值口径（``off``/``0``/``false``/``no`` 关），
    但**是两个独立开关**：一个是 pi 配置侧的分层，一个是服务端 ``tools/list``
    裁剪，回滚时需要能分别关。
    """
    raw = (os.environ.get(TOOL_TIER_GATE_ENV, "on") or "").strip().lower()
    if raw in ("off", "0", "false", "no"):
        return False
    if raw in ("on", "1", "true", "yes", ""):
        return True
    logger.warning("非法 %s=%r，回退启用工具面裁剪", TOOL_TIER_GATE_ENV, raw)
    return True


def is_direct_tool(name: str) -> bool:
    """工具是否属于直连层（精确名优先，模式按 ``*`` 通配）。

    口径与 pi 的 ``toolExposure`` 匹配一致（``tool_tiers.build_tool_exposure``）：
    精确名是真实注册名，模式覆盖 ``delete_*`` 这类破坏性工具。
    """
    if name in DIRECT_TOOLS:
        return True
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in DIRECT_PATTERNS)


def requested_tier(headers: Any) -> str:
    """从请求头解析客户端要的口径；不带头 → ``full``。

    ``headers`` 是 Starlette 的 ``Headers``（小写化 + 大小写不敏感取），也接受
    任意带 ``.get`` 的 mapping。未知值**回退 full 并 WARNING**，绝不 fail-closed。
    """
    if headers is None:
        return TIER_FULL
    raw = (headers.get(TOOL_TIER_HEADER) or "").strip().lower()
    if not raw:
        return TIER_FULL
    if raw in KNOWN_TIERS:
        return raw
    logger.warning("%s=%r 不是已知口径（支持 %s），按全量返回", TOOL_TIER_HEADER, raw, sorted(KNOWN_TIERS))
    return TIER_FULL


def filter_tools(tools: list[dict[str, Any]], tier: str) -> list[dict[str, Any]]:
    """按口径裁剪 wire 形态的工具列表（``full`` 原样返回）。"""
    if tier == TIER_FULL:
        return tools
    return [tool for tool in tools if is_direct_tool(str(tool.get("name", "")))]


class ToolTierGateMiddleware:
    """服务端工具面裁剪中间件（``(ctx, call_next) -> result``）。

    只改 ``tools/list`` 的 wire 结果，其余方法原样透传。
    """

    async def __call__(
        self,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> HandlerResult:
        result = await call_next(ctx)
        if not gate_enabled() or ctx.method != "tools/list":
            return result
        # ``_serialize`` 之后是 wire dict；pydantic 对象上赋值无效（实测踩过）。
        if not isinstance(result, dict):
            return result
        tools = result.get("tools")
        if not isinstance(tools, list):
            return result
        request = ctx.request
        tier = requested_tier(request.headers if request is not None else None)
        if tier == TIER_FULL:
            return result
        filtered = filter_tools(tools, tier)
        logger.debug("%s 裁剪 %d → %d 个工具", tier, len(tools), len(filtered))
        # 复制一层再改：``call_next`` 的返回值可能仍被别的中间件持有。
        return {**result, "tools": filtered}


#: 进程级单例：幂等挂载的判据。
_TOOL_TIER_GATE = ToolTierGateMiddleware()


def install_tool_tier_gate(server: Any) -> bool:
    """把本中间件 append 到 ``server.middleware``（幂等）。

    返回 ``True`` 表示本次真的挂上了，``False`` 表示已经在链上。用**同一个
    单例**判据，重复调用不会让过滤跑两遍。
    """
    chain = server.middleware
    if any(item is _TOOL_TIER_GATE for item in chain):
        return False
    chain.append(_TOOL_TIER_GATE)
    logger.info("工具面裁剪中间件已挂载: %s（lite=%d 个直连工具）", TOOL_TIER_GATE_ENV, len(DIRECT_TOOLS))
    return True
