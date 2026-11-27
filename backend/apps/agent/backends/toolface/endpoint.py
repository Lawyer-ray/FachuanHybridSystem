"""共享 MCP endpoint 的值对象与环境解析（后端无关）。

## 为什么这一层要独立

``pi`` 与 ``dsh`` 两个后端连的是**同一个常驻进程**（``python -m mcp_server``，
见 ``pi/shared_mcp.py`` 的模块 docstring）：一份 ~225MB、冷启动 ~6s，所以全局
只起一份、两边都指向它。endpoint 的「主机/端口从哪来、URL 怎么拼、开关怎么读」
是纯粹的环境解析，与「谁来拉起进程」无关，放在这里让 ``backends`` 侧不必
import ``pi``（否则 ``backends ⇄ pi`` 成环）。

## 只依赖 stdlib

``dataclass`` / ``os`` / ``socket`` / ``pathlib`` 之外不许 import 任何本仓库模块。
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path

#: 共享 MCP 开关：``0`` / ``false`` / ``no`` / ``off`` 退回 stdio（每 pi 一份）。
SHARED_ENV = "FACHUAN_MCP_SHARED"
PORT_ENV = "FACHUAN_MCP_HTTP_PORT"
HOST_ENV = "FACHUAN_MCP_HTTP_HOST"
DEFAULT_PORT = 8011
DEFAULT_HOST = "127.0.0.1"
ENDPOINT_PATH = "/mcp"

#: django-q / AppConfig 侧拉起共享 MCP 后等端口可连的上限（秒）。
#: 冷启动实测 ~6s，30s 留足了慢机器余量。
READY_TIMEOUT = 30.0


@dataclass(slots=True)
class McpEndpoint:
    """共享 MCP 的连接信息。"""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}{ENDPOINT_PATH}"


def shared_enabled() -> bool:
    """是否启用共享 MCP（默认启用）。"""
    raw = os.environ.get(SHARED_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def endpoint_from_env() -> McpEndpoint:
    """按环境变量解析 endpoint（**不是** ``resolve_endpoint``，见下）。

    改名原因：``pi.shared_mcp.resolve_endpoint`` 是个**可被替换的间接层**
    （``scripts/verify_dsh_mcp.py`` / 测试把 :8011 换成假服务器的手法），
    两个同名函数放一起会让替换看起来「只生效一半」。这里叫 ``endpoint_from_env``
    表明它只读环境；``pi.shared_mcp.resolve_endpoint`` 保留原名并转调本函数。
    """
    host = os.environ.get(HOST_ENV, DEFAULT_HOST).strip() or DEFAULT_HOST
    try:
        port = int(os.environ.get(PORT_ENV, DEFAULT_PORT))
    except ValueError:
        port = DEFAULT_PORT
    return McpEndpoint(host=host, port=port)


def port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """探测端口是否可连。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def agent_home() -> Path:
    """运行时状态的稳定根目录（默认 ``~/.fachuan-agent``，``FACHUAN_AGENT_HOME`` 可覆盖）。

    ## 为什么在本模块重新实现而不 import ``pi.session_store.agent_home``

    ``pi`` 依赖本包（``pi/rpc_client.py`` / ``pi/shared_mcp.py`` 都 import
    ``backends.toolface``），反过来 import 就成环。取值规则必须与
    ``pi.session_store.agent_home()`` **逐字一致**（同一个环境变量、同一个默认
    目录、同样 ``expanduser``），由 ``tests/ci/unit/agent/test_toolface.py``
    钉住两者不漂移。

    与 ``pi.session_store.agent_home()`` 的差异只有一处、且刻意：本函数**不建目录、
    不改权限**。它被 ``/agent/backends`` 这类只读探测路径调用，在只读文件系统或
    权限不足的部署里 mkdir 会抛错，把「能不能用」的探测变成 500。需要写盘的
    调用方自己 ``mkdir(parents=True, exist_ok=True)`` 并收权限。
    """
    raw = os.environ.get("FACHUAN_AGENT_HOME", "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".fachuan-agent"


def mcp_log_dir() -> Path:
    """共享 MCP 日志目录（``<agent home>/logs``，0700）。

    走 :func:`agent_home` 而不是自己再读一次环境变量：两处各读一次就会在
    「一个改了另一个没改」时把日志写到两个地方，而这种漂移没有任何报错。
    """
    return agent_home() / "logs"


def backend_dir() -> Path:
    """``backend/`` 目录（``mcp_server`` 包的父目录，spawn 的 cwd 与 venv 的位置）。

    本文件位于 ``<backend>/apps/agent/backends/toolface/endpoint.py``，
    所以 ``parents[4]`` 就是 ``<backend>``。
    """
    return Path(__file__).resolve().parents[4]


def python_bin() -> str:
    """拉起子进程用的解释器：优先 ``backend/.venv/bin/python``，否则 ``$PYTHON``。"""
    candidate = backend_dir() / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return os.environ.get("PYTHON", "python3") or "python3"
