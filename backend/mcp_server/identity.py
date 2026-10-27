"""按请求透传用户身份 —— agent 的工具调用以真实律师身份执行。

## 为什么

``mcp_server`` 默认用服务账号（``FACHUAN_USERNAME``，超管）调 REST API。
共享 MCP（streamable-http）模式下所有用户的 agent 连的都是同一个 server
进程，若不区分身份，任何律师都能借 agent 读到全所数据，写操作的审计也
记在服务账号名下（confused deputy）。

## 机制

``apps/agent`` 为每轮对话铸「当前律师」的 access token，经 pi 的 ``mcp.json``
以 ``Authorization: Bearer ${FACHUAN_USER_TOKEN}`` 头发来。本模块的纯 ASGI
中间件把该头存入 ContextVar，``client.py`` 发上游请求时优先透传它：

- ContextVar 在 ASGI 请求任务里设置，Starlette → MCP 会话 → 工具协程同任务
  可见；anyio 的 ``to_thread`` 会把 context 拷贝进工作线程，**同步工具同样
  读得到**。
- stdio 模式 / 无 Authorization 头 / 头不是合法 Bearer：回退服务账号（保持
  既有行为，手工 ``pi``、脚本等场景不受影响）。
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from .config import require_request_auth

#: 当前 HTTP 请求的 Authorization 头原文（无则空串）
request_authorization: ContextVar[str] = ContextVar("fachuan_request_authorization", default="")

#: 当前 HTTP 请求携带的会话标识（来自 ``X-Fachuan-Session``）。
#:
#: 为什么需要它：``ask_user`` 要把提问推到**对的** SSE 通道，而 MCP 进程
#: 服务所有律师的所有会话。pi 每请求起一个进程，``chat_service`` 已把
#: ``FACHUAN_SESSION_ID`` 注入子进程 env，``mcp.json`` 再用 header 把它带过来。
request_session_id: ContextVar[str] = ContextVar("fachuan_request_session_id", default="")


SESSION_HEADER = "x-fachuan-session"


def current_session_id() -> str:
    """当前会话标识（无则空串）。"""
    return request_session_id.get().strip()


def passthrough_authorization() -> str:
    """返回可直接用于上游请求的 Authorization 值；无有效 Bearer 时为空串。"""
    value = request_authorization.get().strip()
    if value.lower().startswith("bearer") and len(value) > len("bearer "):
        return value
    return ""


class RequestAuthMiddleware:
    """纯 ASGI 中间件：把 Authorization 头写进 ContextVar，并在 HTTP 模式强制鉴权。

    ## 安全边界（2026-10-28 审计实测）

    本服务在 streamable-http 模式下绑 ``127.0.0.1:8011`` 常驻，一份进程服务全所。
    早期实现只写 ContextVar、不做任何校验：无 ``Authorization`` 头的请求会静默回退
    到 ``config.USERNAME/PASSWORD`` 换来的**服务账号（超管）** token。实测（无任何
    凭证）：

    ```
    POST /mcp {"method":"initialize"}              → 200
    POST /mcp {"method":"tools/call","list_cases"} → 返回真实客户案件
    ```

    即本机任意进程（其他用户 shell / 被 XSS 的前端 / 恶意依赖脚本 / 其他 agent
    会话）都能绕过 JWT、租户隔离与审批读到全所数据。

    因此 HTTP 模式下：**缺 Bearer 或不是合法 Bearer 一律 401**，不再回退。
    身份只能来自每个请求自带的 Authorization 头。
    """

    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        raw_auth = ""
        for name, value in scope.get("headers") or []:
            if name == b"authorization":
                raw_auth = value.decode("latin-1")
            elif name == SESSION_HEADER.encode():
                request_session_id.set(value.decode("latin-1"))

        request_authorization.set(raw_auth)

        if require_request_auth() and not _is_valid_bearer(raw_auth):
            await _send_401(send)
            return

        await self._app(scope, receive, send)


def _is_valid_bearer(value: str) -> bool:
    """是否为形如 ``Bearer <token>`` 的有效值。"""
    text = value.strip()
    return text.lower().startswith("bearer") and len(text) > len("bearer ")


async def _send_401(send: Any) -> None:
    """返回 401（JSON-RPC 风格 body，兼容 MCP 客户端错误展示）。"""
    import json

    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "error": {
                "code": -32001,
                "message": "未认证：共享 MCP 要求每个请求携带 Authorization: Bearer <token>",
            },
            "id": None,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
                (b"www-authenticate", b'Bearer realm="fachuan-mcp"'),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
