"""MCP Server 配置 - 从环境变量读取法穿连接信息"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

BASE_URL: str = os.getenv("FACHUAN_BASE_URL", "http://127.0.0.1:8002/api/v1")
USERNAME: str = os.getenv("FACHUAN_USERNAME", "")
PASSWORD: str = os.getenv("FACHUAN_PASSWORD", "")


def http_transport_enabled() -> bool:
    """当前进程是否以 streamable-http 模式运行（共享 MCP）。

    HTTP 模式下一份常驻进程服务所有律师，**禁止**回退到服务账号（超管）：
    那样任何能发本机 HTTP 请求的进程都能以超管身份读写全所数据。
    身份只能来自每个请求自带的 ``Authorization`` 头。
    """
    return os.getenv("FACHUAN_MCP_TRANSPORT", "stdio").strip().lower() in {"streamable-http", "http"}


def require_request_auth() -> bool:
    """是否强制每个请求必须带 Authorization（HTTP 模式 = True）。

    ``FACHUAN_MCP_REQUIRE_AUTH=0`` 仅供本机调试临时关闭，默认开启。
    """
    if not http_transport_enabled():
        return False
    return os.getenv("FACHUAN_MCP_REQUIRE_AUTH", "1").strip().lower() not in {"0", "false", "no", "off"}
