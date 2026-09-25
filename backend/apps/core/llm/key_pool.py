"""单平台多 Key 槽位管理。

服务路径（``OpenAICompatibleBackend``）与 Agent 路径（pydantic-ai）共用本模块，
使「每 Key 并发上限」的语义在两条路径上保持一致，避免各自实现一套轮询规则。
"""

from __future__ import annotations

import threading
import time


class KeyPool:
    """单平台多 Key 槽位管理：按模型过滤候选、轮询分配、每 Key 并发上限、失败冷却。

    - 并发上限为 0 表示不限制；
    - 全部候选 Key 处于并发上限时超限使用（保证请求可用）；
    - 失败后的 ``(Key, 模型)`` 组合进入 30 秒冷却。冷却**按组合而非按 Key** 记账，
      避免某模型的无权限 403 误伤同一 Key 对其他模型的正常请求；
    - ``scopes`` 为 ``{key: [model, ...]}``，未出现的 Key 表示不限模型。

    线程安全：``acquire`` / ``release`` 由内部锁保护，可在多线程与多事件循环下共用。
    """

    COOLDOWN_SECONDS = 30.0

    def __init__(
        self,
        keys: list[str],
        concurrency_per_key: int = 0,
        scopes: dict[str, list[str]] | None = None,
    ) -> None:
        self.keys = list(keys)
        self.limit = max(0, int(concurrency_per_key or 0))
        self.scopes: dict[str, list[str]] = {key: list(models) for key, models in (scopes or {}).items()}
        self._active = [0] * len(self.keys)
        self._failed_until: dict[tuple[int, str], float] = {}
        self._cursor = 0
        self._lock = threading.Lock()

    def _eligible(self, model: str) -> list[int]:
        """返回可用于该模型的 Key 下标（未声明白名单的 Key 视为不限模型）。"""
        used = (model or "").strip()
        if not used:
            return list(range(len(self.keys)))
        return [i for i, key in enumerate(self.keys) if not self.scopes.get(key) or used in self.scopes[key]]

    def has_key_for(self, model: str = "") -> bool:
        """是否存在可用于该模型的 Key（不校验并发与冷却状态）。"""
        return bool(self._eligible(model))

    def acquire(self, model: str = "") -> int | None:
        """在可用于该模型的 Key 中选中一个下标并占用；无候选或全部冷却时返回 None。"""
        used = (model or "").strip()
        with self._lock:
            candidates = self._eligible(used)
            total = len(candidates)
            if total == 0:
                return None
            now = time.monotonic()
            for _ in range(total):
                idx = candidates[self._cursor % total]
                self._cursor += 1
                if self._failed_until.get((idx, used), 0.0) > now:
                    continue
                if self.limit and self._active[idx] >= self.limit:
                    continue
                self._active[idx] += 1
                return idx
            # 全部处于并发上限：超限使用下一个未冷却的 Key，保证请求可用
            for _ in range(total):
                idx = candidates[self._cursor % total]
                self._cursor += 1
                if self._failed_until.get((idx, used), 0.0) <= now:
                    self._active[idx] += 1
                    return idx
            return None

    def release(self, idx: int, *, success: bool, model: str = "") -> None:
        with self._lock:
            if 0 <= idx < len(self._active):
                self._active[idx] = max(0, self._active[idx] - 1)
                if not success:
                    self._failed_until[(idx, (model or "").strip())] = time.monotonic() + self.COOLDOWN_SECONDS

    def is_cooling(self, idx: int, model: str = "") -> bool:
        """该 ``(Key, 模型)`` 组合是否处于失败冷却中。"""
        with self._lock:
            return self._failed_until.get((idx, (model or "").strip()), 0.0) > time.monotonic()

    @property
    def active_counts(self) -> list[int]:
        """各 Key 当前占用的槽位数（只读快照，供日志与监控观察池饱和度）。"""
        with self._lock:
            return list(self._active)
