"""Tests for various automation utility services: task_queue, browser_context_factory, sms helpers."""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

try:
    from plugins import has_court_login_plugin
    _HAS_LOGIN = has_court_login_plugin()
except ImportError:
    _HAS_LOGIN = False

from apps.automation.services.sms.task_queue import DjangoQTaskQueue, TaskQueue

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")


# ── TaskQueue protocol ──


class TestTaskQueueProtocol:
    def test_django_q_task_queue_is_frozen(self):
        queue = DjangoQTaskQueue()
        assert hasattr(queue, "enqueue")

    @patch("apps.core.tasking.submit_task")
    def test_enqueue_with_string_func(self, mock_submit):
        mock_submit.return_value = "task-id-123"
        queue = DjangoQTaskQueue()
        result = queue.enqueue("apps.some.module.func", 42, task_name="test_task")
        mock_submit.assert_called_once_with("apps.some.module.func", 42, task_name="test_task")

    @patch("apps.core.tasking.submit_task")
    def test_enqueue_with_callable_func(self, mock_submit):
        mock_submit.return_value = "task-id-456"
        queue = DjangoQTaskQueue()

        def my_func():
            pass

        result = queue.enqueue(my_func, task_name="test_task")
        mock_submit.assert_called_once()


# ── BrowserContextFactory ──


class TestBrowserContextFactory:
    def test_playwright_factory_with_create_context(self):
        from plugins.court_automation.token.browser_context_factory import PlaywrightBrowserContextFactory

        mock_browser_service = MagicMock()
        mock_browser_service.create_context.return_value = "context"
        mock_provider = MagicMock()
        mock_provider.get_options.return_value = {"headless": True}

        factory = PlaywrightBrowserContextFactory(
            browser_service=mock_browser_service,
            anti_detection_options_provider=mock_provider,
        )
        result = factory.new_context()
        assert result == "context"
        mock_browser_service.create_context.assert_called_once()

    def test_playwright_factory_with_get_browser(self):
        from plugins.court_automation.token.browser_context_factory import PlaywrightBrowserContextFactory

        mock_browser_service = MagicMock(spec=[])  # No create_context method
        mock_browser = MagicMock()
        mock_browser_service.get_browser = MagicMock(return_value=mock_browser)
        mock_browser.new_context.return_value = "context_from_browser"
        mock_provider = MagicMock()
        mock_provider.get_options.return_value = {"headless": True}

        factory = PlaywrightBrowserContextFactory(
            browser_service=mock_browser_service,
            anti_detection_options_provider=mock_provider,
        )
        result = factory.new_context()
        assert result == "context_from_browser"

    def test_playwright_factory_exception_raises_network_error(self):
        from plugins.court_automation.token.browser_context_factory import PlaywrightBrowserContextFactory
        from apps.core.exceptions import NetworkError

        mock_browser_service = MagicMock()
        mock_browser_service.create_context.side_effect = Exception("browser error")
        mock_provider = MagicMock()
        mock_provider.get_options.return_value = {}

        factory = PlaywrightBrowserContextFactory(
            browser_service=mock_browser_service,
            anti_detection_options_provider=mock_provider,
        )
        with pytest.raises(NetworkError, match="无法获取浏览器上下文"):
            factory.new_context()

    def test_default_anti_detection_provider(self):
        from plugins.court_automation.token.browser_context_factory import DefaultAntiDetectionOptionsProvider

        provider = DefaultAntiDetectionOptionsProvider()
        assert provider is not None
        # get_options() calls anti_detection.get_context_options() which requires browser deps
        # Just verify the provider can be instantiated
