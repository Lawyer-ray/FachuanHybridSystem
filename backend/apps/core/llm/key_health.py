"""跨进程的 Key 健康记账 + 平台配置「代次」计数器（Django cache，**fail-open**）。

## 为什么需要跨进程（2026-11-21 审计 P0-2 / P1-6）

生产拓扑是 `2 个 gunicorn worker + 1 个共享 MCP 进程`，而 Key 冷却与平台配置缓存
原本都是**进程内**的：

- 某把 Key 在 worker A 里因 401 被冷却，worker B 与 MCP 进程都不知道 → 同一个坏
  Key 会被反复选中、反复吃 401；
- Admin 换 Key 后只有「保存的那个 worker」清缓存，其它进程要等 TTL（MCP 与
  服务路径都是 **300 秒**）→ 用户看到「聊天好了、检索还用旧 Key」。

所以这里补两样最小可用的跨进程状态，全部走 `django.core.cache`：
配 Redis 即为全局共享，未配则 LocMem（**等价于今天的进程内行为，不会更差**）。

## 红线一：**fail-open**，不是 fail-closed

缓存抖动/不可用时，健康查询必须返回「健康」、代次查询返回「不变」。Fail-closed
会让一次 Redis 抖动把整个 Key 池判死——那比读不到状态糟糕得多。所有函数内部
`except Exception` 吞掉并 debug 记录。

## 红线二：Key 明文与可枚举指纹都不进缓存键

缓存键里出现 Key 明文（或裸 SHA256）会被安全扫描器一律拦下（见
`key_scheduler.fingerprint` 的同类论证）。这里复用仓库既有的 HMAC 派生
（`apps.core.infrastructure.cache._hash_key_component`，SECRET_KEY 为密钥），
既有非可枚举性、也不会被 `py/weak-sensitive-data-hashing` 命中。

## 红线三：健康状态必须有 TTL

冷却时间到点必须自动消失（缓存 TTL 就是它的生命周期）。**没有**「永久标记某把
Key 坏了」这种状态：那会让一次误判把 Key 永久排除，而运维只能靠改配置来救。
`401/403` 这类鉴权错也只用较长的 TTL（默认 600 秒）而不是永久。
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

#: 平台配置代次计数器：Admin 保存时 +1，各进程**每次取配置**时比对一次。
CONFIG_GENERATION_KEY = "llm:config:generation"

#: 单个 Key 冷却状态的键前缀。
_HEALTH_PREFIX = "llm:keyhealth"

#: 缓存不可用时的降级返回值（fail-open）。
_HEALTHY = 0.0


@dataclass(frozen=True)
class KeyHealth:
    """一把 Key 的冷却状态快照（只读）。"""

    remaining: float
    reason: str

    @property
    def cooling(self) -> bool:
        return self.remaining > 0


# ── 内部：缓存访问一律包一层，失败即降级 ────────────────────────────────


def _cache() -> Any | None:
    try:
        from django.core.cache import cache

        return cache
    except Exception:  # pragma: no cover - Django 未就绪（脚本/单测早期）
        logger.debug("Django cache 不可用，Key 健康降级为进程内", exc_info=True)
        return None


def _key_id(api_key: str) -> str:
    """Key 的缓存键片段：HMAC(SECRET_KEY, key)，不携带可枚举的明文信息。"""
    try:
        from apps.core.infrastructure.cache import _hash_key_component

        return _hash_key_component(api_key)
    except Exception:  # pragma: no cover - 极端降级：用长度占位（不同 Key 会撞，但只影响健康判定）
        logger.debug("HMAC 派生失败，健康键退化为长度占位", exc_info=True)
        return f"len{len(api_key or '')}"


_UNSAFE_CACHE_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_provider_segment(provider: str) -> str:
    """平台名 → 缓存键安全片段。

    平台名是中文（「律所 kimi」）时直接拼进缓存键，Django 会抛
    ``CacheKeyWarning``（memcached 只接受 ASCII 且不含空格/控制字符）。这里保留
    可读前缀并附一段短摘要，既过静态检查又不丢可读性。
    """
    raw = (provider or "").strip()
    if not raw:
        return "default"
    safe = _UNSAFE_CACHE_CHARS.sub("_", raw)[:40]
    if safe == raw:
        return safe
    return f"{safe}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:8]}"


def _health_key(provider: str, api_key: str) -> str:
    return f"{_HEALTH_PREFIX}:{_safe_provider_segment(provider)}:{_key_id(api_key)}"


# ── 代次计数器（配置变更的跨进程通知）──────────────────────────────────


def config_generation() -> int:
    """当前平台配置代次；缓存不可用时返回 0（调用方据此判断「不知道」= 走 TTL）。"""
    cache = _cache()
    if cache is None:
        return 0
    try:
        return int(cache.get(CONFIG_GENERATION_KEY) or 0)
    except Exception:
        logger.debug("读取配置代次失败（按 0 处理）", exc_info=True)
        return 0


def bump_config_generation() -> int:
    """配置变更后 +1；返回新代次。任何 worker 调用都能让所有进程下一次取配置时重载。"""
    cache = _cache()
    if cache is None:
        return 0
    try:
        # add 失败（键不存在时置 0）再 incr，避免第一次 incr 抛 ValueError
        cache.add(CONFIG_GENERATION_KEY, 0, timeout=None)
        return int(cache.incr(CONFIG_GENERATION_KEY))
    except Exception:
        logger.debug("递增配置代次失败（其它进程只能等 TTL）", exc_info=True)
        return 0


# ── Key 冷却状态 ────────────────────────────────────────────────────────


def mark_cooling(provider: str, api_key: str, seconds: float, reason: str) -> None:
    """标记某把 Key 在 ``seconds`` 秒内不健康（TTL 到点自动失效）。"""
    cache = _cache()
    if cache is None or seconds <= 0:
        return
    payload = {"until": time.time() + float(seconds), "reason": (reason or "")[:120]}
    try:
        cache.set(_health_key(provider, api_key), payload, timeout=max(1, int(seconds)))
    except Exception:
        logger.debug("写 Key 冷却状态失败（仅本进程内生效）", exc_info=True)


def clear_cooling(provider: str, api_key: str) -> None:
    """该 Key 恢复正常（成功一次即可清除）。"""
    cache = _cache()
    if cache is None:
        return
    try:
        cache.delete(_health_key(provider, api_key))
    except Exception:
        logger.debug("清除 Key 冷却状态失败", exc_info=True)


def get_health(provider: str, api_key: str) -> KeyHealth:
    """读该 Key 的健康状态；缓存不可用或读失败一律视为**健康**（fail-open）。"""
    cache = _cache()
    if cache is None:
        return KeyHealth(remaining=_HEALTHY, reason="")
    try:
        payload = cache.get(_health_key(provider, api_key))
    except Exception:
        logger.debug("读 Key 健康状态失败（按健康处理）", exc_info=True)
        return KeyHealth(remaining=_HEALTHY, reason="")
    if not isinstance(payload, dict):
        return KeyHealth(remaining=_HEALTHY, reason="")
    remaining = float(payload.get("until") or 0) - time.time()
    if remaining <= 0:
        return KeyHealth(remaining=_HEALTHY, reason="")
    return KeyHealth(remaining=remaining, reason=str(payload.get("reason") or ""))


def cooling_map(provider: str, api_keys: list[str]) -> dict[str, KeyHealth]:
    """批量读（一次 ``get_many``，避免每把 Key 一次往返）；只返回冷却中的项。"""
    cache = _cache()
    if cache is None or not api_keys:
        return {}
    keys = [_health_key(provider, key) for key in api_keys]
    try:
        payloads = cache.get_many(keys)
    except Exception:
        logger.debug("批量读 Key 健康失败（按全部健康处理）", exc_info=True)
        return {}
    now = time.time()
    result: dict[str, KeyHealth] = {}
    for api_key, cache_key in zip(api_keys, keys):
        payload = payloads.get(cache_key)
        if not isinstance(payload, dict):
            continue
        remaining = float(payload.get("until") or 0) - now
        if remaining > 0:
            result[api_key] = KeyHealth(remaining=remaining, reason=str(payload.get("reason") or ""))
    return result


__all__ = [
    "CONFIG_GENERATION_KEY",
    "KeyHealth",
    "bump_config_generation",
    "clear_cooling",
    "config_generation",
    "cooling_map",
    "get_health",
    "mark_cooling",
]
