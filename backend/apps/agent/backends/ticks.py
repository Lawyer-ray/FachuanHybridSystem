"""把 SDK 的消息流包成「有消息给消息、静默给 ``None``」的 tick 流。

## 为什么必须让出

编排层（``services/chat/stream.py``）只在后端 ``yield`` 时才排空外部事件总线，
而审批卡正是从那条总线推进来的（``services/approval`` → Redis → SSE 队列）。
后端每请求拉起一条子进程时，SDK 的 ``receive_response()`` 在「工具正在等人工
审批」的那段时间**一个消息都不产**——不让出就表现为「工具在等审批，前端的
审批卡永远不出现，直到审批超时」。这不是理论风险：``claude_agent_backend``
接入时真机踩到过。

## 为什么独立成模块而不是各后端各写一份

``claude_agent_backend._with_ticks`` 与本实现同源。两份都在「取消时要收掉挂起
的 ``__anext__``」这一处有细节（漏了会在事件循环关闭时刷
"Task was destroyed but it is pending"），各写一份必然有一份先漂。新后端一律
用这里的 ``with_ticks``；老模块暂不改动（已上线、有 12 个单测守护，改动收益
低于回归风险）。

## 超时取值

:data:`TICK_TIMEOUT_SECONDS` 与 pi / claude-agent 同值（0.2s）：它同时是
「审批卡出现的最大延迟」和「空转频率」。太小会把事件循环刷满，太大审批卡会
慢半拍——0.2s 在两个方向上都不可感知。
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

#: 等下一个消息的上限（秒）。超时即 ``yield None``，把控制权让给编排层。
TICK_TIMEOUT_SECONDS = 0.2


async def with_ticks(source: AsyncIterator[Any]) -> AsyncGenerator[Any | None, None]:
    """``source`` 的每一帧原样产出；静默超过 :data:`TICK_TIMEOUT_SECONDS` 时产出 ``None``。

    ``None`` 在 ``StreamFrame`` 契约里的含义就是「本 tick 无事件」（见
    ``base.py`` 的 ``StreamFrame`` 注释），编排层据此空转一次并排空总线。

    提前退出（本轮 ``done`` / 客户端断开 / 取消）时把挂起的那次 ``__anext__``
    收掉：不取消它会让协程永远停在 SDK 的读循环里，进程退出时刷一堆
    "Task was destroyed"。
    """
    pending: asyncio.Task[Any] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(source.__anext__())
            await asyncio.wait({pending}, timeout=TICK_TIMEOUT_SECONDS)
            if not pending.done():
                yield None
                continue
            task, pending = pending, None
            try:
                yield task.result()
            except StopAsyncIteration:
                return
    finally:
        if pending is not None:
            pending.cancel()
            with contextlib.suppress(BaseException):
                await pending


__all__ = ["TICK_TIMEOUT_SECONDS", "with_ticks"]
