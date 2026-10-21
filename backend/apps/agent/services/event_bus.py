"""会话事件总线 —— 把 agent 产出的事件推给对应的 SSE 连接。

## 为什么需要总线

审批走的是独立 HTTP 回调（pi extension → Django），这条链路和「发起对话的那条
SSE 连接」不在同一个调用栈里。要在这里把 ``approval_request`` 推给前端，
就必须有一个按会话寻址的通道。

## 跨进程（Redis）

单 worker 时纯进程内队列就够。但生产是多 worker 部署：**审批回调可能落在
worker A，而用户的 SSE 连接在 worker B**。若只用进程内队列，事件会永远
送不到前端——表现为审批必定超时。

因此分两层：

```
publish(session_id, event)
  ├─ 直接投递给本进程的订阅者（快路径，同 worker 场景零开销）
  └─ 写入 Redis list（跨进程，供其他 worker 消费）

每个 worker 跑一个 relay 协程：
  while True: 从 Redis list 弹出 → 投递给本进程订阅者
```

- 无 Redis（开发环境 InMemoryCache）时自动退化为纯进程内，行为不变
- relay 用 ``asyncio`` 协程而非线程，与 SSE 循环共享事件循环
- 事件带 ``origin`` 标记，本进程已投递过的不再重复投递（避免双发）

## 背压

本地订阅队列有上限，超了丢最旧的并告警，避免慢客户端把内存吃光。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from django.core.cache import cache

logger = logging.getLogger(__name__)

MAX_QUEUED = 256
REDIS_KEY_PREFIX = "agent:bus:"
RELAY_POLL_INTERVAL = 0.05
#: 事件在 Redis 里的存活时间，防止无人消费时无限堆积
REDIS_TTL = 60
#: 单个会话在 Redis 里最多堆积的事件数
REDIS_MAX_LEN = 500

#: 本进程唯一标识，用于跳过自己发出的事件
_PROCESS_ID = uuid.uuid4().hex[:12]


def _redis_client() -> Any:
    """拿原生 redis 客户端（Django 的 RedisCache 包装在 ``_cache`` 上）。

    ``cache.client`` 在 Django 4.x 可用，5.x 已移除；这里两种都兼容，
    避免升级时再次踩坑。
    """
    inner = getattr(cache, "_cache", None)
    if inner is not None and hasattr(inner, "get_client"):
        return inner.get_client(write=True)
    legacy = getattr(cache, "client", None)
    if legacy is not None:
        return legacy.get_client(write=True)
    raise RuntimeError("当前缓存后端不支持原生 Redis 操作")


def redis_cache_enabled() -> bool:
    """缓存后端是否是 Redis（决定跨进程分发是否可用）。

    approval.py 的跨 worker 决定读写也依赖同一判定，统一从这里取。
    """
    try:
        from django.conf import settings

        backend = str(((settings.CACHES or {}).get("default") or {}).get("BACKEND", ""))
    except Exception:
        return False
    return "redis" in backend.lower()


class EventBus:
    """按会话分发事件的进程内总线 + Redis 跨进程中继。"""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        self._lock = asyncio.Lock()
        self._relay_task: asyncio.Task[None] | None = None
        self._relay_stop = False

    # ── 订阅 ────────────────────────────────────────────────────────────────

    async def register(self, session_id: str) -> asyncio.Queue[dict[str, Any]]:
        """为一个会话登记订阅队列。"""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        async with self._lock:
            self._subscribers.setdefault(session_id, []).append(queue)
        self._ensure_relay()
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

    async def subscriber_count(self, session_id: str) -> int:
        async with self._lock:
            return len(self._subscribers.get(session_id, ()))

    async def has_subscribers(self, session_id: str) -> bool:
        return await self.subscriber_count(session_id) > 0

    # ── 发布 ────────────────────────────────────────────────────────────────

    async def publish(self, session_id: str, event: dict[str, Any]) -> int:
        """向会话的订阅者推送事件，返回本进程送达数量。

        同时写入 Redis，供其他 worker 的订阅者消费。
        """
        delivered = await self._deliver_local(session_id, event, skip_origin=_PROCESS_ID)

        if redis_cache_enabled():
            await self._publish_redis(session_id, event)

        return delivered

    async def _deliver_local(
        self,
        session_id: str,
        event: dict[str, Any],
        *,
        skip_origin: str = "",
    ) -> int:
        """投递给本进程的订阅者。"""
        if skip_origin and event.get("_origin") == skip_origin:
            return 0
        async with self._lock:
            queues = list(self._subscribers.get(session_id, ()))
        delivered = 0
        for queue in queues:
            if queue.qsize() >= MAX_QUEUED:
                logger.warning(
                    "订阅队列积压超过 %s，丢弃最旧事件: session=%s",
                    MAX_QUEUED,
                    session_id,
                )
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass  # 已被消费者取走，无需丢弃
            await queue.put(event)
            delivered += 1
        return delivered

    # ── Redis 跨进程 ────────────────────────────────────────────────────────

    async def _publish_redis(self, session_id: str, event: dict[str, Any]) -> None:
        """把事件写入 Redis list（带 origin 标记）。"""

        def _write() -> None:
            payload = json.dumps({**event, "_origin": _PROCESS_ID}, ensure_ascii=False, default=str)
            key = f"{REDIS_KEY_PREFIX}{session_id}"
            try:
                client = _redis_client()
                client.rpush(key, payload)
                client.ltrim(key, -REDIS_MAX_LEN, -1)
                client.expire(key, REDIS_TTL)
            except Exception:
                logger.debug("写入 Redis 事件失败（已降级为进程内）: %s", session_id, exc_info=True)

        await asyncio.to_thread(_write)

    def _ensure_relay(self) -> None:
        """确保本进程的 Redis 中继协程在跑。"""
        if not redis_cache_enabled():
            return
        if self._relay_task is not None and not self._relay_task.done():
            return
        self._relay_stop = False
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._relay_task = loop.create_task(self._relay_loop())

    async def _relay_loop(self) -> None:
        """从 Redis 拉取其他 worker 发出的事件，投递给本进程订阅者。"""
        while not self._relay_stop:
            try:
                await self._drain_redis()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("Redis 中继异常", exc_info=True)
            await asyncio.sleep(RELAY_POLL_INTERVAL)

    async def _drain_redis(self) -> None:
        """把当前所有会话的 Redis 队列取空并投递。"""
        async with self._lock:
            session_ids = list(self._subscribers.keys())
        if not session_ids:
            return

        def _read(sid: str) -> list[str]:
            key = f"{REDIS_KEY_PREFIX}{sid}"
            try:
                client = _redis_client()
                pipe = client.pipeline()
                pipe.lrange(key, 0, -1)
                pipe.delete(key)
                result = pipe.execute()
                raw = result[0] if result else []
                return [item.decode() if isinstance(item, bytes) else item for item in raw]
            except Exception:
                return []

        for sid in session_ids:
            raw_items = await asyncio.to_thread(_read, sid)
            for raw in raw_items:
                try:
                    event = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                if event.get("_origin") == _PROCESS_ID:
                    continue  # 自己发的，本地已投递过
                event.pop("_origin", None)
                await self._deliver_local(sid, event)

    async def stop_relay(self) -> None:
        """停止中继（测试 / 进程退出）。"""
        self._relay_stop = True
        if self._relay_task is not None:
            self._relay_task.cancel()
            try:
                await self._relay_task
            except (asyncio.CancelledError, Exception):
                pass  # 停止中继：取消或收尾异常都不再关心
            self._relay_task = None


_bus = EventBus()


def get_bus() -> EventBus:
    """获取进程内单例总线。"""
    return _bus
