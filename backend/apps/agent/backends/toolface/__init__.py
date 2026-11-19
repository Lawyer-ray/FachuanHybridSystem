"""toolface —— 「法穿工具面」的共用层：server 名、endpoint、子进程拉起。

``apps.agent.pi``、``apps.agent.backends``、``mcp_server`` 三方都依赖这层的
同一份取值，而被拆散到各处的旧写法已经漂移过：``fachuan`` 这个名字曾经有
9 份硬编码，其中审批链按 ``mcp__fachuan__<tool>`` 全名匹配——任何一处改名都会
让四级审批**静默失效**（工具照旧能调，只是不再经过人工闸门）。

约束：本包只依赖 stdlib。不许 import ``apps.agent.pi.*`` /
``backends.dsh_mcp`` / ``services.*`` / ``mcp_server.*``——``pi`` 与
``backends`` 都依赖本包，再加反向依赖即成环。

符号收敛关系（旧名一律保留为 re-export，见 ``pi/shared_mcp.py``）：

===========================  ==========================================
本包符号                     说明
===========================  ==========================================
``SERVER_NAME``              MCP server 名（审批口径的根）
``TOOL_TIMEOUT_SECONDS``     双端超时的服务端一侧（秒）
``SESSION_HEADER``           ``ask_user`` 回推用的会话标识头
``tool_prefix()``            ``mcp__<server>__``
``skill_prefix()``           ``mcp__skill__``
``McpEndpoint``              共享 MCP 地址值对象
``shared_enabled()``         ``FACHUAN_MCP_SHARED`` 解析
``endpoint_from_env()``      按环境变量解析 endpoint
``port_open()``              端口探测
``spawn_shared_server()``    拉起常驻 MCP 子进程
``wait_until_port_ready()``  同步就绪等待
===========================  ==========================================
"""

from __future__ import annotations

from .bootstrap import spawn_shared_server, wait_until_port_ready
from .constants import (
    SERVER_DESCRIPTION,
    SERVER_DISPLAY_NAME,
    SERVER_NAME,
    SESSION_HEADER,
    SESSION_ID_ENV,
    TIER_FULL,
    TIER_LITE,
    TOOL_TIER_HEADER,
    TOOL_TIMEOUT_SECONDS,
    skill_prefix,
    tool_prefix,
)
from .endpoint import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ENDPOINT_PATH,
    HOST_ENV,
    PORT_ENV,
    READY_TIMEOUT,
    SHARED_ENV,
    McpEndpoint,
    backend_dir,
    endpoint_from_env,
    mcp_log_dir,
    port_open,
    python_bin,
    shared_enabled,
)

__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "ENDPOINT_PATH",
    "HOST_ENV",
    "McpEndpoint",
    "PORT_ENV",
    "READY_TIMEOUT",
    "SERVER_DESCRIPTION",
    "SERVER_DISPLAY_NAME",
    "SERVER_NAME",
    "SESSION_HEADER",
    "SESSION_ID_ENV",
    "SHARED_ENV",
    "TIER_FULL",
    "TIER_LITE",
    "TOOL_TIMEOUT_SECONDS",
    "TOOL_TIER_HEADER",
    "backend_dir",
    "endpoint_from_env",
    "mcp_log_dir",
    "port_open",
    "python_bin",
    "shared_enabled",
    "skill_prefix",
    "spawn_shared_server",
    "tool_prefix",
    "wait_until_port_ready",
]
