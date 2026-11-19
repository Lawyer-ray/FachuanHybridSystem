"""stream_dual —— 已并入 ``multi.py``，此处只留兼容转发。

## 为什么保留这个文件

``dual`` 这个名字把「同一问题问几个 agent」锁死在 2。v27.20 起主实现搬到了
``multi.py``（``stream_multi``，认 ``kinds: list[str]``），加第 4、5 个 agent
不需要动它一个字。

但外部还有调用点按 ``stream_dual`` 这个名字 import（含测试）。一次性全改会让
这个 PR 混进大量纯改名噪音，掩盖真正的抽象改动——所以这里留一个**纯转发**
薄壳，等下一轮清理时删掉。

**不要在这里加任何逻辑**：任何「双答特判」都该写进 ``multi.py``，否则又会长出
第二份实现（这正是本次要消除的问题）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from ...models import AgentSession
from .multi import ACTIVITY_DEGRADED, StreamMemo, pick_secondary, stream_multi

__all__ = ["ACTIVITY_DEGRADED", "StreamMemo", "pick_secondary", "stream_dual"]


async def stream_dual(
    *,
    session: AgentSession,
    user_message: str,
    user_id: int | None = None,
    tool_selection: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """``stream_multi`` 的两栏薄包装（``dual=True`` 旧前端契约）。

    两个 kind 的挑选规则见 ``multi.pick_secondary``：会话自己的后端是主，
    注册表里第一个不等于主的是次。
    """
    async for event in stream_multi(
        session=session,
        user_message=user_message,
        user_id=user_id,
        tool_selection=tool_selection,
        kinds=None,
    ):
        yield event
