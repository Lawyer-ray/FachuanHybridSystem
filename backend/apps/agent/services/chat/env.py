"""会话级环境变量与用户凭证铸造。

``session_env`` / ``mint_user_token`` 是 chat 包对外共享的公开助手：
除 stream 编排外，``compact_service`` 也复用同一套会话 env 与凭证铸造逻辑。

注入的变量清单：``FACHUAN_SESSION_ID`` / ``FACHUAN_USER_ID`` / ``FACHUAN_RUN_ID``
/ ``FACHUAN_USER_TOKEN`` / ``FACHUAN_APPROVAL_URL`` / ``FACHUAN_INTERNAL_TOKEN``。
"""

from __future__ import annotations

import os
import socket

from asgiref.sync import sync_to_async

from ...models import AgentSession
from ...pi.user_token import USER_TOKEN_ENV, mint_user_access_token


def _worker_id() -> str:
    """本 worker 唯一标识（P2-3 跨 worker 路由用）。"""
    return os.environ.get("HOSTNAME", "") or socket.gethostname()


def session_env(
    session: AgentSession | None,
    user_id: int | None,
    user_token: str = "",
    run_id: str = "",
) -> dict[str, str]:
    """注入给 pi 子进程的会话级环境变量。

    - ``FACHUAN_SESSION_ID`` / ``FACHUAN_USER_ID``：审批 extension 回调路由
    - ``FACHUAN_RUN_ID``：审批回调的**二级寻址键**（``{session_id}:{agent_kind}:{seq}``）。
      同会话内可并行多个 agent，只按 session 寻址会让审批弹窗分不清是哪次调用；
      为空时不注入，审批侧回退到只按 session 寻址（兼容旧行为）。
    - ``FACHUAN_USER_TOKEN``：律师本人的 access token，mcp.json 以 ``${...}`` 引用
      作为 Authorization 头（见 ``pi/user_token.py``）。**无 token 也要写空串**：
      让 pi 的变量展开得到空值而不是保留字面量，mcp_server 据此回退服务账号。
    """
    env: dict[str, str] = {USER_TOKEN_ENV: user_token}
    if session is not None:
        env["FACHUAN_SESSION_ID"] = str(session.session_id)
    if user_id is not None:
        env["FACHUAN_USER_ID"] = str(user_id)
    # 二级寻址键：调用方不传（旧调用方 / 单 agent 场景）即保持原有行为。
    if run_id:
        env["FACHUAN_RUN_ID"] = run_id
    approval_url = os.environ.get("FACHUAN_APPROVAL_URL", "").strip()
    if approval_url:
        env["FACHUAN_APPROVAL_URL"] = approval_url
    token = os.environ.get("FACHUAN_INTERNAL_TOKEN", "").strip()
    if token:
        env["FACHUAN_INTERNAL_TOKEN"] = token
    return env


async def mint_user_token(user_id: int | None) -> str:
    """为本轮对话铸律师 access token；无用户身份时返回空串。

    铸造走同步 ORM（取用户）, 放线程里跑；失败直接抛给调用方——宁可本轮对话
    不跑，也不能让工具退回超管服务账号（fail-closed）。
    """
    if user_id is None:
        return ""
    return await sync_to_async(mint_user_access_token, thread_sensitive=True)(user_id)
