"""UI 动作回执 —— 让工具返回里就能看见执行结果（v2-A）。

## 为什么回执只能经「工具返回值」回到模型

pi 后端的会话由**子进程**持有，Django 无法在两跳之间往会话里插系统消息。
但工具调用发生在模型循环**内部**，所以工具返回值本身就是天然注入点：只要
``publish_ui_action`` 在返回前拿到回执，模型这一次就能看到真实结果，不必再开
一次请求。

## 三条路，缺一不可

1. **同进程快路径**：``wait()`` 先看本进程的 ``asyncio.Event``，前端回执落在
   同一个 worker 时零延迟。
2. **跨 worker**：派发在 MCP 进程、回执 POST 落在 Django 进程，``Event`` 跨不过去。
   所以 :func:`resolve` 同时把回执写 Redis（``agent:uiack:{call_id}``，TTL 60），
   等待方按 :data:`ACK_POLL_INTERVAL` 轮询。间隔 0.05s 比
   ``question.py::_ANSWER_POLL_INTERVAL`` 的 0.2s 短一个数量级：那边等**人**
   （180s 里晚 200ms 无所谓），这里等一次已经发生的页面跳转（总窗口 2s，
   轮询慢半拍就等于白等）。
3. **超时后的积压**：2s 窗口会漏（律师正好切页、弱网、前端渲染慢）。漏了不能
   假装没发生——模型会一直以为自己什么都没看见。所以没等到就登记进
   :func:`push_pending` 的进程内积压表（按会话，TTL 60s，上限 20 条），由
   ① 同一会话的下一次 ``publish_ui_action``（把上一次的结果拼进这一次的返回值）
   ② 模型主动调 ``ui_action_results`` 两个消费点取走。

## 为什么积压表是进程内、不写 Redis

两个消费点都在**同一个进程**里：动作由某进程的 MCP 工具下发，下一次工具调用
也发生在该进程（共享 MCP 是单进程常驻；stdio 模式每个 pi 子进程自带一份，
自洽）。写 Redis 只会让「哪份积压是真的」变成两个真相，还要自己实现原子出队。
代价是进程重启会丢掉尚未取走的积压——可接受：它们最多 60s 就过期，且丢的是
「没被问起过的历史」，不是「当前的等待」。

## 为什么 TTL 与回执键同寿命（都是 60s）

积压表里只存「我们在等哪个 ``call_id``」，真正的结果要等回执 POST 落进 Redis
才有。回执键 60s 后过期，之后再取也补不到结果，所以积压留更久毫无意义。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
import os
import time
from typing import Any

from ..event_bus import redis_cache_enabled

logger = logging.getLogger(__name__)

#: 等回执的时长（秒）。``0`` = 不等，直接走积压（灰度/弱网想要的就是「立刻返回 + 稍后 poll」）。
ACK_WAIT_ENV = "FACHUAN_UI_ACTION_ACK_WAIT"
#: 默认 2s：短到不明显拖慢模型循环，长到够一次本地路由跳转（实测 100~600ms）。
DEFAULT_ACK_WAIT = 2.0
#: 硬上限 8s：这段等待发生在**模型循环内部**，每个动作都占着 pi 的执行位。
#: 一屏 6 个动作 × 8s = 48s 纯等待，与 ``question.py`` 的 180s 被审计收紧同理。
MAX_ACK_WAIT = 8.0

#: 轮询 Redis 的间隔（秒）。理由见模块 docstring：这里等的是「刚发生的跳转」。
ACK_POLL_INTERVAL = 0.05

#: 回执在 Redis 的键前缀（跨 worker 传递，与提问的 ``agent:question:answer:`` 同构）。
ACK_KEY_PREFIX = "agent:uiack:"
#: 回执 TTL：与等待窗口同量级，够跨 worker 取到即可。
ACK_TTL = 60
#: ``call_id → 派发它的会话`` 的键前缀（上行回执做归属校验用，TTL 同上）。
SESSION_KEY_PREFIX = "agent:uiack:session:"

#: 积压回执的存活时长（秒，与 :data:`ACK_TTL` 同寿命，理由见模块 docstring）。
PENDING_TTL = 60.0
#: 每会话最多留几条积压。超限丢**最旧**：模型会回头看的只有最近几个动作，
#: 留下 30 条中最老的 20 条反而全是噪音。
PENDING_CAP = 20

#: 缓存类可重试异常。不写 ``except Exception``：仓库的棘轮门禁
#: （``tests/ci/structure/test_exception_ratchet.py``）禁止扩大宽 except，
#: 而这两处失败本来就该降级（与 ``event_bus._CACHE_ERRORS`` 同口径）。
_CACHE_ERRORS: tuple[type[BaseException], ...] = (OSError, ValueError, TypeError, RuntimeError)


class _UiAckWaiter:
    """进程内等待器：把「前端执行结果」交回正在阻塞的调用方。

    形状照 ``question.py::_QuestionWaiter``：``asyncio.Event`` 只做同 worker 快路径，
    跨 worker 靠 Redis（见 :func:`wait`）。
    """

    def __init__(self) -> None:
        self._events: dict[str, asyncio.Event] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def register(self, call_id: str) -> asyncio.Event:
        async with self._lock:
            event = asyncio.Event()
            self._events[call_id] = event
            self._results.pop(call_id, None)
            return event

    async def resolve(self, call_id: str, payload: dict[str, Any]) -> bool:
        """前端 POST 回执后调用；返回本次是否真的唤醒了等待方。

        **幂等**：同一 ``call_id`` 的第二次提交返回 ``False``，且**不覆盖**第一次的值。
        前端会重试（网络抖动、用户刷新），晚到的第二份结果可能与第一份不同
        （第一次 ``ok``、重放时 ``aborted``），覆盖它等于让模型看到一次从未发生的执行。
        """
        async with self._lock:
            event = self._events.get(call_id)
            if event is None:
                return False
            if event.is_set():
                return False
            self._results[call_id] = payload
            event.set()
            return True

    async def take_result(self, call_id: str) -> dict[str, Any] | None:
        async with self._lock:
            return self._results.get(call_id)

    async def discard(self, call_id: str) -> None:
        async with self._lock:
            self._events.pop(call_id, None)
            self._results.pop(call_id, None)

    def event_for(self, call_id: str) -> asyncio.Event | None:
        """已登记的等待对象（没登记过返回 ``None``）。

        不加锁读 dict：调用方一定是「刚 ``register`` 过的同一个协程」，
        没有多步写的竞态（锁保护的是 :meth:`resolve` 的「查—写—set」三步）。
        """
        return self._events.get(call_id)


_waiter = _UiAckWaiter()


def _cache() -> Any:
    """缓存客户端。延迟 import：本模块要能在**没有 Django settings** 的进程里 import
    （``python -m apps.agent.services.ui_action --ts`` 会先执行包 ``__init__``）。
    """
    from django.core.cache import cache

    return cache


def ack_wait_seconds() -> float:
    """``FACHUAN_UI_ACTION_ACK_WAIT``：等回执的秒数（默认 2.0，clamp 0~8）。

    非法值回默认并告警而不是抛：这个变量是**运维开关**，写错一个字符就让整条
    UI 动作通道失效，代价远高于「按默认值继续 + 日志里说一句」。NaN/±inf 一并
    算非法——``float()`` 接受它们，而它们会让 clamp 形同虚设（``min(nan, 8)`` 仍是 nan，
    一路传进 ``asyncio.wait_for`` 就是永不超时）。
    """
    raw = os.environ.get(ACK_WAIT_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_ACK_WAIT
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        logger.warning("非法 %s=%r，按默认 %ss 处理", ACK_WAIT_ENV, raw, DEFAULT_ACK_WAIT)
        return DEFAULT_ACK_WAIT
    if not math.isfinite(seconds):
        logger.warning("非有限值 %s=%r，按默认 %ss 处理", ACK_WAIT_ENV, raw, DEFAULT_ACK_WAIT)
        return DEFAULT_ACK_WAIT
    return min(max(seconds, 0.0), MAX_ACK_WAIT)


def _store_ack(call_id: str, payload: dict[str, Any]) -> bool:
    """把回执写进 Redis（跨 worker 的唯一通道）；返回本次是否为**第一次**写入。

    用 ``cache.add`` 而不是 ``cache.set``：它是原子的「只有第一个写入者成功」，
    正好就是重复提交的幂等判据——两个进程同时收到同一份重试，也只落一份。
    """
    if not redis_cache_enabled():
        return False
    try:
        return bool(_cache().add(f"{ACK_KEY_PREFIX}{call_id}", json.dumps(payload, ensure_ascii=False), ACK_TTL))
    except _CACHE_ERRORS:
        # 写失败 = 跨 worker 的等待者读不到回执，会表现为「页面明明变了、模型说没看见」，
        # 属用户可见的无法解释结果，按根 CLAUDE.md 标准不低于 warning。
        logger.warning("写 UI 动作回执失败（跨 worker 等待者将读不到）: %s", call_id, exc_info=True)
        return False


def _read_ack(call_id: str) -> dict[str, Any] | None:
    """读别的进程写下的回执（本进程没有等待者时才用得上）。"""
    if not redis_cache_enabled() or not call_id:
        return None
    try:
        raw = _cache().get(f"{ACK_KEY_PREFIX}{call_id}")
    except _CACHE_ERRORS:
        logger.warning("读取 UI 动作回执失败（跨 worker 等待者读不到结果）: %s", call_id, exc_info=True)
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


async def register(call_id: str) -> asyncio.Event:
    """登记一个等待者，**必须在 ``publish`` 之前**调（否则前端快答的回执找不到人）。

    返回的 Event 不交给调用方使用：``wait`` 会从登记表里取同一份对象，封装在这里是
    为了避免「调用方自己存着 event、却又靠轮询 Redis 取结果」两套真相。
    """
    return await _waiter.register(call_id)


async def resolve(call_id: str, payload: dict[str, Any]) -> bool:
    """前端提交回执的唯一入口（HTTP 端点调用）。

    Returns:
        这份回执是否**被某个等待方收下**（本进程唤醒了，或写进 Redis 供别的
        进程取）。``False`` 不是错误：模型只等 2 秒，律师慢一步就是超时——回执
        仍应被记录，但要让前端知道「本轮已按超时继续」，别弹成失败。
    """
    woken = await _waiter.resolve(call_id, payload)
    stored = _store_ack(call_id, payload)
    return woken or stored


async def discard(call_id: str) -> None:
    """收工：把等待对象与结果一并丢掉（``publish_ui_action`` 的 ``finally`` 调）。

    不丢就是每次下发漏一个 dict 项（常驻进程无限长大），而且之后到的回执会
    “找到人”却没人读——那个回执看起来被收下了，实际什么也影响不到。
    """
    await _waiter.discard(call_id)


async def wait(call_id: str, timeout: float) -> dict[str, Any] | None:
    """等回执；返回执行结果，超时返回 ``None``（不抛异常——调用方据此走积压分支）。

    本地 event 是快路径、Redis 是跨 worker 的唯一通道，两条都要看：先看本地
    （零开销、无网络），再每 :data:`ACK_POLL_INTERVAL` 秒读一次 Redis。
    """
    if timeout <= 0:
        return None
    event = _waiter.event_for(call_id)
    if event is None:
        # 没登记过 = 本次不打算等（``ACK_WAIT=0``）或调用方忘了 register。
        return None
    if event.is_set():
        # 回执先于 wait 到达（register → publish → 前端 200ms 内就答）：不能因为
        # 「进函数时还什么都没发生」就漏掉它。
        return await _waiter.take_result(call_id)
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        # 用 wait_for 包住而不是裸 event.wait()：超时必须能打断等待，否则 pi 的
        # 执行位会被一个永不到来的回执占死（同 ``question.py::_wait_answer``）。
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(event.wait(), min(ACK_POLL_INTERVAL, remaining))
        if event.is_set():
            return await _waiter.take_result(call_id)
        remote = _read_ack(call_id)
        if remote is not None:
            return remote


def mark_dispatch_session(call_id: str, session_id: str) -> None:
    """记下 ``call_id`` 是**哪个会话**派发的，供上行回执做归属校验。

    只写 Redis（TTL 与回执同寿命）：派发在 MCP 进程、回执 POST 在 Django 进程，
    归属信息必须跨进程。没有共享缓存时不保留进程内副本——那种部署下回执本来就
    到不了等待方（见模块 docstring），多一份本地真相只会让人查错方向。
    """
    if not redis_cache_enabled():
        return
    try:
        _cache().set(f"{SESSION_KEY_PREFIX}{call_id}", session_id, ACK_TTL)
    except _CACHE_ERRORS:
        logger.warning("记录 UI 动作归属失败（上行回执将无法校验归属）: %s", call_id, exc_info=True)


def dispatch_session(call_id: str) -> str | None:
    """``mark_dispatch_session`` 写下的会话 id；过期或没记过返回 ``None``。"""
    if not redis_cache_enabled() or not call_id:
        return None
    try:
        raw = _cache().get(f"{SESSION_KEY_PREFIX}{call_id}")
    except _CACHE_ERRORS:
        logger.warning("读取 UI 动作归属失败（上行回执将按「无法校验」处理）: %s", call_id, exc_info=True)
        return None
    return str(raw) if raw else None


#: 每会话的积压：``session_id -> [(写入时刻, {call_id, action}), ...]``（最旧在前）。
#: 用 ``time.monotonic()`` 记 TTL 而不是墙钟：系统时间被校准时，墙钟差值会让刚写进去的
#: 结果显示为「已过期」，或者永不过期。
_PENDING: dict[str, list[tuple[float, dict[str, Any]]]] = {}


def _live_rows(session_id: str, now: float) -> list[tuple[float, dict[str, Any]]]:
    """丢掉过期项并返回剩余；顺手清掉空会话，免得字典跟着会话数无限长大。"""
    rows = [(stamp, ref) for stamp, ref in _PENDING.get(session_id, []) if now - stamp < PENDING_TTL]
    if rows:
        _PENDING[session_id] = rows
    else:
        _PENDING.pop(session_id, None)
    return rows


def push_pending(session_id: str, ref: dict[str, Any]) -> None:
    """把「没等到回执」的动作登记进积压表，等下一次工具调用取走。

    ``ref`` 只含 ``call_id`` / ``action``：结果此刻**还不存在**（页面没回执），
    取走时才去 Redis 补（见 :func:`drain_pending`）。

    同步实现（不再 await）：drain → push 必须连续完成，中间出现 await 点就会
    让别的协程把当次动作 drain 走，变成「自己拼进自己的返回值」。
    """
    now = time.monotonic()
    rows = _live_rows(session_id, now)
    rows.append((now, dict(ref)))
    _PENDING[session_id] = rows[-PENDING_CAP:]


def drain_pending(session_id: str) -> list[dict[str, Any]]:
    """取走并清空该会话的积压回执（TTL 内，最旧在前）。

    取走时用 :func:`_read_ack` 补上结果：积压表里只有「我们在等哪个 ``call_id``」，
    真正的执行结果要等回执 POST 才产生、且落在**另一个进程**。补不到的记
    ``outcome="unknown"``——页面始终没有回执，模型据此**不能**断言成功。

    **报一次就丢掉**（不留在表里等下一次机会）：同一条结果在之后每次工具返回里
    重复出现，既把返回体撑满，也会让模型以为那是刚发生的新动作。
    """
    rows = _live_rows(session_id, time.monotonic())
    _PENDING.pop(session_id, None)
    drained: list[dict[str, Any]] = []
    for _stamp, ref in rows:
        item = dict(ref)
        item["outcome"] = "unknown"
        payload = _read_ack(str(ref.get("call_id") or ""))
        if payload is not None:
            item["outcome"] = str(payload.get("outcome") or "unknown")
            for field in ("code", "detail", "location"):
                value = str(payload.get(field) or "").strip()
                if value:
                    item[field] = value
        drained.append(item)
    return drained
