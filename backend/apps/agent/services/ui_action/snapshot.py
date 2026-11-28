"""UI 页面状态快照 —— 让模型「先看一眼页面再说话」（v2-B）。

前端只回页面**主动声明**的字段（``ui-tools/page-state.ts``）：截图模型读不到，整页 dump 会
为「确认律师在哪一页」烧掉一次往返的 token 预算；页面没声明就明说 ``no_page_state``，绝不用空对象冒充。

超时不是错误（同 ``ask_user`` 的 ``timed_out``）：3 秒没等到，唯一确定的事实是「没问到」，
**不是**「页面是空的」——混成一个返回值，模型会把一辆空白页面当事实转述给律师。超限
直接拒（不截断）的理由见 ``UiSnapshotIn``。

页面回的东西分**两半**：``state`` 进模型上下文，``private_state`` **永远不进**（页面放未提交
草稿 / 原始 id / 调试字段的地方）。保证只有一处：:func:`request_snapshot` 按
:data:`MODEL_FACING_KEYS` 挑键，绝不对 payload 做 ``**`` 透传（理由见 ``_model_facing``）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections.abc import Sequence
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

#: 允许进**模型上下文**的应答键（白名单）。``private_state`` 刻意不在里面：它一旦漏进去，页面
#: 就再没有一个「有话要说但不想让模型看见」的地方了。
MODEL_FACING_KEYS: frozenset[str] = frozenset(
    {"status", "state", "route", "note", "available_actions", "blocked_actions"}
)

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
    # 写成直接 `if` 而不是「先算一个布尔再判它」：mypy 只按表达式本身收窄类型，
    # 走布尔变量那条路会把 future 留成 `Future | None`（union-attr 报错）。
    woken = future is not None and not future.done()
    if future is not None and woken:
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


async def accept_snapshot(
    request_id: str,
    *,
    state: dict[str, Any],
    route: str,
    available_actions: Sequence[str] = (),
    blocked_actions: Sequence[dict] = (),
    private_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把契约层（``UiSnapshotIn``）已脱敏、已限量的快照交给等待方。
    ``success=False`` 不是失败：模型只等 3 秒，律师慢一步就是超时（与回执同口径）。

    ``available_actions`` / ``blocked_actions`` / ``private_state`` 必须带默认值：缺省让它与
    ``state`` / ``route`` 不同，是可选的——页面没报、或调用方还没接上这个字段，都退化成一个空表，
    而不是把一个 TypeError 抛进一条本来只该降级的链路。

    ``private_state`` 进 payload（等待方按白名单挑键，见 :func:`_model_facing`），**唯一的可观测面
    是本函数这一条 info 日志**：只有键名与字节数，**不打值**。这条日志是「页面有话要说但不想让
    模型看见」时唯一的排查面——缺了它，那份数据就彻底是黑洞。
    """
    if not _REQUEST_ID_RE.match(request_id or ""):
        return {"accepted": False, "success": False, "error": "request_id 不合法（限字母/数字/下划线/短横，≤64）"}
    private = private_state or {}
    if private:
        # 只记键名 + 字节数：值可能就是律师没提交的草稿，抄进日志等于开第二条泄漏面。
        logger.info(
            "页面快照带 private_state keys=%s bytes=%d（不进模型上下文，只留这一条日志）",
            sorted(private),
            len(json.dumps(private, ensure_ascii=False, default=str).encode("utf-8")),
        )
    found = await resolve(
        request_id,
        {
            "state": state,
            "route": route,
            "available_actions": list(available_actions),
            "blocked_actions": list(blocked_actions),
            "private_state": private,
        },
    )
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
    ``ok`` / ``no_page_state`` 带 ``route`` / ``available_actions`` / ``blocked_actions``（页面没报
    就是空表）；``no_channel`` / ``timeout`` 只有状态本身——**没问到就不带字段**，空表会被模型读成
    「页面上没有可做的动作」、或读成「这页什么都做得了」。

    **返回体绝不带 ``private_state``**（这是整条改动存在的理由），且保证方式是结构性的：两个
    返回分支都过 :func:`_model_facing`，按 :data:`MODEL_FACING_KEYS` 挑键。
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
    # 页面报来的动作名只在契约层洗过一遍（去控制字符/截断/去重/限量）；这里再挡一次类型：
    # 跨进程那份 payload 是 JSON，``available_actions`` / ``blocked_actions`` 不一定是 list。
    actions = _available_actions(payload)
    blocked = _blocked_actions(payload)
    if note:
        # 前端明确说「页面没有声明状态」：**不许**当成空对象，模型据此会误判页面为空。
        # 但 blocked 仍可能是真的（页面只是没声明字段，并不是没有动作），所以照带。
        return _model_facing(
            {
                "status": "no_page_state",
                "route": route,
                "note": note,
                "available_actions": actions,
                "blocked_actions": blocked,
            }
        )
    state = payload.get("state")
    return _model_facing(
        {
            "status": "ok",
            "route": route,
            "state": state if isinstance(state, dict) else {},
            "available_actions": actions,
            "blocked_actions": blocked,
        }
    )


def _model_facing(fields: dict[str, Any]) -> dict[str, Any]:
    """只放行 :data:`MODEL_FACING_KEYS` 里的键——``private_state`` 不进模型上下文的那道锁。

    **刻意不对 payload 做 ``**`` 透传**：payload 是跨进程收到的一份字典，将来往里加字段
    （比如再开一条私有通道）时，透传会让它**自动**出现在模型上下文里，而没有任何断言会红。
    白名单的坏处是「新字段忘了加就不出现」，那是可见的、测试能钉住的失败方向。
    """
    return {key: value for key, value in fields.items() if key in MODEL_FACING_KEYS}


def _available_actions(payload: dict[str, Any]) -> list[str]:
    """从应答载荷里取动作名（非字符串项丢掉；没有就是空表）。"""
    raw = payload.get("available_actions")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str) and item]


def _blocked_actions(payload: dict[str, Any]) -> list[dict[str, str]]:
    """从应答载荷里取「有、但此刻做不了」的动作（形状不对的项丢掉；没有就是空表）。

    与 ``_available_actions`` 同一个理由再挡一次类型：这一份是 JSON，``name`` / ``reason``
    不一定是字符串。只保留两个键——多出来的键在契约层已经丢过，这里再收窄一次，免得模型
    读到一份「原因之外还有别的字段」的想象。
    """
    raw = payload.get("blocked_actions")
    if not isinstance(raw, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name, reason = item.get("name"), item.get("reason")
        if isinstance(name, str) and name and isinstance(reason, str) and reason:
            cleaned.append({"name": name, "reason": reason})
    return cleaned
