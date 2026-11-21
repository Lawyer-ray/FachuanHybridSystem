"""给 dsh 接上法穿的 423 个 MCP 业务工具（生成 mcp-client 的 patch 层）。

## 为什么必须自己写 patch（不是 ``dsh plugin add`` 一下就好）

官方 ``@deepseek-ai/dsh-mcp-client`` **不声明 ``dsh.bundle``**，``dsh plugin add``
装完只会得到一句 ``installed as a plain dependency, not a profile layer``——
插件在 profile 的 ``node_modules`` 里，但**不会被加载**。要让它成为一个层，
只能自己往组合树里 ``insert`` 一条：

.. code-block:: yaml

    - insert:
        - id: mcp-fachuan
          name: '@deepseek-ai/dsh-mcp-client'
          config:
            serverName: fachuan
            transport: streamable-http
            url: http://127.0.0.1:8011/mcp
            headers:
              Authorization: Bearer <律师 token>

``serverName: fachuan`` 是**硬约束**：mcp-client 把工具注册成
``mcp__<serverName>__<rawName>``（见 ``lib/types/tools.d.ts`` 的
``publicToolName``），只有这个名字才能让现网的四级审批
（按 ``mcp__fachuan__delete_case`` 这类全名匹配）原样命中。换成别的名字，
审批链会静默失效——工具仍能调，但**不再经过人工闸门**。

## 为什么要先 ``ensure_shared_server()``

:8011 **不是「部署就有」**：``mcp_server`` 的共享实例只在有人 `pool.acquire()`
（即有人用 Copilot）时才被拉起，``AppConfig.ready()`` 里没有任何启动逻辑
（见 ``docs/04-计划/活跃/dsh-plugin-evaluation.md`` §11.1）。没人用过 Copilot
时 dsh 连 :8011 会 ``ECONNREFUSED``，而 mcp-client 默认
``failOnStartupError: false`` → **静默地一个工具都没有**，只在 dsh 自己的日志里
留一行 ``mcp-client(fachuan): startup failed``。

所以这里在写 patch 之前先同步地 ensure 一把（与 ``pi/pool.py`` 每次 acquire 时
自愈的口径一致），新拉实例等它 ready（冷启动实测 ~6s）才放行。

## token 只进文件，不进日志

``headers.Authorization`` 是**律师本人的 access token**（混淆代理修复，见
``pi/user_token.py``），泄漏等于把该律师的业务数据读权限交出去。因此：

- 文件权限 ``0600``，且用 ``os.open`` 的 mode 参数原子创建（不是先建 0644 再 chmod）；
- 任何日志只写 token 的长度/是否为空，绝不写值；
- 贴错位置的服务器名/URL 可以打日志，token 不行。

## 工具面：全量 vs 高频

mcp-client 的 config schema 里**没有** ``tools`` / ``include`` / ``exclude``
这类过滤字段（``lib/types/index.d.ts`` 的两个分支只有 transport / serverName /
url / headers / toolCallTimeoutMs / failOnStartupError）。它在
``syncTools`` 里无条件把服务器给的整份 ``tools/list`` 全注册进 ToolRegistry。
所以「只暴露 ~30 个高频工具」在 dsh 这一层做不到——要么全量进上下文，
要么在 MCP server 侧另起一个裁剪过的 serverName。实测数字见
``docs/04-计划/活跃/dsh-python-sdk-integration.md`` §3.4。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from ..pi import shared_mcp as shared_mcp_module
from ..pi.shared_mcp import ensure_shared_server
from .toolface import (
    SERVER_NAME,
    SESSION_HEADER,
    TIER_LITE,
    TOOL_TIER_HEADER,
    TOOL_TIMEOUT_SECONDS,
    McpEndpoint,
    shared_enabled,
)

logger = logging.getLogger(__name__)

#: 单个 MCP 工具调用的超时（毫秒）。mcp-client 默认 60s，而法穿的文书生成 /
#: 批量类工具自己就是 180s（``mcp_server`` 侧 ``timeout=180``），默认值会先把
#: 它们掐断。200s 与 pi 的 ``mcp.json`` 同口径（双端超时必须调用方 > 服务端），
#: 所以直接从 ``toolface.TOOL_TIMEOUT_SECONDS`` 换算——两边各写一个数就是漂移的
#: 起点（历史：pi 侧 200 / dsh 侧另写 200_000）。
TOOL_CALL_TIMEOUT_MS = TOOL_TIMEOUT_SECONDS * 1000

__all__ = [
    "PATCH_FILENAME",
    "SERVER_NAME",
    "TOOL_CALL_TIMEOUT_MS",
    "ensure_mcp_patch",
    "ensure_shared_server",
    "patch_body",
]

#: patch 文件名。放在 dsh home 下是因为它是每次启动都要用的稳定配置，且**含
#: 真实 token**：临时目录会被清掉（下次启动静默失去工具），而 /tmp 上的可预测
#: 路径 + 默认权限会把它泄露给本机其他用户。
PATCH_FILENAME = "fachuan-mcp.patch.yml"


def _resolve_endpoint() -> McpEndpoint:
    """读共享 MCP 的 endpoint（**每次调用都去模块属性上取**，不在 import 时绑定）。

    写成函数而不是在 ``ensure_mcp_patch`` 里直接调 ``resolve_endpoint()``：后者会
    在 import 期把函数对象固化到本模块命名空间，替换 ``shared_mcp.resolve_endpoint``
    （测试 / 验收脚本把 :8011 换成假服务器的手法）就对这里不生效——表现是
    「patch 里写的是 :8011，脚本却以为接上了假服务器」，最容易把验证变成假绿。
    """
    endpoint: McpEndpoint = shared_mcp_module.resolve_endpoint()
    return endpoint


def _quoted(value: str) -> str:
    """YAML 双引号字符串（转义 ``\\`` 与 ``"``，其余原样）。

    不用 ``yaml.safe_dump``：整个 patch 是几行固定结构，手工拼比「构造 dict 再
    序列化」更可读；而 token 里可能出现 ``:`` / ``#`` / 前导空格，所以值一律
    加引号，不能裸写。
    """
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _write_private(path: Path, content: str) -> None:
    """以 ``0600`` 原子写入（先写临时文件再 ``os.replace``）。

    为什么不用 ``path.write_text``：它是「按 umask 创建（通常 0644）→ 写内容」，
    在中间那一刻 token 对本机其他用户可读；而且内容写一半崩溃会留下半截 YAML，
    dsh 读到会启动失败。
    """
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)  # 旧文件可能已存在且权限更宽，显式收紧
        os.write(fd, content.encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(tmp, path)


#: 工具面分层开关（``off`` 一键回到全量）。与 MCP server 侧
#: ``FACHUAN_MCP_TOOL_TIER_GATE`` 分开：那个是服务端总闸（关掉等于谁都不分层），
#: 这个是**本客户端**要不要声明 lite——两者都开才真的分层，便于单侧回滚。
_TIER_ENV = "FACHUAN_DSH_TOOL_TIER"


def _tool_tier() -> str:
    """本轮要声明的工具面档位。

    只在值明确为 ``off`` 式写法时退回全量；其余一律 ``lite``——默认收紧而不是
    默认放开，因为「多给模型 400 个工具」的成本是每轮 8.3 万 token，而「少给」
    最多是模型说一句「我没有这个能力」，后者用户能感知、前者只有账单能看到。
    """
    raw = (os.environ.get(_TIER_ENV, "") or "").strip().lower()
    if raw in ("off", "0", "false", "no", "full"):
        return "full"
    return TIER_LITE


def patch_body(endpoint: McpEndpoint, user_token: str, *, session_id: str = "") -> str:
    """生成 patch 文件内容（纯函数，便于测试与单测断言）。

    为什么 ``failOnStartupError: true``：默认的 ``false`` 会把「连不上 / 401」
    变成「静默无工具」——模型照常回答，只是答不出业务数据，且用户看不出原因。
    打开它以后插件激活失败会让本轮回退到 ``BackendError(UNAVAILABLE)``，
    用户看到的是「后端不可用」，运维在日志里看到 ``mcp-client(fachuan):
    startup failed: ...``。法务场景里「装作能查但查不到」比「明确报错」危险得多。
    """
    return "\n".join(
        [
            "# 由 apps.agent.backends.dsh_mcp 生成——不要手改（含真实律师 token）",
            "# 作用：让 dsh 通过 @deepseek-ai/dsh-mcp-client 连上法穿共享 MCP（:8011）",
            "- insert:",
            "    - id: mcp-fachuan",
            "      name: '@deepseek-ai/dsh-mcp-client'",
            "      config:",
            f"        serverName: {SERVER_NAME}",
            "        transport: streamable-http",
            f"        url: {_quoted(endpoint.url)}",
            "        headers:",
            f"          Authorization: {_quoted(f'Bearer {user_token}')}",
            # 会话标识（与 pi 同源头名，HTTP 头大小写不敏感）：MCP 服务端的审批闸门
            # 靠它把审批卡投到正确的会话、并把「谁在等」写成 AgentApproval.session。
            # 不带时审批网关只能建无会话单（只有超管能批）→ 等于高危工具全拒。
            *([f"          {SESSION_HEADER}: {_quoted(session_id)}"] if session_id else []),
            # 工具面分层（2026-11-19）：让 MCP server 只返回 direct 层工具。
            #
            # **为什么必须由 dsh 这一侧声明**：dsh 的 mcp-client 会把
            # `tools/list` 返回的每个工具都注册给模型，且**会话内不重新同步**
            # （实测：加 tool_search 动态解锁也不行，见
            #  docs/04-计划/活跃/工具面分层方案.md）。所以「给多少」
            # 必须在连接建立那一刻就定下来，唯一能表达这个意图的位置是请求头。
            #
            # 实测收益：424 个工具 244KB / 8.3 万 token → 61 个 33KB / 1.1 万。
            #
            # 不带这个头 = 全量（MCP server 侧的兼容底线），所以老客户端与
            # 手工调试仍然看到完整工具面。
            f"          {TOOL_TIER_HEADER}: {_quoted(_tool_tier())}",
            f"        toolCallTimeoutMs: {TOOL_CALL_TIMEOUT_MS}",
            "        failOnStartupError: true",
            "",
        ]
    )


def ensure_mcp_patch(dsh_home: str, *, user_token: str, session_id: str = "", wait_ready: bool = True) -> str | None:
    """确保 :8011 在跑并写出 mcp patch，返回 patch 文件路径。

    同步函数：调用方（``dsh_config.build_config``）本身就在线程里跑（它要读同步
    ORM），所以这里可以直接用阻塞的 ``ensure_shared_server``。

    Args:
        dsh_home: 该用户的 dsh home（``dsh_home_for`` 的结果）。
        user_token: 律师 access token。**不得写进日志**。
        wait_ready: 新拉共享 MCP 时是否等到端口可连。测试传 ``False``。

    Returns:
        patch 文件的绝对路径；**没有 token 时返回 ``None``**。

        无 token（``user_id`` 为空：测试 / 后台任务）不写 patch 是刻意的：
        :8011 在 HTTP 模式下强制 Bearer（``mcp_server/identity.py``），且
        **刻意不回退服务账号**（2026-10-28 限权修复）。写了 patch 也只会让
        dsh 以 401 失败、把「本来能对话」变成「启动失败」。所以降级为
        「无工具但能对话」，并留一条 warning——这是用户可感知的能力缺失
        （模型查不到业务数据），按日志口径至少是 warning。
    """
    token = (user_token or "").strip()
    if not token:
        logger.warning("dsh 本轮没有律师 token，无法接入法穿 MCP 工具（无工具但可对话）")
        return None

    endpoint = _resolve_endpoint()
    if shared_enabled():
        # 幂等：端口在就秒回。失败只降级（dsh 侧 failOnStartupError 会把
        # 「连不上」报成后端不可用），不在这里抛——那会把「工具面缺失」
        # 升级成「整轮对话失败」，而模型本身是能跑的。
        try:
            # ``ensure_shared_server`` 必须继续作为**本模块的顶层符号**存在：
            # ``test_dsh_mcp.py`` 用 ``monkeypatch.setattr(dsh_mcp,
            # "ensure_shared_server", ...)`` 挡住真起子进程，符号消失就是
            # 静默失效 → 真拉起一个 ~225MB 的 MCP 子进程。所以这里调用的是
            # 「本模块命名空间里的那个名字」（运行时按 globals 解析），而不是
            # 再套一层 ``shared_mcp_module.`` 前缀。
            ensure_shared_server(endpoint, wait_ready=wait_ready)
        except OSError:
            logger.warning("拉起共享 MCP 失败，dsh 本会话将无业务工具", exc_info=True)
    else:
        # ``FACHUAN_MCP_SHARED=0`` 时 pi 各自起 stdio，而 dsh 这份 patch 只认
        # HTTP endpoint。如实提示，而不是让用户以为工具接上了。
        logger.warning("共享 MCP 已禁用（FACHUAN_MCP_SHARED=0），dsh 本会话无业务工具")
        return None

    if not _port_open(endpoint):
        # 不必在这里 raise：mcp-client 的 failOnStartupError 会把这件事变成
        # 明确的启动失败，比我们猜「是不是还在冷启动」更准。
        logger.warning("共享 MCP %s 当前不可连，dsh 启动时可能报插件激活失败", endpoint.url)

    path = Path(dsh_home) / PATCH_FILENAME
    try:
        _write_private(path, patch_body(endpoint, token, session_id=session_id))
    except OSError:
        logger.warning("写入 dsh MCP patch 失败：%s（本会话无业务工具）", path, exc_info=True)
        return None
    # 只记长度，绝不记取值。
    logger.info("dsh MCP patch 已写入 %s（endpoint=%s token 长度=%s）", path, endpoint.url, len(token))
    return str(path)


def _port_open(endpoint: McpEndpoint) -> bool:
    """探测 endpoint 是否可连（同样走模块属性，理由见 :func:`_resolve_endpoint`）。"""
    probe: Any = shared_mcp_module.port_open
    return bool(probe(endpoint.host, endpoint.port))
