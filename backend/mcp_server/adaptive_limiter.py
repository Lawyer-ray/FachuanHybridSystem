"""自适应并发调度：在「硬件上限」之下自己找安全水位。

## 为什么不能写死一个数（2026-11-21 实测）

律所网关给每个 key 的并行上限是 3，我们有 10 把 key ⇒ **硬上限 30**。
但把 30 个请求同时放出去，上游检索服务顶不住：

| 并发 | 成功 | 耗时 | 现象 |
|---|---|---|---|
| 5 | 5/5 | 2.4s | 正常 |
| 10（每 key 1） | 10/10 | 2.8s | 安全 |
| 20 | 14/20 | 48.5s | 45s 超时 + 空 pages |
| 30（打满 30 槽位） | 22/30 | 23s，p50 21s | **27% 返回空 pages** |

也就是说：**网关限额 ≠ 上游能吃下的量**。而「上游能吃多少」会随外部因素变
（百炼侧负载、网络、查询复杂度），任何写死的常量都会在某个时刻变成错误的：
调小了浪费 30 个槽位、调大了把上游打爆（空结果比失败更糟——模型会以为真没资料）。

## 所以：窗口采样 + 梯度升降（Vegas/AIMD 思路）

- 记一个「历史最快延迟」``base``（只要观测到更快的样本就下调，代表链路底噪）；
- 每完成一个窗口的请求，看窗口 p50：
  - ``p50 <= base * UP_RATIO``（延迟接近底噪）→ 还有余量，``+1`` 慢增；
  - ``p50 >= base * DOWN_RATIO``（明显排队）→ ``减半`` 快降；
  - 中间保持。
- 上游明确报错（``empty`` / 429 / 超时）→ 不等窗口，立刻 ``-2``：这些都是
  「已经压过界」的直接信号，等比延迟统计更及时。
- ``limit`` 永远夹在 ``[1, max_limit]``，``max_limit`` 就是「key 数 × 每 key 并发」。

效果：轻负载时自动爬到 30 吃满所有 key；一旦上游开始排队就自己退回来，
不需要运维去调 ``MAX_CONCURRENT``（该环境变量现在只当**上限封顶**用）。

## 为什么状态可以放进程内 / 不需要持久化

它只是「当前该放几个请求过去」的估计值，丢了从 1 开始慢爬即可——最坏影响是
冷启动头几个请求慢一点，不会给出错误答案。共享 MCP 只有一个进程，
所以这份估计等于「全所的检索并发」。
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

__all__ = ["AdaptiveLimiter"]


class AdaptiveLimiter:
    """窗口采样的自适应并发闸门（阻塞式获取槽位，不做忙等）。

    Args:
        max_limit: 硬上限（= key 数 × 每 key 并发）。永远不越过它。
        min_limit: 下限，默认 1；再差也要放一个请求过去，否则整条通道等于关闭。
        window: 每多少个完成样本调整一次 limit。
        up_ratio: 窗口 p50 低于 ``base * up_ratio`` 时加一。
        down_ratio: 窗口 p50 高于 ``base * down_ratio`` 时减半。
        clock: 单调时钟（单测注入）。
    """

    UP_RATIO = 1.6
    DOWN_RATIO = 2.5
    WINDOW = 8
    #: 冷启动窗口更小：前几次调用就能判断链路底噪，不必等满 8 个样本。
    START_WINDOW = 2

    def __init__(
        self,
        max_limit: int,
        min_limit: int = 1,
        initial: int | None = None,
        window: int = WINDOW,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_limit = max(1, int(max_limit))
        self.min_limit = max(1, min(int(min_limit), self.max_limit))
        self._window_size = max(1, int(window))
        self._clock = clock
        self._cond = threading.Condition()
        self._in_flight = 0
        # 起步值：默认调用方给「每 key 1 并发」（实测安全水位），而不是 1。
        # 从 1 起步在 30 并发下等于把大多数调用排队排死（实测 7/30 就被 busy 挡掉），
        # 而一上来就给满 30 会踩「27% 空结果」。从安全水位开始向上试探最稳。
        start = self.min_limit if initial is None else int(initial)
        self._limit = max(self.min_limit, min(self.max_limit, start))
        self._base: float | None = None
        self._samples: deque[float] = deque(maxlen=self._window_size)
        self._adjustments = 0
        #: 慢启动阶段（翻倍上涨），一旦观测到排队/过载就转入「加性增长、乘性下降」。
        #: 没有慢启动时每次只 +1，30 个槽位要 240 个样本才爬满——高峰期等于常年低并发。
        self._slow_start = True

    # ── 只读观察面（日志/压测用）────────────────────────────────────────
    @property
    def limit(self) -> int:
        with self._cond:
            return self._limit

    @property
    def in_flight(self) -> int:
        with self._cond:
            return self._in_flight

    @property
    def base_latency(self) -> float | None:
        with self._cond:
            return self._base

    @property
    def adjustments(self) -> int:
        with self._cond:
            return self._adjustments

    # ── 槽位 ────────────────────────────────────────────────────────────
    def acquire(self, timeout: float) -> bool:
        """取一个槽位；``timeout`` 秒内拿不到返回 ``False``（调用方快速失败）。"""
        deadline = self._clock() + max(0.0, timeout)
        with self._cond:
            while self._in_flight >= self._limit:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
            self._in_flight += 1
            return True

    def release(self, *, latency: float | None = None, overload: bool = False) -> None:
        """还槽位，并用这次的结果更新水位估计。

        Args:
            latency: 本次调用耗时（秒）。``None`` 表示这次没拿到有效样本
                （比如在本地就失败了），不参与延迟统计。
            overload: 上游是否报了「压过界」类错误（``empty`` / 429 / 超时）。
        """
        with self._cond:
            self._in_flight = max(0, self._in_flight - 1)
            if overload:
                # 明确过载信号：不等窗口，立刻退让（多把 key 同时报空说明是上游，
                # 不是某一把 key 的问题），并退出慢启动。
                # 退让幅度固定 -2。实测对比：按比例退让（-limit/4）会让 limit
                # 一路崩到 1-2，随后每次请求都排队、又触发更多过载信号，
                # 30 并发成功率从 30/30 掉到 20/30。固定步长慢但如果真过载会
                # 连续命中，退得也够快。
                self._limit = max(self.min_limit, self._limit - 2)
                self._slow_start = False
                self._adjustments += 1
                self._samples.clear()
            elif latency is not None and latency > 0:
                if self._base is None or latency < self._base:
                    self._base = latency
                self._samples.append(latency)
                # 慢启动阶段用更小的窗口：冷启动几次调用就够判断底噪，
                # 不必先攒满 8 个样本（那在高峰期等于常年低并发）。
                threshold = self.START_WINDOW if self._slow_start else self._window_size
                if len(self._samples) >= min(threshold, self._window_size):
                    self._adjust()
            self._cond.notify_all()

    def _adjust(self) -> None:
        samples = sorted(self._samples)
        self._samples.clear()
        base = self._base or samples[0]
        p50 = samples[len(samples) // 2]
        if p50 <= base * self.UP_RATIO and self._limit < self.max_limit:
            # 慢启动阶段翻倍（10 → 20 → 30），之后只 +1 稳步试探。
            # 实测：改成 1.5 倍增长反而更差（30 并发 30/30 → 20/30），因为爬升慢
            # 导致请求排队更久、排队又触发了更多「空结果」过载信号。
            step = self._limit if self._slow_start else 1
            self._limit = min(self.max_limit, self._limit + step)
            self._adjustments += 1
        elif p50 >= base * self.DOWN_RATIO and self._limit > self.min_limit:
            self._limit = max(self.min_limit, self._limit // 2)
            self._slow_start = False
            self._adjustments += 1

    @property
    def slow_start(self) -> bool:
        with self._cond:
            return self._slow_start

    def snapshot(self) -> dict[str, float | int | None]:
        """一行日志用的快照。"""
        with self._cond:
            return {
                "limit": self._limit,
                "max": self.max_limit,
                "in_flight": self._in_flight,
                "base": round(self._base, 3) if self._base else None,
                "adjustments": self._adjustments,
            }
