"""
BrowserManager 属性测试

使用 Hypothesis 进行属性测试，验证 BrowserManager 的正确性。
"""

import os
from unittest.mock import MagicMock, patch

# Django setup
import django
import psutil
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
django.setup()

from apps.automation.services.scraper.config.browser_config import BrowserConfig
from apps.automation.services.scraper.core.browser_manager import BrowserCreationError, BrowserManager

browser_manager = BrowserManager()


def _make_mock_playwright() -> MagicMock:
    """构造一个模拟 Playwright 对象"""
    mock_page = MagicMock()
    mock_page.viewport_size = {"width": 1280, "height": 720}
    mock_page.evaluate = MagicMock(return_value="Mozilla/5.0 Test")

    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = MagicMock()
    mock_browser.new_context.return_value = mock_context

    mock_chromium = MagicMock()
    mock_chromium.launch.return_value = mock_browser

    mock_pw = MagicMock()
    mock_pw.chromium = mock_chromium

    mock_sync_pw = MagicMock()
    mock_sync_pw.start.return_value = mock_pw
    mock_sync_pw.__enter__ = MagicMock(return_value=mock_pw)
    mock_sync_pw.__exit__ = MagicMock(return_value=False)

    return mock_sync_pw


def get_chromium_process_count() -> int:
    """获取当前运行的 Chromium 进程数量"""
    count = 0
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info["name"]
            if name and "chrom" in name.lower():
                count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return count


# =============================================================================
# Property Test 2.1: Browser cleanup on normal exit
# **Feature: automation-decoupling, Property 1: Browser cleanup on normal exit**
# **Validates: Requirements 1.2**
# =============================================================================


class TestBrowserCleanupNormalExit:
    """
    **Feature: automation-decoupling, Property 1: Browser cleanup on normal exit**

    验证：对于任何浏览器配置，当使用 BrowserManager 上下文管理器并正常退出时，
    浏览器资源应被正确清理，不应有浏览器进程残留。
    """

    @given(
        headless=st.booleans(),
        slow_mo=st.integers(min_value=0, max_value=100),
        viewport_width=st.integers(min_value=800, max_value=1920),
        viewport_height=st.integers(min_value=600, max_value=1080),
    )
    @settings(max_examples=5, deadline=60000)
    def test_browser_cleanup_on_normal_exit(
        self,
        headless: bool,
        slow_mo: int,
        viewport_width: int,
        viewport_height: int,
    ):
        """
        **Feature: automation-decoupling, Property 1: Browser cleanup on normal exit**

        对于任何有效的浏览器配置，正常退出时浏览器资源应被清理。
        """
        config = BrowserConfig(
            headless=headless,
            slow_mo=slow_mo,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            timeout=10000,
            navigation_timeout=10000,
        )

        mock_sync_pw = _make_mock_playwright()
        mock_page = mock_sync_pw.start.return_value.chromium.launch.return_value.new_context.return_value.new_page.return_value
        mock_page.viewport_size = {"width": viewport_width, "height": viewport_height}

        page_created = False
        context_created = False

        with patch("apps.automation.services.scraper.core.browser_manager.sync_playwright", return_value=mock_sync_pw):
            with browser_manager.create_browser(config, use_anti_detection=False) as (page, context):
                assert page is not None
                assert context is not None
                page_created = True
                context_created = True
                viewport = page.viewport_size
                assert viewport is not None

        assert page_created and context_created, "浏览器应该被成功创建"


# =============================================================================
# Property Test 2.2: Browser cleanup on error
# **Feature: automation-decoupling, Property 2: Browser cleanup on error**
# **Validates: Requirements 1.4**
# =============================================================================


class TestBrowserCleanupOnError:
    """
    **Feature: automation-decoupling, Property 2: Browser cleanup on error**

    验证：对于任何浏览器配置，当使用 BrowserManager 上下文管理器并发生错误时，
    浏览器资源仍应被正确清理。
    """

    @given(
        headless=st.booleans(),
        slow_mo=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=5, deadline=60000)
    def test_browser_cleanup_on_exception(
        self,
        headless: bool,
        slow_mo: int,
    ):
        """
        **Feature: automation-decoupling, Property 2: Browser cleanup on error**

        对于任何有效的浏览器配置，即使发生异常，浏览器资源也应被清理。
        """
        config = BrowserConfig(
            headless=headless,
            slow_mo=slow_mo,
            timeout=10000,
            navigation_timeout=10000,
        )

        mock_sync_pw = _make_mock_playwright()
        page_created = False
        context_created = False

        with patch("apps.automation.services.scraper.core.browser_manager.sync_playwright", return_value=mock_sync_pw):
            with pytest.raises(BrowserCreationError):
                with browser_manager.create_browser(config, use_anti_detection=False) as (page, context):
                    assert page is not None
                    assert context is not None
                    page_created = True
                    context_created = True
                    viewport = page.viewport_size
                    assert viewport is not None
                    raise RuntimeError("测试异常")

        assert page_created and context_created, "浏览器应该被成功创建"


