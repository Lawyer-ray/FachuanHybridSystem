"""ConcurrencyOptimizer 全覆盖测试。"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from apps.automation.services.token.concurrency_optimizer import (
    ConcurrencyConfig,
    ConcurrencyOptimizer,
    ResourceUsage,
)


class TestConcurrencyConfig:
    """ConcurrencyConfig 数据类测试。"""

    def test_defaults(self) -> None:
        cfg = ConcurrencyConfig()
        assert cfg.max_concurrent_acquisitions == 3
        assert cfg.max_concurrent_per_site == 2
        assert cfg.max_concurrent_per_account == 1
        assert cfg.acquisition_timeout == 300.0
        assert cfg.lock_timeout == 30.0
        assert cfg.queue_timeout == 60.0


class TestResourceUsage:
    """ResourceUsage 数据类测试。"""

    def test_defaults(self) -> None:
        ru = ResourceUsage()
        assert ru.total_acquisitions == 0
        assert ru.site_acquisitions == {}
        assert ru.account_acquisitions == {}
        assert ru.active_locks == set()


class TestConcurrencyOptimizer:
    """ConcurrencyOptimizer 测试。"""

    def _make_optimizer(self, config: ConcurrencyConfig | None = None) -> ConcurrencyOptimizer:
        opt = ConcurrencyOptimizer.__new__(ConcurrencyOptimizer)
        opt.config = config or ConcurrencyConfig()
        opt._locks = {}
        opt._lock_creation_lock = asyncio.Lock()
        opt._resource_usage = ResourceUsage()
        opt._wait_queue: deque = __import__("collections").deque()
        return opt

    # ─── _check_concurrency_limits ───

    def test_check_limits_within(self) -> None:
        opt = self._make_optimizer()
        assert opt._check_concurrency_limits("site1", "acct1") is True

    def test_check_limits_total_exceeded(self) -> None:
        opt = self._make_optimizer()
        opt._resource_usage.total_acquisitions = 3
        assert opt._check_concurrency_limits("site1", "acct1") is False

    def test_check_limits_site_exceeded(self) -> None:
        opt = self._make_optimizer()
        opt._resource_usage.site_acquisitions = {"site1": 2}
        assert opt._check_concurrency_limits("site1", "acct1") is False

    def test_check_limits_account_exceeded(self) -> None:
        opt = self._make_optimizer()
        opt._resource_usage.account_acquisitions = {"acct1": 1}
        assert opt._check_concurrency_limits("site1", "acct1") is False

    # ─── _update_resource_usage ───

    def test_update_resource_usage_increment(self) -> None:
        opt = self._make_optimizer()
        opt._update_resource_usage("site1", "acct1", increment=True)
        assert opt._resource_usage.total_acquisitions == 1
        assert opt._resource_usage.site_acquisitions["site1"] == 1
        assert opt._resource_usage.account_acquisitions["acct1"] == 1

    def test_update_resource_usage_decrement(self) -> None:
        opt = self._make_optimizer()
        opt._resource_usage.total_acquisitions = 2
        opt._resource_usage.site_acquisitions = {"site1": 2}
        opt._resource_usage.account_acquisitions = {"acct1": 2}
        opt._update_resource_usage("site1", "acct1", increment=False)
        assert opt._resource_usage.total_acquisitions == 1
        assert opt._resource_usage.site_acquisitions["site1"] == 1
        assert opt._resource_usage.account_acquisitions["acct1"] == 1

    def test_update_resource_usage_decrement_to_zero(self) -> None:
        opt = self._make_optimizer()
        opt._resource_usage.total_acquisitions = 1
        opt._resource_usage.site_acquisitions = {"site1": 1}
        opt._resource_usage.account_acquisitions = {"acct1": 1}
        opt._update_resource_usage("site1", "acct1", increment=False)
        assert opt._resource_usage.total_acquisitions == 0
        assert "site1" not in opt._resource_usage.site_acquisitions
        assert "acct1" not in opt._resource_usage.account_acquisitions

    def test_update_resource_usage_floor_at_zero(self) -> None:
        opt = self._make_optimizer()
        opt._resource_usage.total_acquisitions = 0
        opt._update_resource_usage("site1", "acct1", increment=False)
        assert opt._resource_usage.total_acquisitions == 0

    # ─── _get_lock ───

    @pytest.mark.asyncio
    async def test_get_lock_creates_new(self) -> None:
        opt = self._make_optimizer()
        lock = await opt._get_lock("site:acct")
        assert isinstance(lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_get_lock_returns_existing(self) -> None:
        opt = self._make_optimizer()
        lock1 = await opt._get_lock("site:acct")
        lock2 = await opt._get_lock("site:acct")
        assert lock1 is lock2

    # ─── get_resource_usage ───

    @pytest.mark.asyncio
    async def test_get_resource_usage(self) -> None:
        opt = self._make_optimizer()
        opt._resource_usage.total_acquisitions = 5
        opt._resource_usage.site_acquisitions = {"s1": 3}
        usage = await opt.get_resource_usage()
        assert usage["total_acquisitions"] == 5
        assert usage["site_acquisitions"] == {"s1": 3}

    # ─── optimize_concurrency ───

    @pytest.mark.asyncio
    async def test_optimize_concurrency_no_issues(self) -> None:
        opt = self._make_optimizer()
        result = await opt.optimize_concurrency()
        assert result["optimization_applied"] is False
        assert result["recommendations"] == []

    @pytest.mark.asyncio
    async def test_optimize_concurrency_high_total(self) -> None:
        cfg = ConcurrencyConfig(max_concurrent_acquisitions=5)
        opt = self._make_optimizer(cfg)
        opt._resource_usage.total_acquisitions = 4  # 80%
        result = await opt.optimize_concurrency()
        assert any(r["type"] == "increase_max_concurrent" for r in result["recommendations"])

    @pytest.mark.asyncio
    async def test_optimize_concurrency_site_bottleneck(self) -> None:
        cfg = ConcurrencyConfig(max_concurrent_per_site=2)
        opt = self._make_optimizer(cfg)
        opt._resource_usage.site_acquisitions = {"site1": 2}
        result = await opt.optimize_concurrency()
        assert any(r["type"] == "site_bottleneck" for r in result["recommendations"])

    @pytest.mark.asyncio
    async def test_optimize_concurrency_queue_backlog(self) -> None:
        opt = self._make_optimizer()
        for i in range(6):
            opt._wait_queue.append(MagicMock())
        result = await opt.optimize_concurrency()
        assert any(r["type"] == "queue_backlog" for r in result["recommendations"])

    # ─── cleanup_resources ───

    @pytest.mark.asyncio
    async def test_cleanup_resources(self) -> None:
        opt = self._make_optimizer()
        opt._resource_usage.total_acquisitions = 5
        opt._wait_queue.append(MagicMock())
        opt._locks = {"k1": asyncio.Lock(), "k2": asyncio.Lock()}
        await opt.cleanup_resources()
        assert opt._resource_usage.total_acquisitions == 0
        assert len(opt._wait_queue) == 0

    # ─── _cleanup_expired_locks ───

    @pytest.mark.asyncio
    async def test_cleanup_expired_locks(self) -> None:
        opt = self._make_optimizer()
        lock = asyncio.Lock()
        opt._locks = {"key1": lock}
        await opt._cleanup_expired_locks()
        assert "key1" not in opt._locks

    # ─── acquire_resource + release_resource ───

    @pytest.mark.asyncio
    async def test_acquire_and_release_resource(self) -> None:
        opt = self._make_optimizer(ConcurrencyConfig(lock_timeout=5.0))
        result = await opt.acquire_resource("id1", "site1", "acct1")
        assert result is True
        assert opt._resource_usage.total_acquisitions == 1

        await opt.release_resource("id1", "site1", "acct1")
        assert opt._resource_usage.total_acquisitions == 0

    @pytest.mark.asyncio
    async def test_acquire_resource_queue_wait(self) -> None:
        """When at capacity, request queues and waits."""
        cfg = ConcurrencyConfig(max_concurrent_acquisitions=1, queue_timeout=2.0, lock_timeout=5.0)
        opt = self._make_optimizer(cfg)
        opt._resource_usage.total_acquisitions = 1  # at capacity

        async def release_after_delay() -> None:
            await asyncio.sleep(0.1)
            opt._resource_usage.total_acquisitions = 0
            opt._wake_next_eligible()

        # Run release in background
        asyncio.create_task(release_after_delay())

        result = await opt.acquire_resource("id2", "site1", "acct2")
        assert result is True

    # ─── _wake_next_eligible ───

    def test_wake_next_eligible_empty_queue(self) -> None:
        opt = self._make_optimizer()
        opt._wake_next_eligible()  # No error

    def test_wake_next_eligible_cleans_expired(self) -> None:
        import time
        opt = self._make_optimizer()
        entry = MagicMock()
        entry.enqueued_at = time.time() - 9999  # expired
        entry.site_name = "s"
        entry.account = "a"
        opt._wait_queue.append(entry)
        opt._wake_next_eligible()
        assert len(opt._wait_queue) == 0
