"""会话事件总线 —— 把 agent 产出的事件推给对应的 SSE 连接。

## 为什么需要总线

审批走的是独立 HTTP 回调（pi extension → Django），这条链路和「发起对话的那条
SSE 连接」不在同一个调用栈里。要在这里把 ``approval_request`` 推给前端，
就必须有一个按会话寻址的通道。

## 设计

- 按 ``session_id`` 维护一组订阅队列（同一会话可能多端打开）
- 进程内实现（单机多 worker 场景下，需要用户连到同一 worker；
  跨 worker 广播可后续替换为 Redis pub/sub，接口不变）
- 队列无界但有上限保护：超过 ``MAX_QUEUED`` 丢弃最旧的并告警，
  避免慢客户端把内存吃光
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

MAX_QUEUED = 256


class EventBus:
    """按会话分发事件的进程内总线。"""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        self._lock = asyncio.Lock()

    async def register(self, session_id: str) -> asyncio.Queue[dict[str, Any]]:
        """为一个会话登记订阅队列。"""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        async with self._lock:
            self._subscribers.setdefault(session_id, []).append(queue)
        return queue

    async def unregister(self, session_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """注销订阅队列。"""
        async with self._lock:
            queues = self._subscribers.get(session_id)
            if not queues:
                return
            try:
                queues.remove(queue)
            except ValueError:
                return
            if not queues:
                self._subscribers.pop(session_id, None)

    async def publish(self, session_id: str, event: dict[str, Any]) -> int:
        """向会话的所有订阅者推送事件；返回送达数量。"""
        async with self._lock:
            queues = list(self._subscribers.get(session_id, ()))
        delivered = 0
        for queue in queues:
            if queue.qsize() >= MAX_QUEUED:
                logger.warning("订阅队列积压超过 %s，丢弃最旧事件: session=%s", MAX_QUEUED, session_id)
                with_suppress = getattr(queue, "get_nowait", None)
                if with_suppress is not None:
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
            await queue.put(event)
            delivered += 1
        return delivered

    async def subscriber_count(self, session_id: str) -> int:
        async with self._lock:
            return len(self._subscribers.get(session_id, ()))


_bus = EventBus()


def get_bus() -> EventBus:
    """获取进程内单例总线。"""
    return _bus
