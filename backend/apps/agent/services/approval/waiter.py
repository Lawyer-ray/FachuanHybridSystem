"""进程内等待器 + 跨 worker 决定/心跳（Redis）—— 状态真相在数据库。"""

from __future__ import annotations

import asyncio
import logging

from ..event_bus import redis_cache_enabled

logger = logging.getLogger(__name__)

DECISION_KEY_PREFIX = "agent:approval:decision:"
#: P2-4 waiter 心跳键前缀——存在 = 有 worker 在等；过期 = 等待者已死
WAITER_KEY_PREFIX = "agent:approval:waiter:"
DECISION_TTL = 600
DECISION_POLL_INTERVAL = 0.2


def _write_decision(approval_id: str, approved: bool) -> None:
    """把决定写入 Redis，供**其他 worker** 上的等待者读取。

    等待审批的 HTTP 请求和「用户点同意」的 HTTP 请求可能落在不同 worker，
    而 ``_ApprovalWaiter`` 是进程内的。没有这一步，跨 worker 时等待方永远
    等不到结果，只能超时走 fail-closed（表现为「审批了但工具没执行」）。
    """
    if not redis_cache_enabled():
        return
    from django.core.cache import cache

    try:
        cache.set(f"{DECISION_KEY_PREFIX}{approval_id}", "1" if approved else "0", DECISION_TTL)
    except Exception:
        # CLAUDE.md 标准:失败会让用户看到「审批了但工具没执行」的无法解释结果,
        # 必须高于 debug——跨 worker 决定丢失正是这一步要防的事故。
        logger.warning("写入审批决定失败(跨 worker 等待者将读不到结果): %s", approval_id, exc_info=True)


def _write_waiter_heartbeat(approval_id: str, timeout_seconds: float) -> None:
    """P2-4：写 waiter 心跳键（TTL = 等待超时 × 1.5，下限 60s）。键在 = 有人在等。"""
    if not redis_cache_enabled():
        return
    from django.core.cache import cache

    try:
        cache.set(
            f"{WAITER_KEY_PREFIX}{approval_id}",
            "alive",
            max(int(timeout_seconds * 1.5), 60),
        )
    except Exception:
        # 心跳写失败会让「无人在线挂起等离线审批」的判定失真,同上不低于 warning。
        logger.warning("写 waiter 心跳失败(离线审批挂起判定将失真): %s", approval_id, exc_info=True)


def _waiter_is_alive(approval_id: str) -> bool:
    """P2-4：waiter 心跳键是否存在（不存在 = 等待进程已死）。

    查不到/查失败时返回 True（保守认为活着）——宁可让前端少报一个
    「可能已失效」，也不要误报把仍然有效的审批标成失效。代价是 Redis 故障时
    waiter_dead 恒为 False，因此必须留日志（根 CLAUDE.md：用户可见的
    无法解释结果至少 warning）。
    """
    if not redis_cache_enabled():
        return True  # 无 Redis 时无法判定，保守认为活着
    from django.core.cache import cache

    try:
        return cache.get(f"{WAITER_KEY_PREFIX}{approval_id}") is not None
    except Exception:
        # Redis 抖动期间 waiter_dead 会恒为 False（审批卡片不提示失效），留痕便于对账。
        logger.warning("读取 waiter 心跳失败(waiter_dead 判定失真): %s", approval_id, exc_info=True)
        return True


def _clear_waiter_heartbeat(approval_id: str) -> None:
    """P2-4：等待结束（决定/超时），清除心跳键。"""
    if not redis_cache_enabled():
        return
    from django.core.cache import cache

    try:
        cache.delete(f"{WAITER_KEY_PREFIX}{approval_id}")
    except Exception:
        # 审批链路不得 debug 吞错（见 tests/ci/unit/agent/test_approval_log_levels.py）：
        # 心跳键残留会让离线挂起判定失真，属用户可见的无法解释结果。
        logger.warning("清除审批心跳键失败 approval_id=%s", approval_id, exc_info=True)


def _read_decision(approval_id: str) -> bool | None:
    """读取其他 worker 写入的决定；无则返回 ``None``。"""
    if not redis_cache_enabled():
        return None
    from django.core.cache import cache

    try:
        raw = cache.get(f"{DECISION_KEY_PREFIX}{approval_id}")
    except Exception:
        # 读不到跨 worker 决定 → 等待方只能超时拒绝，用户看到「审批了但工具
        # 没执行」的无法解释结果，按根 CLAUDE.md 标准必须 ≥ warning。
        logger.warning("读取审批决定失败(跨 worker 等待者将读不到结果): %s", approval_id, exc_info=True)
        return None
    if raw is None:
        return None
    return str(raw) == "1"


def _clear_decision(approval_id: str) -> None:
    if not redis_cache_enabled():
        return
    from django.core.cache import cache

    try:
        cache.delete(f"{DECISION_KEY_PREFIX}{approval_id}")
    except Exception:
        logger.warning("清理审批决定键失败（键会按 TTL 自然过期）: %s", approval_id, exc_info=True)


class _ApprovalWaiter:
    """进程内等待器：把「前端点了什么」交回给阻塞的 HTTP 请求。

    只做进程内协调，**状态真相在数据库**。这样即便进程重启，
    历史审批仍可审计；只是进行中的等待会随进程消失（客户端得到超时 → 拒绝）。
    """

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}
        self._results: dict[str, bool] = {}
        self._lock = asyncio.Lock()

    async def register(self, approval_id: str) -> asyncio.Event:
        async with self._lock:
            event = asyncio.Event()
            self._events[approval_id] = event
            self._results[approval_id] = False
            return event

    async def resolve(self, approval_id: str, approved: bool) -> bool:
        """前端决定后调用；返回是否找到等待者。"""
        async with self._lock:
            event = self._events.get(approval_id)
            if event is None:
                return False
            self._results[approval_id] = approved
            event.set()
            return True

    async def take_result(self, approval_id: str) -> bool:
        async with self._lock:
            return self._results.get(approval_id, False)

    async def discard(self, approval_id: str) -> None:
        async with self._lock:
            self._events.pop(approval_id, None)
            self._results.pop(approval_id, None)


_waiter = _ApprovalWaiter()


async def _wait_decision(approval_id: str, event: asyncio.Event, timeout: float) -> bool:
    """等审批结果：本进程有人点就立即醒，否则轮询 Redis（跨 worker）。

    Returns:
        是否放行。

    Raises:
        TimeoutError: 超时未决。
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout

    while True:
        if event.is_set():
            return await _waiter.take_result(approval_id)

        remote = _read_decision(approval_id)
        if remote is not None:
            return remote

        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError

        try:
            await asyncio.wait_for(event.wait(), timeout=min(DECISION_POLL_INTERVAL, remaining))
        except TimeoutError:
            continue
