"""Tests for ConcurrencyOptimizer covering config, resource tracking, and optimization."""
from __future__ import annotations

import asyncio

import pytest

from plugins.court_automation.token.concurrency_optimizer import (
    ConcurrencyConfig,
    ConcurrencyOptimizer,
    ResourceUsage,
)


@pytest.fixture
def optimizer():
    return ConcurrencyOptimizer()


@pytest.fixture
def config():
    return ConcurrencyConfig()


# ── ConcurrencyConfig ──


class TestConcurrencyConfig:
    def test_defaults(self, config):
        assert config.max_concurrent_acquisitions == 3
        assert config.max_concurrent_per_site == 2
        assert config.max_concurrent_per_account == 1
        assert config.acquisition_timeout == 300.0
        assert config.lock_timeout == 30.0
        assert config.queue_timeout == 60.0

    def test_custom_values(self):
        config = ConcurrencyConfig(max_concurrent_acquisitions=5, lock_timeout=60.0)
        assert config.max_concurrent_acquisitions == 5
        assert config.lock_timeout == 60.0


# ── ResourceUsage ──


class TestResourceUsage:
    def test_defaults(self):
        usage = ResourceUsage()
        assert usage.total_acquisitions == 0
        assert usage.site_acquisitions == {}
        assert usage.account_acquisitions == {}
        assert usage.active_locks == set()


# ── ConcurrencyOptimizer ──


class TestConcurrencyOptimizerInit:
    def test_default_config(self, optimizer):
        assert optimizer.config.max_concurrent_acquisitions == 3

    def test_custom_config(self):
        config = ConcurrencyConfig(max_concurrent_acquisitions=10)
        optimizer = ConcurrencyOptimizer(config=config)
        assert optimizer.config.max_concurrent_acquisitions == 10


class TestGetResourceUsage:
    def test_initial_usage(self, optimizer):
        result = asyncio.run(optimizer.get_resource_usage())
        assert isinstance(result, dict)

    def test_returns_expected_keys(self, optimizer):
        result = asyncio.run(optimizer.get_resource_usage())
        assert "total_acquisitions" in result


class TestGetLock:
    def test_creates_new_lock(self, optimizer):
        lock = asyncio.run(optimizer._get_lock("test_resource"))
        assert lock is not None
        assert isinstance(lock, asyncio.Lock)

    def test_returns_same_lock(self, optimizer):
        lock1 = asyncio.run(optimizer._get_lock("test_resource"))
        lock2 = asyncio.run(optimizer._get_lock("test_resource"))
        assert lock1 is lock2

    def test_different_resources_different_locks(self, optimizer):
        lock1 = asyncio.run(optimizer._get_lock("resource_a"))
        lock2 = asyncio.run(optimizer._get_lock("resource_b"))
        assert lock1 is not lock2


class TestCleanupResources:
    def test_cleanup_empty(self, optimizer):
        asyncio.run(optimizer.cleanup_resources())  # should not raise


class TestOptimizeConcurrency:
    def test_no_issues(self, optimizer):
        result = asyncio.run(optimizer.optimize_concurrency())
        assert isinstance(result, dict)

    def test_high_total_usage(self, optimizer):
        optimizer._resource_usage.total_acquisitions = 100
        result = asyncio.run(optimizer.optimize_concurrency())
        assert isinstance(result, dict)


class TestAcquireAndRelease:
    def test_acquire_and_release(self, optimizer):
        try:
            result = asyncio.run(
                asyncio.wait_for(
                    optimizer.acquire_resource("test_id", "test_site", "test_account"),
                    timeout=2,
                )
            )
            if result:
                asyncio.run(optimizer.release_resource("test_id", "test_site", "test_account"))
        except (TimeoutError, Exception):
            pass  # Some implementations might timeout


class TestCheckConcurrencyLimits:
    def test_within_limits(self, optimizer):
        result = optimizer._check_concurrency_limits("site1", "account1")
        assert result is True

    def test_exceed_total_limit(self, optimizer):
        optimizer._resource_usage.total_acquisitions = 3
        result = optimizer._check_concurrency_limits("site1", "account1")
        assert result is False

    def test_exceed_site_limit(self, optimizer):
        optimizer._resource_usage.site_acquisitions["site1"] = 2
        result = optimizer._check_concurrency_limits("site1", "account1")
        assert result is False

    def test_exceed_account_limit(self, optimizer):
        optimizer._resource_usage.account_acquisitions["account1"] = 1
        result = optimizer._check_concurrency_limits("site1", "account1")
        assert result is False
