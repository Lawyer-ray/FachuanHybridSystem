"""``fachuan`` 这个 MCP server 名的唯一权威定义（以及跟着它走的几个常数）。

## 为什么这不是普通常量

这个仓库里 ``fachuan`` 同时是**四件不同事情的标识**，其中两件是安全边界：

1. **审批链的匹配口径**：四级审批按**工具全名** ``mcp__fachuan__<rawName>`` 匹配
   （``mcp_server/tool_tiers.py``、``services/approval/risk.py``）。工具注册名错了
   不会报错——工具照旧可调，只是**不再经过人工闸门**（静默失效家族）。
2. **pi 的 ``mcp.json`` server 键**（``pi/shared_mcp.py``）。键名同时决定 pi 暴露给
   模型的工具全名，所以与 1 是同一根线。
3. **dsh 的 ``mcp-client`` 命名空间**（``backends/dsh_mcp.py`` 的
   ``serverName``）：mcp-client 用 ``mcp__<serverName>__<rawName>`` 注册，
   同样落到 1 的匹配口径上。
4. **纯命名**，与安全无关：pi 的模型 provider 名（``pi/shared_mcp.py`` 的
   ``_write_settings_json``、``pi/model_config.py``）。它只是 gateway 侧的标签，
   改名不影响审批——所以刻意**不**收敛到这里，避免把「安全标识」和「展示标签」
   混成一个名字后，后来的人以为可以随便改。

因此：**要改这个名字，先读本模块与
``tests/ci/unit/agent/test_toolface.py``（跨语言不变量）**。

## 依赖禁令

本包只能依赖 stdlib。它被 ``apps.agent.pi``、``apps.agent.backends``、
``mcp_server`` 三方共用，再加业务依赖（Django / pi 会话 / MCP 工具面）就会
造出 ``backends ⇄ pi`` 与 ``mcp_server → apps`` 的双向环。
"""

from __future__ import annotations

#: MCP server 名（pi 的 ``mcp.json`` 键 / dsh 的 ``serverName`` / 工具全名前缀）。
SERVER_NAME = "fachuan"

#: 面向模型的英文名（pi 的 ``mcp_servers`` 小节与 mcp-client 的日志前缀用）。
SERVER_DISPLAY_NAME = "fachuan"

#: 面向人的一句话描述（pi 的 ``mcp.json`` 里 ``description`` 字段，
#: deferred 暴露模式下会进 system prompt）。
SERVER_DESCRIPTION = "法穿法律事务系统：案件、合同、文书、当事人、财务、期限、法规检索与自动化"

#: 单个 MCP 工具调用的超时（秒）。
#:
#: 是「双端超时」里的服务端一侧，调用方一侧必须**小于**它：
#: ``mcp_server/tools/`` 里慢链路工具自己写 ``timeout=180``（LLM 生成 / 威科 /
#: 企业数据 provider 链），pi 每请求超时若先到就会把它们掐断，client 侧的努力
#: 全部作废。200 给传输层留余量；工具发 progress notifications 可重置该计时。
#: 漂移门禁见 ``tests/ci/unit/mcp_server/test_pi_timeout_alignment.py``。
TOOL_TIMEOUT_SECONDS = 200

#: ``ask_user`` 回推提问用的会话标识请求头（小写形式）。
#:
#: ``ask_user`` 要靠它把提问推回对的 SSE 通道；缺失时返回 ``no_channel``
#: 而不是报错（提问不是闸门，问不到就让模型按假设继续）。
SESSION_HEADER = "x-fachuan-session"

#: 会话标识在 pi 子进程环境变量里的名字（``mcp.json`` 的 header 用
#: ``${FACHUAN_SESSION_ID}`` 展开，值由 ``chat_service`` 注入）。
SESSION_ID_ENV = "FACHUAN_SESSION_ID"

#: 工具面分层请求头（MCP server 读它决定 ``tools/list`` 返回多少工具）。
#:
#: ## 为什么分层要落成请求头
#:
#: pi 有自己的 ``toolExposure`` + ``deferred``（pi 私有机制）。而 dsh 的
#: ``mcp-client`` **没有任何过滤配置**，且**会话内不重新同步** ``tools/list``
#: （实测：加一个 ``tool_search`` 动态解锁也不行）。所以「给模型多少工具」
#: 只能在连接建立那一刻定下来——唯一能表达这个意图的位置就是请求头。
#:
#: 放在 toolface 而不是各写一处：它是**双端契约**（MCP server 读、dsh 写），
#: 两处各写一个字符串就是漂移的起点——头名拼错时 MCP 会当成「没带」而返回
#: **全量**，表现为「分层配置了却没生效」，没有任何报错。
TOOL_TIER_HEADER = "x-fachuan-tool-tier"

#: ``TOOL_TIER_HEADER`` 的取值：只用 ``DIRECT_TOOLS`` + ``DIRECT_PATTERNS``
#: （实测 61 个工具 / 33KB / 1.1 万 token）。
TIER_LITE = "lite"

#: 全量工具面（424 个 / 244KB / 8.3 万 token）。不带头时的默认行为。
TIER_FULL = "full"


def tool_prefix(server_name: str = SERVER_NAME) -> str:
    """工具全名前缀 ``mcp__<server_name>__``（审批与 ``--tools`` 白名单共用口径）。"""
    return f"mcp__{server_name}__"


def skill_prefix() -> str:
    """skill 工具全名前缀 ``mcp__skill__``（与业务 MCP server 分开命名空间）。"""
    return tool_prefix("skill")
