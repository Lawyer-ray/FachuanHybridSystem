"""解析凭证池：多凭证轮询分配 + 每凭证并发上限 + 失败冷却。

同一解析平台（DocumentParseProvider）在多任务间共享一个凭证池（模块级单例），
从而实现「多 Key 并发 + 自动替换（失败冷却）+ 异步并发」：
- 并发上限为 0 表示不限制；
- 全部凭证处于并发上限时超限使用（保证请求可用）；
- 失败后的凭证进入 30 秒冷却，避免反复打到失效凭证。

注：Django-Q 各 worker 进程各自独立维护一份凭证池（与旧 MinerU key 轮转一致），
进程内并发控制有效，跨进程并发由多 worker 自然放大。
"""

from __future__ import annotations

import threading
import time

_COOLDOWN_SECONDS = 30.0


class CredentialPool:
    """单个解析平台的凭证槽位管理（线程安全）。"""

    __slots__ = (
        "_active",
        "_cursor",
        "_failed_until",
        "_lock",
        "credentials",
        "limit",
    )

    def __init__(self, credentials: list[str], concurrency_per_key: int = 0) -> None:
        self.credentials = list(credentials)
        self.limit = max(0, int(concurrency_per_key or 0))
        self._active = [0] * len(self.credentials)
        self._failed_until = [0.0] * len(self.credentials)
        self._cursor = 0
        self._lock = threading.Lock()

    def acquire(self) -> int | None:
        """选中一个可用凭证下标并占用。

        Returns:
            凭证下标；无可用凭证（全部冷却）时返回 None。
        """
        with self._lock:
            n = len(self.credentials)
            if n == 0:
                return None
            now = time.monotonic()
            for _ in range(n):
                idx = self._cursor % n
                self._cursor += 1
                if self._failed_until[idx] > now:
                    continue
                if self.limit and self._active[idx] >= self.limit:
                    continue
                self._active[idx] += 1
                return idx
            # 全部处于并发上限：超限使用下一个未冷却的凭证，保证请求可用
            for _ in range(n):
                idx = self._cursor % n
                self._cursor += 1
                if self._failed_until[idx] <= now:
                    self._active[idx] += 1
                    return idx
            return None

    def release(self, idx: int, *, success: bool) -> None:
        """释放凭证槽位；失败时进入冷却。"""
        with self._lock:
            if 0 <= idx < len(self._active):
                self._active[idx] = max(0, self._active[idx] - 1)
                if not success:
                    self._failed_until[idx] = time.monotonic() + _COOLDOWN_SECONDS


_registry: dict[str, CredentialPool] = {}
_registry_lock = threading.Lock()


def get_credential_pool(
    provider_key: str,
    credentials: list[str],
    concurrency_per_key: int = 0,
) -> CredentialPool:
    """按平台标识获取进程内共享的凭证池。

    当凭证列表或并发上限发生变化时重建池（旧池由仍在执行的任务继续持有，互不影响）。

    Args:
        provider_key: 平台唯一标识（建议用 DocumentParseProvider.name）。
        credentials: 凭证明文列表。
        concurrency_per_key: 每凭证并发上限。

    Returns:
        共享的 CredentialPool 实例。
    """
    global _registry
    with _registry_lock:
        pool = _registry.get(provider_key)
        if (
            pool is not None
            and pool.credentials == list(credentials)
            and pool.limit == max(0, int(concurrency_per_key or 0))
        ):
            return pool
        pool = CredentialPool(credentials, concurrency_per_key)
        _registry[provider_key] = pool
        return pool
