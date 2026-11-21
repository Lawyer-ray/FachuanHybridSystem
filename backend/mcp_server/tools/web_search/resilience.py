"""搜索通道的进程级韧性状态：结果缓存 + 通道熔断冷却。

## 为什么这两件事是必需的（2026-11-21 实测定案）

搜狗免费 HTML 搜索的封禁是 **IP 级**（302 → ``/captcha/?m=1&antip=web_sh2``），
不是 cookie 级、也不是关键词级：封禁期间换 UA、换 Referer、先抓首页养
cookie 全部无效；换手机 UA 走 ``wap.sogou.com`` 则正常（307KB 结果页）。
恢复至少 10 分钟（20 次探针 / 每 30 秒一次 / 10 分钟全拦）。

共享 MCP（streamable-http :8011）下**全所共用一个出口 IP**，于是：

1. **没有熔断**时，模型读到「被反爬」会按 ``web-research`` 技能的提示
   「换个关键词重试」——生产库实测会话 268 在 3 分钟内连打 20 次、全部被拦：
   既烧掉进程级 20 次/分配额（``_rate_limit``），又持续往封禁页送请求，
   延长封禁。
2. **没有结果缓存**时，多答双 lane（pi + openai-agents）对同一问题各搜一次
   （实测同一秒并发），一份结果付两次请求、两次封禁暴露。

## 状态为什么可以放进程内

两者都是**优化性状态**，不是数据：丢了只会退化成「多打一次请求」，不会
给出错误答案。因此不做持久化、不跨进程共享——重启即清空是正确的语义。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class ChannelBreaker:
    """按通道名记录冷却截止时刻；冷却期内**不再发起请求**。

    ``trip`` 之后该通道在 ``seconds`` 秒内被判定为「开着」（open），
    调用方应跳过而不是重试——冷却时长按失败类型区分（反爬最久、
    瞬时网络错误最短），语义见 ``web_search._COOLDOWN_*``。
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._until: dict[str, float] = {}
        self._reason: dict[str, str] = {}
        #: 连续失败次数：同一通道反复失败时冷却时长按 2× 递增（封顶 4×）。
        #: 依据：搜狗封禁实测 ≥10 分钟，而首次冷却只有 600s——到点立刻再撞等于
        #: 白送一次请求并重新计时（SearXNG 也是「按错误类型定长 + 连续失败加重」）。
        self._strikes: dict[str, int] = {}
        self._lock = threading.Lock()

    def info(self, channel: str) -> tuple[float, str]:
        """返回 ``(剩余秒数, 冷却原因)``；未冷却时剩余为 0。"""
        now = self._clock()
        with self._lock:
            until = self._until.get(channel, 0.0)
            if until <= now:
                self._until.pop(channel, None)
                self._reason.pop(channel, None)
                return 0.0, ""
            return until - now, self._reason.get(channel, "")

    def is_open(self, channel: str) -> bool:
        return self.info(channel)[0] > 0

    #: 连续失败的冷却倍数上限（1× → 2× → 4×）。
    MAX_STRIKE_MULTIPLIER = 4

    def trip(self, channel: str, reason: str, seconds: float) -> None:
        """让通道冷却 ``seconds`` 秒；**连续失败**时按 2× 递增（封顶 4×）。

        同通道重复 trip 取更晚的截止时刻。
        """
        if seconds <= 0:
            return
        with self._lock:
            strikes = self._strikes.get(channel, 0) + 1
            self._strikes[channel] = strikes
            multiplier = min(2 ** (strikes - 1), self.MAX_STRIKE_MULTIPLIER)
            until = self._clock() + seconds * multiplier
            if until > self._until.get(channel, 0.0):
                self._until[channel] = until
                self._reason[channel] = f"{reason}（第 {strikes} 次，冷却 ×{multiplier}）"

    def clear(self, channel: str) -> None:
        """通道恢复正常：冷却与**连续失败计数**一起清零。"""
        with self._lock:
            self._until.pop(channel, None)
            self._reason.pop(channel, None)
            self._strikes.pop(channel, None)

    def reset(self) -> None:
        """清空全部状态（测试用；生产不需要调用）。"""
        with self._lock:
            self._until.clear()
            self._reason.clear()
            self._strikes.clear()

    @property
    def strikes(self) -> dict[str, int]:
        """各通道的连续失败次数（只读快照，供诊断）。"""
        with self._lock:
            return dict(self._strikes)


class ResultCache:
    """``(query, page, max_results)`` → 已格式化输出的 TTL+LRU 缓存。

    缓存的是**格式化后的完整文本**，不是结构化结果：命中路径不重新格式化，
    连注入包裹标注都逐字节一致，模型看到的与首次检索完全相同。
    只缓存成功结果——失败结果由 ``ChannelBreaker`` 负责，混在一起会让
    「刚才失败」和「刚才没有结果」两种语义互相污染。
    """

    def __init__(
        self,
        ttl: float = 600.0,
        max_entries: int = 128,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl
        self._max = max_entries
        self._clock = clock
        self._entries: dict[tuple[str, int, int], tuple[float, str]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def key(query: str, page: int, max_results: int) -> tuple[str, int, int]:
        return (query.strip().lower(), page, max_results)

    def get(self, key: tuple[str, int, int]) -> str | None:
        now = self._clock()
        with self._lock:
            hit = self._entries.get(key)
            if hit is None:
                return None
            expires, value = hit
            if expires <= now:
                self._entries.pop(key, None)
                return None
            return value

    def put(self, key: tuple[str, int, int], value: str) -> None:
        now = self._clock()
        with self._lock:
            if len(self._entries) >= self._max:
                oldest = min(self._entries, key=lambda k: self._entries[k][0])
                self._entries.pop(oldest, None)
            self._entries[key] = (now + self._ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


__all__ = ["ChannelBreaker", "ResultCache"]
