"""Additional coverage tests for concurrency_optimizer.py — queue timeout, edge cases."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from unittest.mock import MagicMock

import pytest

from apps.core.exceptions import TokenAcquisitionTimeoutError
from apps.automation.services.token.concurrency_optimizer import (
    ConcurrencyConfig,
    ConcurrencyOptimizer,
    ResourceUsage,
    _WaitEntry,
)


class TestConcurrencyOptimizerQueue:
    def _make(self, **kwargs) -> ConcurrencyOptimizer:
        config = ConcurrencyConfig(**kwargs)
        opt = ConcurrencyOptimizer.__new__(ConcurrencyOptimizer)
        opt.config = config
        opt._locks = {}
        opt._lock_creation_lock = asyncio.Lock()
        opt._resource_usage = ResourceUsage()
        opt._wait_queue = deque()
        return opt

    @pytest.mark.asyncio
    async def test_queue_timeout_raises(self) -> None:
        """When queue_timeout is very short, waiting should raise TokenAcquisitionTimeoutError."""
        opt = self._make(max_concurrent_acquisitions=1, queue_timeout=0.1, lock_timeout=5.0)
        opt._resource_usage.total_acquisitions = 1

        with pytest.raises(TokenAcquisitionTimeoutError):
            await opt.acquire_resource("id1", "site1", "acct1")

    @pytest.mark.asyncio
    async def test_acquire_lock_timeout(self) -> None:
        """When lock cannot be acquired in time, should raise TokenAcquisitionTimeoutError."""
        opt = self._make(max_concurrent_acquisitions=5, lock_timeout=0.01, queue_timeout=5.0)

        # Pre-acquire the lock to cause a timeout
        lock = await opt._get_lock("site1:acct1")
        await lock.acquire()

        with pytest.raises(TokenAcquisitionTimeoutError, match="获取资源锁超时"):
            await opt.acquire_resource("id1", "site1", "acct1")

        lock.release()

    @pytest.mark.asyncio
    async def test_release_unlocked_lock(self) -> None:
        """Releasing when the lock is not locked should not error."""
        opt = self._make()
        # Ensure lock exists but is not locked
        lock = await opt._get_lock("site1:acct1")
        assert not lock.locked()
        # Should not raise
        await opt.release_resource("id1", "site1", "acct1")

    @pytest.mark.asyncio
    async def test_release_logs_error(self) -> None:
        """release_resource should handle errors gracefully."""
        opt = self._make()
        with patch("apps.automation.services.token.concurrency_optimizer.logger"):
            # Force an error in _get_lock by mocking
            with patch.object(opt, "_get_lock", side_effect=RuntimeError("lock error")):
                # Should not raise
                await opt.release_resource("id1", "site1", "acct1")

    def test_wake_next_eligible_wakes_eligible(self) -> None:
        """_wake_next_eligible should wake the first eligible entry."""
        opt = self._make(max_concurrent_acquisitions=2)
        entry = MagicMock(spec=_WaitEntry)
        entry.enqueued_at = time.time()
        entry.site_name = "s1"
        entry.account = "a1"
        entry.event = MagicMock()
        opt._wait_queue.append(entry)

        opt._wake_next_eligible()
        entry.event.set.assert_called_once()

    def test_wake_next_eligible_preserves_ineligible(self) -> None:
        """Entries that don't fit concurrency limits stay in queue."""
        opt = self._make(max_concurrent_acquisitions=1)
        opt._resource_usage.total_acquisitions = 1

        entry = MagicMock(spec=_WaitEntry)
        entry.enqueued_at = time.time()
        entry.site_name = "s1"
        entry.account = "a1"
        entry.event = MagicMock()
        opt._wait_queue.append(entry)

        opt._wake_next_eligible()
        entry.event.set.assert_not_called()
        assert len(opt._wait_queue) == 1

    @pytest.mark.asyncio
    async def test_cleanup_expired_locks_removes_unlocked(self) -> None:
        opt = self._make()
        lock1 = asyncio.Lock()
        lock2 = asyncio.Lock()
        await lock1.acquire()  # locked
        opt._locks = {"k1": lock1, "k2": lock2}  # k2 not locked

        await opt._cleanup_expired_locks()
        assert "k1" in opt._locks  # still locked
        assert "k2" not in opt._locks  # removed


from unittest.mock import patch
