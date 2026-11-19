"""轮次级 API Key 调度：同一轮的 N 个 agent 各拿一把**不同**的 key。

## 为什么需要它（实测账）

律所 LiteLLM 网关对**每把 key** 限制 ``max_parallel_requests = 3``，实测响应头：

    x-ratelimit-api-key-limit-max_parallel_requests: 3
    status=429  retry-after: 60  rate_limit_type: max_parallel_requests

超限时网关返回 429 + ``retry-after: 60``，SDK 自动重试 → 那一栏的表现是「卡住
60 秒」（压测里见过 60.96s / 130.20s / 241.02s，全是 60 的整数倍）。

而本系统一个会话同时有三把 key 可用（``LLMProvider.api_keys`` 实测 5 把），
**三 agent 同答却可能撞到同一把上**——因为 ``_next_key`` 是全局轮转计数：

- 它只保证「先后两次调用拿到的通常不同」，**不保证**同一轮的三个 agent 不同
  （三个协程各自的取 key 时刻之间可以插进别的会话的请求）；
- 它**不知道**哪把 key 已经有 3 个请求在飞，照样发过去 → 429；
- 429 重试仍在同一把 key 上 → 等满 60 秒。

所以「三 agent 用三把 key」必须是**轮次级显式分配**，而不是指望轮转运气。

## 语义

- :meth:`KeyScheduler.allocate` 一次给出 ``count`` 把**互不相同**的 key；
- 优先挑**在飞数最少**的（分散负载），跳过已达 :data:`capacity` 的；
- 全部饱和时仍返回（best-effort）并 WARNING —— 此时宁可排队也不让整轮失败；
- key 不够 ``count`` 把时循环复用（尽量分散），并 WARNING。**不报错**：少几个
  key 是运维配置问题，不该让律师的提问失败。

## 红线：key 不进日志

本模块的 :class:`KeyLease` 持明文 key（要传给后端），但**任何日志/异常消息里
只出现指纹前缀**（:func:`fingerprint`）。调用方也不要打 repr(lease)。
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Iterable

logger = logging.getLogger(__name__)

#: 每把 key 允许的并发请求数。与网关 ``max_parallel_requests`` 同口径（实测 3）。
#:
#: 配置成**保守值**（等于网关值）而不是更大：我们没法从网关读到实时余量，
#: 只能靠这个数近似。设大了会频繁 429，设小了浪费并发槽。
CAPACITY_ENV = "FACHUAN_GATEWAY_KEY_CONCURRENCY"
DEFAULT_CAPACITY = 3


def capacity() -> int:
    """每把 key 的并发上限（``FACHUAN_GATEWAY_KEY_CONCURRENCY``，默认 3）。"""
    raw = (os.environ.get(CAPACITY_ENV, "") or "").strip()
    if not raw:
        return DEFAULT_CAPACITY
    try:
        value = int(raw)
    except ValueError:
        logger.warning("%s=%r 不是整数，用默认 %d", CAPACITY_ENV, raw, DEFAULT_CAPACITY)
        return DEFAULT_CAPACITY
    return max(1, min(value, 64))


#: 每把 key 的**进程内别名**（``key-1`` / ``key-2``…）。
#:
#: ## 为什么不用哈希
#:
#: 这里只需要一个「能区分是哪把 key」的标签，打日志/写断言用。任何**从 key 内容
#: 推导**出来的值都会有两个毛病：
#:
#: 1. **安全扫描器一律报**「不安全的密码哈希」——裸 SHA256 报、带盐 blake2b 也报
#:    （CodeQL ``py/weak-sensitive-data-hashing`` 只看「快速哈希 + 敏感数据」这个
#:    组合，不看我们其实不是存密码）。实测两种算法都被拦，静态检查过不去。
#: 2. 即使加了盐，哈希仍然是「从秘密派生出的稳定值」，在日志里多留一份可被离线
#:    尝试的材料，收益为零。
#:
#: 别名方案没有这两个问题：它**与 key 内容无关**（只是一个递增编号），泄露不了
#: 任何信息，也不需要哈希。代价是别名只在**本进程内**稳定（重启后可能换号）——
#: 而这正是它的用途边界：日志里「这一轮用的是 key-2」不跨进程比对。
_ALIASES: dict[str, str] = {}
_ALIAS_LOCK = threading.Lock()


def fingerprint(api_key: str) -> str:
    """key 的短标签（可安全进日志）。空 key 给 ``(empty)``。

    返回形如 ``key-1`` 的进程内别名（见 ``_ALIASES``）：同一把 key 在同一次进程
    生命周期内拿到同一个标签，不同 key 一定不同，但**标签本身不携带 key 的任何
    信息**。
    """
    text = (api_key or "").strip()
    if not text:
        return "(empty)"
    with _ALIAS_LOCK:
        alias = _ALIASES.get(text)
        if alias is None:
            alias = f"key-{len(_ALIASES) + 1}"
            _ALIASES[text] = alias
        return alias


@dataclass
class KeyLease:
    """一轮里某一栏占用的 key。用完必须 :meth:`release`（或用 ``with``）。"""

    key: str
    _scheduler: KeyScheduler = field(repr=False)
    _released: bool = field(default=False, repr=False)

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._scheduler._release(self.key)

    def __enter__(self) -> KeyLease:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()

    @property
    def label(self) -> str:
        """日志用标签（``sk-abc1…`` 形式，绝不含完整 key）。"""
        return f"key#{fingerprint(self.key)}"


class KeyScheduler:
    """进程内的 key 在飞计数 + 轮次级分配。

    **进程内**就够了：并发闸门的意义是「当下有几个请求在用这把 key」，而这个
    事实只有发起请求的进程知道。跨 worker 的精确协调需要 Redis，收益不抵复杂度
    —— worst case 是多个 worker 各按自己的计数发，等价于现在的行为，不会更差。
    """

    def __init__(self) -> None:
        self._inflight: dict[str, int] = {}
        # 轮转起点：同一次 allocate 内从不同位置开始，避免每次都把负载压到前几把。
        self._cursor = 0
        # 同步原语用 threading.Lock 而不是 asyncio.Lock：本模块的临界区是纯字典
        # 操作（无 await），用同步锁反而能同时服务 async 与 sync 调用方（pi 的
        # models.json 是在同步路径上写的）。
        self._lock = threading.Lock()

    # ── 分配 ────────────────────────────────────────────────────────────

    def allocate(self, keys: Iterable[str], count: int) -> list[KeyLease]:
        """为同一轮的 ``count`` 栏分配 key（互不相同，优先低负载）。

        Args:
            keys: 可用 key 列表（``LLMProvider.api_keys`` 解析结果）。
            count: 本轮需要几把（= 参与 agent 数）。

        Returns:
            长度恒为 ``count`` 的租约列表。``keys`` 为空时返回空串租约。
        """
        pool = [k for k in (keys or []) if (k or "").strip()]
        if count <= 0:
            return []
        if not pool:
            # 没有任何 key：让后端自己按它原有口径处理（通常直接报「未配置平台」）。
            return [KeyLease(key="", _scheduler=self) for _ in range(count)]

        cap = capacity()
        with self._lock:
            start = self._cursor % len(pool)
            self._cursor = (self._cursor + count) % max(1, len(pool))

            # 先按轮转起点旋转，再按「在飞数升序」稳定排序。
            #
            # 顺序不能省：只按在飞数排的话，所有 key 负载相同时会**永远挑前面几个**，
            # 后面的 key 闲置——这正是「三栏总用 A/B/C」的成因（实测踩过：修之前
            # 连跑两轮都拿到 sk-A/sk-B/sk-C，第 5 把 key 一次没用到）。
            rotated = pool[start:] + pool[:start]
            order = sorted(range(len(rotated)), key=lambda i: (self._inflight.get(rotated[i], 0), i))
            chosen: list[str] = []

            # 第一轮：只挑未饱和的，且不与已选的重复
            for idx in order:
                if len(chosen) >= count:
                    break
                key = rotated[idx]
                if key in chosen:
                    continue
                if self._inflight.get(key, 0) >= cap:
                    continue
                chosen.append(key)

            # 第二轮：key 不够（或不饱和的太少）时循环复用，尽量分散。
            # 不报错——少几把 key 是配置问题，不该让律师的提问失败。
            if len(chosen) < count:
                if len(pool) < count:
                    logger.warning(
                        "只有 %d 把 key，本轮要 %d 栏：将循环复用（并发能力上限 %d）",
                        len(pool),
                        count,
                        len(pool) * cap,
                    )
                else:
                    logger.warning(
                        "全部 %d 把 key 都已达到并发上限 %d，本轮 %d 栏可能有请求排队（429 后重试）",
                        len(pool),
                        cap,
                        count,
                    )
                i = 0
                while len(chosen) < count:
                    chosen.append(pool[(start + i) % len(pool)])
                    i += 1

            for key in chosen:
                self._inflight[key] = self._inflight.get(key, 0) + 1

        return [KeyLease(key=k, _scheduler=self) for k in chosen]

    # ── 归还 ────────────────────────────────────────────────────────────

    def _release(self, key: str) -> None:
        if not key:
            return
        with self._lock:
            current = self._inflight.get(key, 0)
            if current <= 1:
                self._inflight.pop(key, None)
            else:
                self._inflight[key] = current - 1

    # ── 诊断 ────────────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, int]:
        """当前在飞数快照（键是指纹，可安全打印）。仅用于诊断与测试。"""
        with self._lock:
            return {fingerprint(k): v for k, v in self._inflight.items()}

    def reset(self) -> None:
        """清空计数（测试用）。"""
        with self._lock:
            self._inflight.clear()
            self._cursor = 0


_scheduler = KeyScheduler()


def get_key_scheduler() -> KeyScheduler:
    """进程级调度器单例。"""
    return _scheduler


__all__ = [
    "CAPACITY_ENV",
    "DEFAULT_CAPACITY",
    "KeyLease",
    "KeyScheduler",
    "capacity",
    "fingerprint",
    "get_key_scheduler",
]