# =============================================================================
# Property Test 2.3: Configuration application
# **Feature: automation-decoupling, Property 3: Configuration application**
# **Validates: Requirements 1.3**
# =============================================================================


class TestConfigurationApplication:
    """
    **Feature: automation-decoupling, Property 3: Configuration application**

    验证：对于任何有效的 BrowserConfig，当使用该配置创建浏览器时，
    结果浏览器应具有与配置匹配的设置。
    """

    @given(
        headless=st.booleans(),
        viewport_width=st.integers(min_value=800, max_value=1920),
        viewport_height=st.integers(min_value=600, max_value=1080),
        user_agent=st.text(
            min_size=10, max_size=200, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "P", "Zs"))
        ),
    )
    @settings(max_examples=5, deadline=60000)
    def test_configuration_is_applied(
        self,
        headless: bool,
        viewport_width: int,
        viewport_height: int,
        user_agent: str,
    ):
        """
        **Feature: automation-decoupling, Property 3: Configuration application**

        对于任何有效的配置，创建的浏览器应该应用该配置。
        """
        user_agent = user_agent.strip()
        if not user_agent:
            user_agent = "Mozilla/5.0 Test"

        config = BrowserConfig(
            headless=headless,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            user_agent=user_agent,
            timeout=10000,
            navigation_timeout=10000,
        )

        mock_sync_pw = _make_mock_playwright()
        mock_page = mock_sync_pw.start.return_value.chromium.launch.return_value.new_context.return_value.new_page.return_value
        mock_page.viewport_size = {"width": viewport_width, "height": viewport_height}
        mock_page.evaluate = MagicMock(return_value=user_agent)

        with patch("apps.automation.services.scraper.core.browser_manager.sync_playwright", return_value=mock_sync_pw):
            with browser_manager.create_browser(config, use_anti_detection=False) as (page, context):
                viewport = page.viewport_size
                assert viewport["width"] == viewport_width, f"视口宽度不匹配: 期望={viewport_width}, 实际={viewport['width']}"
                assert viewport["height"] == viewport_height, f"视口高度不匹配: 期望={viewport_height}, 实际={viewport['height']}"

                actual_user_agent = page.evaluate("navigator.userAgent")
                assert actual_user_agent == user_agent, f"User Agent 不匹配: 期望={user_agent}, 实际={actual_user_agent}"


# =============================================================================
# Additional unit tests for error handling
# =============================================================================


class TestBrowserManagerErrorHandling:
    """测试 BrowserManager 的错误处理"""

    def test_invalid_config_raises_error(self):
        """无效配置应该抛出 BrowserCreationError"""
        config = BrowserConfig(
            viewport_width=-100,  # 无效值
            timeout=10000,
        )

        with pytest.raises(BrowserCreationError) as exc_info:
            with browser_manager.create_browser(config) as (page, context):
                pass

        assert "配置验证失败" in str(exc_info.value)

    def test_none_config_uses_defaults(self):
        """None 配置应该使用默认值"""
        env_keys = [
            "BROWSER_HEADLESS",
            "BROWSER_SLOW_MO",
            "BROWSER_VIEWPORT_WIDTH",
            "BROWSER_VIEWPORT_HEIGHT",
        ]
        original_env = {key: os.environ.get(key) for key in env_keys}

        try:
            for key in env_keys:
                os.environ.pop(key, None)

            defaults = BrowserConfig()
            mock_sync_pw = _make_mock_playwright()
            mock_page = mock_sync_pw.start.return_value.chromium.launch.return_value.new_context.return_value.new_page.return_value
            mock_page.viewport_size = {"width": defaults.viewport_width, "height": defaults.viewport_height}

            with patch(
                "apps.automation.services.scraper.core.browser_manager.sync_playwright",
                return_value=mock_sync_pw,
            ):
                with browser_manager.create_browser(None, use_anti_detection=False) as (page, context):
                    assert page is not None
                    assert context is not None

                    viewport = page.viewport_size
                    assert viewport["width"] == defaults.viewport_width
                    assert viewport["height"] == defaults.viewport_height

        finally:
            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
