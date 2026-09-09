"""进程内熔断器，用于 LLM 后端可靠性保护。

当某后端连续失败达到阈值即短路冷却，冷却期内由回退策略跳过该后端、
转而使用其余可用后端，避免对不可用服务持续轰炸造成雪崩。

线程安全：LLM 客户端为共享实例，需在并发请求下正确维护状态。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping


class CircuitBreaker:
    """按后端名跟踪连续失败，超过阈值后短路冷却。

    状态：
    - 连续失败计数失败达到 ``fail_threshold`` 后进入短路状态；
    - 冷却 ``cooldown_seconds`` 秒后自动复位（半开探活窗口）。
    """

    def __init__(self, *, fail_threshold: int = 5, cooldown_seconds: float = 30.0) -> None:
        if fail_threshold < 1:
            raise ValueError("fail_threshold 必须 >= 1")
        self.fail_threshold = fail_threshold
        self.cooldown_seconds = cooldown_seconds
        self._lock = threading.Lock()
        self._failures: dict[str, int] = {}
        self._tripped_until: dict[str, float] = {}

    def record_success(self, name: str) -> None:
        """后端调用成功，清除该后端的失败计数与短路状态。"""
        with self._lock:
            self._failures.pop(name, None)
            self._tripped_until.pop(name, None)

    def record_failure(self, name: str) -> None:
        """后端调用失败，累计失败计数并可能触发短路。"""
        with self._lock:
            count = self._failures.get(name, 0) + 1
            if count >= self.fail_threshold:
                self._tripped_until[name] = time.monotonic() + self.cooldown_seconds
                self._failures[name] = 0
            else:
                self._failures[name] = count

    def is_tripped(self, name: str) -> bool:
        """后端是否处于短路冷却期；冷却结束自动复位。"""
        with self._lock:
            until = self._tripped_until.get(name)
            if until is None:
                return False
            if time.monotonic() >= until:
                self._tripped_until.pop(name, None)
                self._failures.pop(name, None)
                return False
            return True

    def failure_counts(self) -> Mapping[str, int]:
        with self._lock:
            return dict(self._failures)

    def reset(self) -> None:
        """清空所有后端状态（进程内共享实例调试/测试用）。"""
        with self._lock:
            self._failures.clear()
            self._tripped_until.clear()
