"""``session_env`` 的 run_id 注入（多 agent 并行的二级寻址键）。

同一会话内可能并行跑多个 agent，审批 extension 只报 ``FACHUAN_SESSION_ID``
时前端分不清两条审批是哪次调用（安全风险：可能批准错 agent 的写操作）。
``FACHUAN_RUN_ID``（``{session_id}:{agent_kind}:{seq}``）是第二级寻址键。

向后兼容是这里的核心约束：**没传 run_id 的旧调用方必须完全维持原行为**
（环境里不出现该变量），不能因为「多一个空串」就让审批侧把 key 当成有效值。
"""

from __future__ import annotations

import pytest

from apps.agent.models import AgentSession
from apps.agent.services.chat.env import session_env

RUN_ID_ENV = "FACHUAN_RUN_ID"


def test_run_id_not_injected_when_omitted() -> None:
    """不传 run_id：环境里根本没有这个键（不是空串），旧行为不变。"""
    env = session_env(None, None)
    assert RUN_ID_ENV not in env


def test_run_id_injected_when_provided() -> None:
    env = session_env(None, None, run_id="abc-123:pi:1")
    assert env[RUN_ID_ENV] == "abc-123:pi:1"


def test_empty_run_id_not_injected() -> None:
    """空串视为「未接入 run_id」，不注入空值，审批侧回退到只按 session 寻址。"""
    env = session_env(None, None, run_id="")
    assert RUN_ID_ENV not in env


def test_run_id_coexists_with_session_env() -> None:
    """run_id 与 session 级变量同批注入，不互相覆盖。"""
    session = AgentSession(title="run-id-stack")
    env = session_env(session, 7, user_token="tok-123", run_id=f"{session.session_id}:pi:2")
    assert env["FACHUAN_SESSION_ID"] == str(session.session_id)
    assert env["FACHUAN_USER_ID"] == "7"
    assert env["FACHUAN_USER_TOKEN"] == "tok-123"
    assert env[RUN_ID_ENV] == f"{session.session_id}:pi:2"


@pytest.mark.parametrize("run_id", ["abc-123:pi:1", "sess:claude:7"])
def test_run_id_value_passed_through_verbatim(run_id: str) -> None:
    """原样透传：不做格式化/裁剪，格式由调用方统一生产。"""
    assert session_env(None, None, run_id=run_id)[RUN_ID_ENV] == run_id
