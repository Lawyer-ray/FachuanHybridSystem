"""共享 MCP server 管理。

## 为什么必须共享

实测（macOS / Python 3.12 / 本仓库 mcp_server）：

- 单个 ``python -m mcp_server`` 常驻内存约 **225 MB**
- 冷启动到可服务约 **6 秒**

若每个 pi 进程各起一份 stdio MCP：

- 20 并发 → 20 × 225MB ≈ **4.5 GB**，且每路首响应都要等 6 秒以上
- 每次工具调用跨 3 层进程（Django → pi → mcp_server）

改成「一份常驻 + N 个 pi 通过 HTTP 连」：

- 内存固定 1 份（~225MB），与并发数解耦
- 冷启动只发生一次（应用启动 / 首次使用时预热）
- pi 连 HTTP endpoint，启动快

## 部署形态

    Django 启动
      └─ 确保共享 MCP 在 http://127.0.0.1:<port>/mcp 待命

    pi 进程（N 个）
      └─ .pi/mcp.json 指向该 endpoint（type: streamable_http）

## 降级

``FACHUAN_MCP_SHARED=0`` 时退回 stdio 模式：每个 pi 各起一份，
牺牲内存换部署简单。默认**启用共享**。
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

SHARED_ENV = "FACHUAN_MCP_SHARED"
PORT_ENV = "FACHUAN_MCP_HTTP_PORT"
HOST_ENV = "FACHUAN_MCP_HTTP_HOST"
DEFAULT_PORT = 8011
DEFAULT_HOST = "127.0.0.1"
ENDPOINT_PATH = "/mcp"
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


def resolve_endpoint() -> McpEndpoint:
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


async def wait_until_ready(endpoint: McpEndpoint, timeout: float = READY_TIMEOUT) -> bool:
    """等待共享 MCP 端口可连。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if await asyncio.to_thread(port_open, endpoint.host, endpoint.port):
            return True
        await asyncio.sleep(0.3)
    return False


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[3]


def _python_bin() -> str:
    candidate = _backend_dir() / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return os.environ.get("PYTHON", "python3")


def spawn_shared_server(endpoint: McpEndpoint) -> subprocess.Popen[bytes] | None:
    """以 streamable-http 方式拉起共享 MCP（独立进程，与 Django 解耦）。

    Returns:
        子进程句柄；端口已被占用（已有实例在跑）时返回 ``None``。
    """
    if port_open(endpoint.host, endpoint.port):
        logger.info("共享 MCP 已在 %s 运行，复用现有实例", endpoint.url)
        return None

    env = {
        **os.environ,
        "FACHUAN_MCP_TRANSPORT": "streamable-http",
        "FACHUAN_MCP_HTTP_HOST": endpoint.host,
        "FACHUAN_MCP_HTTP_PORT": str(endpoint.port),
    }
    logger.info("拉起共享 MCP: %s", endpoint.url)
    return subprocess.Popen(
        [_python_bin(), "-m", "mcp_server"],
        cwd=str(_backend_dir()),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def ensure_shared_server(endpoint: McpEndpoint | None = None) -> McpEndpoint:
    """确保共享 MCP 在跑；返回可用的 endpoint。

    同步版本，供 Django ``AppConfig.ready()`` 或管理命令调用。
    不等待就绪（就绪由 pi 侧连接时自然等待），避免拖慢启动。
    """
    resolved = endpoint or resolve_endpoint()
    if not shared_enabled():
        logger.info("共享 MCP 已禁用（%s=0），pi 将各自启动 stdio MCP", SHARED_ENV)
        return resolved
    spawn_shared_server(resolved)
    return resolved


def write_pi_mcp_config(target_dir: str | Path, endpoint: McpEndpoint | None = None) -> Path:
    """写出 pi 侧 ``.pi/mcp.json``。

    共享模式写 streamable-http 指向共享实例；非共享模式写 stdio 自起。
    """
    import json

    resolved = endpoint or resolve_endpoint()
    target = Path(target_dir) / ".pi"
    target.mkdir(parents=True, exist_ok=True)
    config_path = target / "mcp.json"

    if shared_enabled():
        server = {"type": "streamable-http", "url": resolved.url}
    else:
        server = {
            "command": _python_bin(),
            "args": ["-m", "mcp_server"],
            "cwd": str(_backend_dir()),
        }

    config_path.write_text(
        json.dumps({"mcpServers": {"fachuan": server}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return config_path
