"""UI 页面状态快照 —— 让模型「先看一眼页面再说话」（v2-B）。

前端只回页面**主动声明**的字段（``ui-tools/page-state.ts``）：截图模型读不到，整页 dump 会
为「确认律师在哪一页」烧掉一次往返的 token 预算；页面没声明就明说 ``no_page_state``，绝不用空对象冒充。

超时不是错误（同 ``ask_user`` 的 ``timed_out``）：3 秒没等到，唯一确定的事实是「没问到」，
**不是**「页面是空的」——混成一个返回值，模型会把一辆空白页面当事实转述给律师。超限
直接拒（不截断）的理由见 ``UiSnapshotIn``。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any

from ..event_bus import redis_cache_enabled
from . import ack

logger = logging.getLogger(__name__)

#: 应答在共享缓存里的键前缀与寿命（派发在 MCP 进程、应答 POST 在 Django 进程，只能走缓存）。
SNAPSHOT_KEY_PREFIX = "agent:uisnap:"
SNAPSHOT_TTL = 30
#: 轮询间隔（秒）：这里等的是「一次已经在发生的读取」，慢半拍就等于白等（同 ack）。
SNAPSHOT_POLL_INTERVAL = 0.05
#: 默认等待上限（秒）：够一次本地读取 + 网络往返，又不至于明显拖慢模型循环。
DEFAULT_TIMEOUT_SECONDS = 3.0
#: ``request_id`` 由本模块生成；它进缓存键也进日志，故限字符集与长度。
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
#: 可重试的缓存异常（与 ``ack._CACHE_ERRORS`` 同口径：这两处失败本来就该降级）。
_CACHE_ERRORS: tuple[type[BaseException], ...] = (OSError, ValueError, TypeError, RuntimeError)

#: 进程内等待表：``request_id → Future``（只做同 worker 快路径，跨 worker 走共享缓存）。
_FUTURES: dict[str, asyncio.Future[dict[str, Any]]] = {}


async def register(request_id: str) -> asyncio.Future[dict[str, Any]]:
    """登记等待者，**必须在 publish 之前**（否则前端的快速应答找不到人）。"""
    future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
    _FUTURES[request_id] = future
    return future


async def resolve(request_id: str, payload: dict[str, Any]) -> bool:
    """应答的唯一入口：本进程唤醒 + 写共享缓存；**幂等**（不覆盖第一份，前端会重试）。"""
    future = _FUTURES.get(request_id)
    woken = future is not None and not future.done()
    if woken:
        future.set_result(payload)
    stored = _write(request_id, payload)
    return woken or stored


async def wait(request_id: str, timeout: float) -> dict[str, Any] | None:
    """等应答；超时返回 ``None``（**不抛异常**——调用方据此返回 ``timeout`` 而非失败）。"""
    future = _FUTURES.get(request_id)
    if future is None or timeout <= 0:
        return None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if future.done():
            return future.result()
        remote = _read(request_id)
        if remote is not None:
            return remote
        await asyncio.sleep(SNAPSHOT_POLL_INTERVAL)
    return future.result() if future.done() else None


def _write(request_id: str, payload: dict[str, Any]) -> bool:
    """写共享缓存（跨 worker 唯一通道）；``add`` 的「只有第一个写入者成功」即幂等判据。"""
    if not redis_cache_enabled():
        return False
    # 延迟 import：本模块要能在没有 Django settings 的进程里被 import。
    from django.core.cache import cache

    try:
        raw = json.dumps(payload, ensure_ascii=False)
        return bool(cache.add(f"{SNAPSHOT_KEY_PREFIX}{request_id}", raw, SNAPSHOT_TTL))
    except _CACHE_ERRORS:
        logger.warning("写页面状态快照失败（跨 worker 等待者将读不到）: %s", request_id, exc_info=True)
        return False


def _read(request_id: str) -> dict[str, Any] | None:
    """读别的进程写下的应答（本进程没有等待者时才用得上）；读不到/非法一律 ``None``。"""
    if not redis_cache_enabled():
        return None
    from django.core.cache import cache

    try:
        # 读不到时 ``or "null"`` → ``None``：非法 JSON 由 ``ValueError`` 一并兜住。
        payload = json.loads(cache.get(f"{SNAPSHOT_KEY_PREFIX}{request_id}") or "null")
    except _CACHE_ERRORS:
        logger.warning("读取页面状态快照失败（跨 worker 等待者读不到）: %s", request_id, exc_info=True)
        return None
    return payload if isinstance(payload, dict) else None


async def accept_snapshot(request_id: str, *, state: dict[str, Any], route: str) -> dict[str, Any]:
    """把契约层（``UiSnapshotIn``）已脱敏、已限量的快照交给等待方。
    ``success=False`` 不是失败：模型只等 3 秒，律师慢一步就是超时（与回执同口径）。
    """
    if not _REQUEST_ID_RE.match(request_id or ""):
        return {"accepted": False, "success": False, "error": "request_id 不合法（限字母/数字/下划线/短横，≤64）"}
    found = await resolve(request_id, {"state": state, "route": route})
    return {
        "accepted": True,
        "success": found,
        "note": "" if found else "快照已记录，但等待方已超时（模型已按没问到继续）",
    }


async def request_snapshot(
    page: str | None,
    session_id: str | None,
    timeout_s: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """请求页面回一份结构化状态；返回 ``status`` 四态之一（超时不抛异常）。
    ``ok`` / ``no_page_state`` 带 ``route``；``no_channel`` / ``timeout`` 只有状态本身。
    """
    if not session_id:
        return {"status": "no_channel"}
    # 延迟 import：本模块要能在没有 Django settings 的进程里被 import。
    from ..event_bus import get_bus

    bus = get_bus()
    # 判据照 ``publish_ui_action``：问真正的订阅事实，而不是「缓存后端是不是 Redis」。
    has_remote = bool(await bus.has_subscribers(session_id)) or bool(await bus.remote_subscriber_count(session_id))
    request_id = uuid.uuid4().hex
    # 归属映射复用 ack（同一条 UI 通道）：应答 POST 在**另一个进程**里校验归属，必须跨进程写。
    ack.mark_dispatch_session(request_id, session_id)
    # 登记必须早于 publish：顺序反了，快速应答会落在「没有等待者」上。
    await register(request_id)
    try:
        delivered = await bus.publish(
            session_id,
            {"type": "ui_snapshot_request", "request_id": request_id, "page": page, "timeout_seconds": int(timeout_s)},
        )
        if not delivered and not has_remote:
            return {"status": "no_channel"}
        payload = await wait(request_id, timeout_s)
    finally:
        # 收工即摘掉等待对象：不摘就是常驻进程里每次漏一个 Future。
        _FUTURES.pop(request_id, None)
    if payload is None:
        return {"status": "timeout"}
    route = str(payload.get("route") or "")
    note = str(payload.get("note") or "").strip()
    if note:
        # 前端明确说「页面没有声明状态」：**不许**当成空对象，模型据此会误判页面为空。
        return {"status": "no_page_state", "route": route, "note": note}
    state = payload.get("state")
    return {"status": "ok", "route": route, "state": state if isinstance(state, dict) else {}}
