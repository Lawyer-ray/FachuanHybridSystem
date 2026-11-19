"""开流前固定开销打点（``FACHUAN_AGENT_PROFILE=1`` 开启，默认关）。

## 为什么需要它

三 agent 同答时 ``stream_chat`` 会被调用 N 次，每次都要铸凭证、探 pi session、
可能查一次历史。这些都是**开流前的固定开销**，直接摊在首字延迟上，但它们全部
走 ``sync_to_async(thread_sensitive=True)``——在同一个线程上排队，只看总时长
分不出哪一段占多少、重复了几遍。这里给每段单独计时，一份日志就能读出
「哪项是真重复、重复了 N 次、每次几毫秒」。

## 为什么默认关

生产路径不该为诊断付开销：关闭时只多一次 ``os.environ`` 读取，不取时间戳、
不写日志。开启时也只走 ``logger.info``，不做进程内汇总——汇总口径一旦写死，
下一次改动就会悄悄失真，不如让人对着日志自己加。
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

logger = logging.getLogger(__name__)

#: 打点开关（``1`` / ``true`` / ``yes`` / ``on`` 开启，其余一律关闭）
PROFILE_ENV = "FACHUAN_AGENT_PROFILE"

_OPEN_VALUES = frozenset({"1", "true", "True", "yes", "on"})


def enabled() -> bool:
    """本次是否打点。每次都读 env：排查时改环境变量不必等进程重启。"""
    return os.environ.get(PROFILE_ENV, "").strip() in _OPEN_VALUES


def _log(stage: str, elapsed_ms: float, fields: dict[str, Any]) -> None:
    detail = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info("[agent-profile] %s %.2fms %s", stage, elapsed_ms, detail)


@asynccontextmanager
async def timed(stage: str, **fields: Any) -> AsyncIterator[None]:
    """给一段开流前的固定开销计时并写一条日志；未开启时零日志零时间戳。"""
    if not enabled():
        yield
        return
    started = time.perf_counter()
    try:
        yield
    finally:
        _log(stage, (time.perf_counter() - started) * 1000.0, fields)


def since(stage: str, started: float, **fields: Any) -> None:
    """补一条「从 ``started`` 到现在」的耗时（用于多段之和的合计行）。"""
    if not enabled():
        return
    _log(stage, (time.perf_counter() - started) * 1000.0, fields)


__all__ = ["PROFILE_ENV", "enabled", "since", "timed"]
