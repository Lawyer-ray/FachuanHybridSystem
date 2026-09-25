"""``python -m mcp_server`` 入口。

MCP stdio 协议把 **stdout 当作 JSON-RPC 通道**，因此这里必须做到两件事：

1. **先初始化 Django，再导入 server。** 工具模块会导入 Django 模型，缺 ``django.setup()``
   会在导入期抛 ``AppRegistryNotReady: Apps aren't loaded yet``；子进程随即秒退，客户端只看到
   "Connection closed"。同时要自己补 ``sys.path``——settings 实际位于
   ``backend/apiSystem/apiSystem/``，而子进程由 ``StdioTransport(cwd=BACKEND_DIR)`` 启动，
   不保证带 ``PYTHONPATH``。
2. **bootstrap 期间把 stdout 改道到 stderr。** ``apiSystem.settings`` 里的
   ``get_logging_config()`` 会把 console handler 的 stream 固定成**当时**的 ``sys.stdout``，
   而 Django 启动会打出几十行 INFO。若留在 stdout，这些行会插进 JSON-RPC 流里导致握手失败。
   在 ``django.setup()`` 之前改道，handler 便永久指向 stderr；之后再把 stdout 还给
   ``mcp.run()``（handler 持有的是对象引用，恢复 ``sys.stdout`` 不影响它）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
#: settings 的导入根，即 ``backend/apiSystem/apiSystem/settings.py`` 所在的上一级
API_SYSTEM_ROOT = BACKEND_DIR / "apiSystem"


def _bootstrap_django() -> None:
    """补 sys.path → 指定 settings → 初始化 Django（期间 stdout 改道 stderr）。"""
    for path in (str(API_SYSTEM_ROOT), str(BACKEND_DIR)):
        if path not in sys.path:
            sys.path.insert(0, path)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

    import django

    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        django.setup()
    finally:
        sys.stdout = real_stdout


def main() -> None:
    _bootstrap_django()

    # 必须在 django.setup() 之后导入：工具模块在导入期就会访问 Django 模型
    from mcp_server.server import mcp

    mcp.run()


if __name__ == "__main__":
    main()
