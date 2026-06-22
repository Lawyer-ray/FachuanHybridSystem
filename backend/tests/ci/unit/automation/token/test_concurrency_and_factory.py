"""并发优化器和浏览器上下文工厂测试。"""

from __future__ import annotations

import pytest

try:
    from plugins import has_court_login_plugin
    _HAS_LOGIN = has_court_login_plugin()
except ImportError:
    _HAS_LOGIN = False

if _HAS_LOGIN:
    from plugins.court_automation.token.concurrency_optimizer import (
        ConcurrencyConfig,
        ResourceUsage,
    )
    from plugins.court_automation.token.browser_context_factory import (
        DefaultAntiDetectionOptionsProvider,
        PlaywrightBrowserContextFactory,
    )
else:
    ConcurrencyConfig = None  # type: ignore[assignment,misc]
    ResourceUsage = None  # type: ignore[assignment,misc]
    DefaultAntiDetectionOptionsProvider = None  # type: ignore[assignment,misc]
    PlaywrightBrowserContextFactory = None  # type: ignore[assignment,misc]

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")


class TestConcurrencyConfig:
    """ConcurrencyConfig 数据类测试。"""

    def test_default_values(self) -> None:
        config = ConcurrencyConfig()
        assert config.max_concurrent_acquisitions == 3
        assert config.max_concurrent_per_site == 2
        assert config.max_concurrent_per_account == 1
        assert config.acquisition_timeout == 300.0
        assert config.lock_timeout == 30.0
        assert config.queue_timeout == 60.0
        assert config.resource_check_interval == 1.0

    def test_custom_values(self) -> None:
        config = ConcurrencyConfig(max_concurrent_acquisitions=5, acquisition_timeout=600.0)
        assert config.max_concurrent_acquisitions == 5
        assert config.acquisition_timeout == 600.0


class TestResourceUsage:
    """ResourceUsage 数据类测试。"""

    def test_default_values(self) -> None:
        usage = ResourceUsage()
        assert usage.total_acquisitions == 0
        assert usage.site_acquisitions == {}
        assert usage.account_acquisitions == {}
        assert usage.active_locks == set()

    def test_custom_values(self) -> None:
        usage = ResourceUsage(
            total_acquisitions=5,
            site_acquisitions={"site1": 2},
            account_acquisitions={"acc1": 1},
            active_locks={"lock1"},
        )
        assert usage.total_acquisitions == 5
        assert usage.site_acquisitions["site1"] == 2


class TestBrowserContextFactory:
    """BrowserContextFactory 测试。"""

    def test_playwright_factory_creation(self) -> None:
        """创建 PlaywrightBrowserContextFactory。"""
        browser_service = object.__new__(type("BS", (), {}))
        provider = DefaultAntiDetectionOptionsProvider()
        factory = PlaywrightBrowserContextFactory(
            browser_service=browser_service,
            anti_detection_options_provider=provider,
        )
        assert factory.browser_service is browser_service
        assert factory.anti_detection_options_provider is provider
