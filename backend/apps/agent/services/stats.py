"""会话统计的读取（ORM 下沉层）。

结构门禁要求 `apps/*/api/` 不直连 ORM；统计端点需要「该会话最新一轮 run」，
放在这里而不是路由里。
"""

from __future__ import annotations

from typing import Any


async def latest_run_for_session(session: Any) -> Any:
    """取某会话最新的一轮 run；没有则返回 None。"""
    from apps.agent.models.agent import AgentRun

    return await AgentRun.objects.filter(session=session).order_by("-id").afirst()
