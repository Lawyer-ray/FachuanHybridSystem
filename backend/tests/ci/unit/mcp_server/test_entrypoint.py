"""``python -m mcp_server`` 入口的启动契约。

MCP stdio 协议把 **stdout 当作 JSON-RPC 通道**，因此入口必须同时满足两点，缺一即整个
Agent 路径不可用（子进程秒退 → 客户端只看到 "Connection closed"）：

1. 自己补齐 ``sys.path`` 与 ``DJANGO_SETTINGS_MODULE`` 并调用 ``django.setup()`` —— 工具模块
   在导入期就会访问 Django 模型，否则抛 ``AppRegistryNotReady: Apps aren't loaded yet``。
2. bootstrap 期间把 stdout 改道到 stderr —— ``apiSystem.settings`` 里的
   ``get_logging_config()`` 会把 console handler 固定到当时的 ``sys.stdout``，而 Django 启动
   会打出几十行 INFO，留在 stdout 就会插进 JSON-RPC 流里导致握手失败。

这里用**子进程**实测，并刻意清掉 ``PYTHONPATH`` / ``DJANGO_SETTINGS_MODULE``，
以证明入口自洽、不依赖父进程环境继承。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[4]

_PROBE = (
    "import mcp_server.__main__ as entry; "
    "entry._bootstrap_django(); "
    "from mcp_server.server import mcp; "
    "print('TOOLS', len(mcp._tool_manager._tools))"
)

#: 探针用的库名，指向一个**不存在**的库：``django.setup()`` 之后唯一会碰 DB 的步骤是
#: ``AppConfig.ready()`` 里的定时任务注册，连不上会立即失败并被它自己的 try/except 吞掉。
#: 这样测试既不会写任何真实库（尤其不会写非测试库），也不会与 pytest-django 建库过程争用。
_PROBE_DB_NAME = "__mcp_entrypoint_probe__"


def _probe_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in ("PYTHONPATH", "DJANGO_SETTINGS_MODULE", "PYTHONHOME"):
        env.pop(key, None)
    env["DB_NAME"] = _PROBE_DB_NAME
    return env


def _run_probe() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(BACKEND_DIR),
        env=_probe_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_entrypoint_bootstraps_django_and_keeps_stdout_clean() -> None:
    result = _run_probe()

    assert result.returncode == 0, f"入口启动失败：\n{result.stderr[-2000:]}"

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # stdout 必须只有探针自己打的那一行；混进任何日志都会破坏 JSON-RPC 分帧
    assert len(lines) == 1, f"stdout 被污染（应只有 1 行）：{lines[:5]}"
    assert lines[0].startswith("TOOLS "), f"stdout 内容异常：{lines[0]!r}"
    assert int(lines[0].split()[1]) > 0, "MCP 未注册任何工具"


def test_bootstrap_logs_go_to_stderr() -> None:
    """Django 启动日志应落在 stderr，而不是 JSON-RPC 通道所在的 stdout。"""
    result = _run_probe()

    assert result.returncode == 0, result.stderr[-2000:]
    assert "INFO - " not in result.stdout
    assert "INFO - " in result.stderr
