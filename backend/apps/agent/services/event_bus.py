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

#: 缓存/计数类的可重试异常。
#:
#: 为什么不用宽泛的异常捕获：仓库有棘轮门禁
#: （``tests/ci/structure/test_exception_ratchet.py``）禁止扩大宽 except；
#: 这两个位置（跨进程订阅计数）失败本来就该降级，用具体类型反而更诚实。
_CACHE_ERRORS: tuple[type[BaseException], ...] = (OSError, ValueError, TypeError, RuntimeError)
try:  # pragma: no cover - redis 一定装了（RedisCache 依赖），这里只为类型收敛
    from redis.exceptions import RedisError as _RedisError

    _CACHE_ERRORS = (*_CACHE_ERRORS, _RedisError)
except ImportError:  # pragma: no cover
    pass

MAX_QUEUED = 256
REDIS_KEY_PREFIX = "agent:bus:"
#: 跨 worker 的「有人在看这个会话」计数键。审批层靠它区分
#: 「真没人看 → 挂起等离线审批」与「有人在别的 worker 看 → 走在线超时」。
#: 不能拿 ``redis_cache_enabled()`` 代替：生产用 Redis，那个表达式恒真，
#: 会让离线审批这条路永远不可达。
SUBSCRIBER_KEY_PREFIX = "agent:bus:subs:"
SUBSCRIBER_TTL = 3600
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


def raw_redis_client() -> Any:
    """原生 redis 客户端（``cache._cache._cache`` 链）；不可用返回 ``None``。

    Stream 持久化 / live_sessions 路由 / pool 闸门统一从这里取，避免多处
    各自 getattr 的取法漂移。与 ``_redis_client()`` 语义不同：后者走
    ``get_client(write=True)`` 且不可用时抛错（list 中继专用），两者不可互换。
    """
    try:
        inner = getattr(cache, "_cache", None)
        return getattr(inner, "_cache", None) if inner else None
    except Exception:
        return None


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


def _bump_subscribers(session_id: str, delta: int) -> None:
    """跨 worker 订阅计数 +1/-1（无 Redis 时静默跳过）。

    计数带 TTL 只是为了兜「进程被杀没走到 unregister」的泄漏；不刷新不重入。
    """
    if not redis_cache_enabled():
        return
    key = f"{SUBSCRIBER_KEY_PREFIX}{session_id}"
    try:
        if delta > 0:
            cache.add(key, 0, SUBSCRIBER_TTL)
            cache.incr(key)
        else:
            if int(cache.decr(key) or 0) <= 0:
                cache.delete(key)
    except _CACHE_ERRORS:
        logger.warning("更新跨进程订阅者计数失败: %s", session_id, exc_info=True)


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
        _bump_subscribers(session_id, 1)
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
        _bump_subscribers(session_id, -1)

    async def remote_subscriber_count(self, session_id: str) -> int:
        """跨进程订阅者数（Redis 计数）；无 Redis 时恒 0。

        含本进程（register 时也 +1），但调用方已经先用 ``has_subscribers``
        判过本地，重复计数不影响结论。
        """
        if not redis_cache_enabled():
            return 0
        try:
            return int(cache.get(f"{SUBSCRIBER_KEY_PREFIX}{session_id}") or 0)
        except _CACHE_ERRORS:
            logger.warning("读取跨进程订阅者计数失败: %s", session_id, exc_info=True)
            return 0

    async def subscriber_count(self, session_id: str) -> int:
        async with self._lock:
            return len(self._subscribers.get(session_id, ()))

    async def has_subscribers(self, session_id: str) -> bool:
        return await self.subscriber_count(session_id) > 0

    # ── 发布 ────────────────────────────────────────────────────────────────

    async def publish(self, session_id: str, event: dict[str, Any]) -> int:
        """向会话的订阅者推送事件，返回本进程送达数量。

        同时写入 Redis，供其他 worker 的订阅者消费。
        P2-1：同时写入 Redis Stream（带自增 seq），SSE 断线重连时回放。
        """
        # P2-1 SSE 断线续传：事件持久化到 Redis Stream
        _append_to_stream(session_id, event)

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
                    # 已被消费者取走，无需丢弃
                    logger.debug("积压丢弃时队列已空: session=%s", session_id)
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
                logger.warning("写入 Redis 事件失败（已降级为进程内）: %s", session_id, exc_info=True)

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
                logger.warning("Redis 中继异常", exc_info=True)
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
            except asyncio.CancelledError:
                # 正常取消路径，不记录
                pass
            except Exception:
                logger.debug("中继协程结束时抛错（已忽略）", exc_info=True)
            self._relay_task = None


_bus = EventBus()


def get_bus() -> EventBus:
    """获取进程内单例总线。"""
    return _bus


# ── P2-1 SSE 断线续传：Redis Stream 事件持久化 ──────────────────────────────

_EVENT_STREAM_PREFIX = "agent:sse:stream:"
_EVENT_STREAM_TTL = 300  # 5 分钟（覆盖重连窗口）


def _append_to_stream(session_id: str, event: dict[str, Any]) -> None:
    """事件写入 Redis Stream（XADD），带 TTL 和长度上限。"""
    if not redis_cache_enabled():
        return
    try:
        import redis

        client = raw_redis_client()
        if client and isinstance(client, redis.Redis):
            key = f"{_EVENT_STREAM_PREFIX}{session_id}"
            seq = client.incr(f"{_EVENT_STREAM_PREFIX}{session_id}:seq")
            client.xadd(key, {"seq": str(seq), "data": json.dumps(event, ensure_ascii=False)})
            client.expire(key, _EVENT_STREAM_TTL)
    except Exception:
        logger.warning("事件写 Redis Stream 失败（不影响实时投递）", exc_info=True)


def replay_events(session_id: str, last_event_id: int) -> list[dict[str, Any]]:
    """断线重连：回放 last_event_id 之后的事件（P2-1）。

    Returns:
        事件列表；Redis 不可用或 Stream 过期返回空列表（前端退化为重拉历史）。
    """
    if not redis_cache_enabled():
        return []
    try:
        import redis

        client = raw_redis_client()
        if not client or not isinstance(client, redis.Redis):
            return []
        key = f"{_EVENT_STREAM_PREFIX}{session_id}"
        entries = client.xrange(key, min=f"{last_event_id + 1}", max="+") or []
        events = []
        for _entry_id, fields in entries:
            # fields 可能是 None（stubs 联合类型；极端断连窗口下防御）
            if not fields:
                continue
            try:
                event = json.loads(fields.get("data", "{}"))
                events.append(event)
            except (ValueError, TypeError):
                continue
        return events
    except Exception:
        logger.warning("事件回放失败", exc_info=True)
        return []
