"""拉起 / 就绪等待共享 MCP 子进程（pi 与 dsh 共用同一套）。

进程形态：一份常驻的 ``python -m mcp_server``（streamable-http），两个后端都
连它。为什么必须共享、为什么不能每会话 stdio 一份，见
``pi/shared_mcp.py`` 的模块 docstring（225MB / 冷启动 ~6s 的实测数字）。

## 为什么日志目录是参数而不是自己算

本模块不能 import ``pi.session_store.agent_home()``——``pi`` 依赖本包，
反向 import 直接成环。所以 ``log_dir`` 由调用方注入：``pi.shared_mcp`` 传
``agent_home() / "logs"``，其它调用方传自己的目录。默认值走
:func:`toolface.endpoint.mcp_log_dir`，只读环境变量，不碰任何业务模块。
"""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import IO

from .endpoint import McpEndpoint, backend_dir, mcp_log_dir, port_open, python_bin

logger = logging.getLogger(__name__)

#: 本进程拉起的共享 MCP 子进程句柄。崩溃复活靠下次 spawn 重新拉起，
#: 已退出的旧句柄在这里 poll 回收（waitpid WNOHANG），不留僵尸。
_spawned_procs: list[subprocess.Popen[bytes]] = []


def _reap_exited_procs() -> None:
    for proc in list(_spawned_procs):
        if proc.poll() is not None:
            _spawned_procs.remove(proc)


def spawn_shared_server(
    endpoint: McpEndpoint,
    *,
    log_dir: Path | None = None,
    cwd: Path | None = None,
    python: str | None = None,
) -> subprocess.Popen[bytes] | None:
    """以 streamable-http 方式拉起共享 MCP（独立进程，与 Django 解耦）。

    Args:
        endpoint: 要绑定的地址（也是被探测是否已有实例的地址）。
        log_dir: stderr 日志目录；缺省走 :func:`toolface.endpoint.mcp_log_dir`。
            目录以 ``0700`` 语义创建，日志文件 ``0600``（可能含业务数据）。
        cwd: 子进程工作目录（``mcp_server`` 可 import 的前提）；缺省为
            ``backend/``。
        python: 解释器路径；缺省 :func:`toolface.endpoint.python_bin`。

    Returns:
        子进程句柄；端口已被占用（已有实例在跑）时返回 ``None``。
    """
    _reap_exited_procs()
    if port_open(endpoint.host, endpoint.port):
        logger.info("共享 MCP 已在 %s 运行，复用现有实例", endpoint.url)
        return None

    resolved_cwd = cwd or backend_dir()
    resolved_python = python or python_bin()

    # 与 rpc_client._clean_env 同口径剔除代理：MCP 工具经内网 REST 访问
    # Django，继承系统代理会把内网地址也代理出去（超时/502，极难定位）。
    proxy_keys = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"}
    env = {
        **{key: value for key, value in os.environ.items() if key not in proxy_keys},
        "FACHUAN_MCP_TRANSPORT": "streamable-http",
        "FACHUAN_MCP_HTTP_HOST": endpoint.host,
        "FACHUAN_MCP_HTTP_PORT": str(endpoint.port),
    }
    # stderr 落到日志文件：MCP 启动失败（依赖缺失、端口冲突、Django 初始化报错）
    # 的唯一线索都在这里。落在 agent home（0700 根目录）下并以 0600 原子创建：
    # 日志可能含业务数据，/tmp 可预测路径 + 默认 0644 会泄露给本机其他用户。
    directory = (log_dir or mcp_log_dir()).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / f"shared-mcp-{endpoint.port}.log"
    logger.info("拉起共享 MCP: %s（日志: %s）", endpoint.url, log_path)
    log_file: IO[bytes] | None = None
    try:
        fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        # 已存在的旧文件权限可能更宽，显式收紧兜底
        with contextlib.suppress(OSError):
            os.fchmod(fd, 0o600)
        log_file = os.fdopen(fd, "ab")
    except OSError:
        logger.warning("共享 MCP 日志文件不可写，stderr 将丢弃: %s", log_path, exc_info=True)
    proc: subprocess.Popen[bytes]
    try:
        proc = subprocess.Popen(
            [resolved_python, "-m", "mcp_server"],
            cwd=str(resolved_cwd),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=log_file if log_file is not None else subprocess.DEVNULL,
            start_new_session=True,
        )
    finally:
        # 子进程已继承 fd 副本；父进程句柄必须关，否则每次拉起泄漏一个 fd
        if log_file is not None:
            log_file.close()
    _spawned_procs.append(proc)
    return proc


def wait_until_port_ready(endpoint: McpEndpoint, timeout: float) -> bool:
    """阻塞等待端口可连（同步上下文用；异步上下文用 ``pi.shared_mcp.wait_until_ready``）。

    Returns:
        ``True`` 就绪，``False`` 超时。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if port_open(endpoint.host, endpoint.port):
            return True
        time.sleep(0.2)
    return False


def spawned_procs() -> tuple[subprocess.Popen[bytes], ...]:
    """当前本进程持有的子进程句柄快照（测试/排障用，勿修改）。"""
    return tuple(_spawned_procs)
