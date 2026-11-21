"""给「不占槽位」的调用方挑一把 Key：跳过别的进程判定不健康的那些。

## 为什么需要它（2026-11-21 审计 P0-1 / S4）

真正持有槽位的路径（core `LLMClient` 与检索通道）用 ``KeyPool.acquire``，并发与
冷却都精确记账。但律师日常对话走的是 **pi / dsh / openai-agents** 三条后端路径：
它们在**外部进程**里直接跟网关说话，我们只能把 key 写进配置交给它们，拿不到
「请求开始/结束」这两个时刻——所以**不能**在这里 acquire 槽位（会泄漏）。

这些路径原来用 ``_next_key``：一个 `itertools.count()` 取模的全局轮转。它有两个
已知问题（``key_scheduler`` docstring 也写了）：

1. **不知道哪把 Key 已经被别的进程判死**（401/429 冷却中）→ 反复选中坏 Key；
2. 只保证「先后两次通常不同」，并发高时仍会撞到同一把。

这里做**读侧**最小修复：在健康（未必最优，但绝不选已知坏 Key）的前提下轮转。
「在飞数」的精确协调留给持有租约的路径（``KeyScheduler`` / ``KeyPool``）。

## 为什么全冷却时仍要返回一把

宁可发一个可能 429 的请求，也不要让律师的提问卡在「没有可用 Key」。冷却只是
**概率上的坏**，不是**确定不可用**——fail-open 与 ``key_health`` 的原则一致。
"""

from __future__ import annotations

import itertools
import logging

from apps.core.infrastructure.cache import CACHE_ERRORS

logger = logging.getLogger(__name__)

#: 进程内轮转计数（``next()`` 在 CPython 下原子，无需锁）。
_rotation = itertools.count()


def select_key(api_keys: list[str], provider: str = "") -> str:
    """从 ``api_keys`` 里挑一把：先剔除**跨进程判定冷却中**的，再轮转。

    Args:
        api_keys: 候选 Key（保持配置顺序）。
        provider: 平台名（跨进程健康记账的一维键）。为空则跳过健康过滤
            （拿不到平台名时退化为旧行为，不做半吊子过滤）。

    Returns:
        选中的 Key；``api_keys`` 为空时返回空串。
    """
    keys = [key for key in (api_keys or []) if (key or "").strip()]
    if not keys:
        return ""

    healthy = keys
    if provider:
        try:
            from apps.core.llm.key_health import cooling_map

            cooling = cooling_map(provider, keys)
            if cooling:
                survivors = [key for key in keys if key not in cooling]
                if survivors:
                    logger.info(
                        "Key 选择：跳过 %d 把冷却中的 Key（平台 %s，剩 %d 把可用）",
                        len(keys) - len(survivors),
                        provider,
                        len(survivors),
                    )
                    healthy = survivors
                # survivors 为空 = 全部冷却 → 保持全量轮转（fail-open，见模块 docstring）
        except CACHE_ERRORS:  # pragma: no cover - 缓存不可用则按全健康处理
            logger.debug("读取跨进程 Key 健康失败，按全健康轮转", exc_info=True)

    return healthy[next(_rotation) % len(healthy)]


__all__ = ["select_key"]
