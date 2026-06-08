"""apps/core/services/browser/cdp_connector.py 单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.core.services.browser.profiles import BrowserProfile


def _make_profile(**overrides: object) -> BrowserProfile:
    """创建测试用 BrowserProfile 实例。"""
    defaults: dict[str, object] = {
        "name": "test",
        "headless": True,
        "anti_detection": False,
        "proxy": None,
        "user_data_dir": None,
        "timeout": 30000,
        "navigation_timeout": 60000,
    }
    defaults.update(overrides)
    return BrowserProfile(**defaults)  # type: ignore[arg-type]


class TestConnectCdpBrowser:
    """测试 connect_cdp_browser 异步上下文管理器。"""

    @pytest.mark.asyncio
    async def test_yields_browser_and_context(self) -> None:
        """正常启动时应 yield (browser, context)。"""
        from apps.core.services.browser.cdp_connector import connect_cdp_browser

        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_context.set_default_timeout = MagicMock()
        mock_context.set_default_navigation_timeout = MagicMock()

        profile = _make_profile()

        # ensure_binary, launch_async 都是通过 from cloakbrowser import 的
        mock_cb = MagicMock()
        mock_cb.ensure_binary = MagicMock()
        mock_cb.launch_async = AsyncMock(return_value=mock_browser)

        mock_ad = MagicMock()
        mock_ad.get_context_options = MagicMock(return_value={})

        with (
            patch.dict("sys.modules", {"cloakbrowser": mock_cb}),
            patch("apps.core.services.browser.cdp_connector.anti_detection", mock_ad),
        ):
            async with connect_cdp_browser(profile) as (browser, ctx):
                assert browser is mock_browser
                assert ctx is mock_context

        mock_cb.ensure_binary.assert_called_once()
        mock_cb.launch_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_persistent_context_when_user_data_dir(self) -> None:
        """指定 user_data_dir 时应使用 launch_persistent_context_async。"""
        from apps.core.services.browser.cdp_connector import connect_cdp_browser

        mock_context = AsyncMock()
        mock_context.set_default_timeout = MagicMock()
        mock_context.set_default_navigation_timeout = MagicMock()

        profile = _make_profile(user_data_dir="/tmp/test_profile")

        mock_cb = MagicMock()
        mock_cb.ensure_binary = MagicMock()
        mock_cb.launch_persistent_context_async = AsyncMock(return_value=mock_context)

        with (
            patch.dict("sys.modules", {"cloakbrowser": mock_cb}),
            patch("apps.core.services.browser.cdp_connector.anti_detection", MagicMock()),
            patch("pathlib.Path.mkdir"),
        ):
            async with connect_cdp_browser(profile) as (browser, ctx):
                assert ctx is mock_context
                # 持久化模式下 browser == context
                assert browser is mock_context

        mock_cb.launch_persistent_context_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_sets_timeouts(self) -> None:
        """应设置 default_timeout 和 default_navigation_timeout。"""
        from apps.core.services.browser.cdp_connector import connect_cdp_browser

        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_context.set_default_timeout = MagicMock()
        mock_context.set_default_navigation_timeout = MagicMock()

        profile = _make_profile(timeout=5000, navigation_timeout=10000)

        mock_cb = MagicMock()
        mock_cb.ensure_binary = MagicMock()
        mock_cb.launch_async = AsyncMock(return_value=mock_browser)

        mock_ad = MagicMock()
        mock_ad.get_context_options = MagicMock(return_value={})

        with (
            patch.dict("sys.modules", {"cloakbrowser": mock_cb}),
            patch("apps.core.services.browser.cdp_connector.anti_detection", mock_ad),
        ):
            async with connect_cdp_browser(profile):
                mock_context.set_default_timeout.assert_called_once_with(5000)
                mock_context.set_default_navigation_timeout.assert_called_once_with(10000)

    @pytest.mark.asyncio
    async def test_closes_context_on_exit(self) -> None:
        """退出上下文时应关闭 context。"""
        from apps.core.services.browser.cdp_connector import connect_cdp_browser

        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_context.set_default_timeout = MagicMock()
        mock_context.set_default_navigation_timeout = MagicMock()

        profile = _make_profile()

        mock_cb = MagicMock()
        mock_cb.ensure_binary = MagicMock()
        mock_cb.launch_async = AsyncMock(return_value=mock_browser)

        mock_ad = MagicMock()
        mock_ad.get_context_options = MagicMock(return_value={})

        with (
            patch.dict("sys.modules", {"cloakbrowser": mock_cb}),
            patch("apps.core.services.browser.cdp_connector.anti_detection", mock_ad),
        ):
            async with connect_cdp_browser(profile):
                pass

        mock_context.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_proxy_passed_to_launch(self) -> None:
        """proxy 配置应传递给 launch_async。"""
        from apps.core.services.browser.cdp_connector import connect_cdp_browser

        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_context.set_default_timeout = MagicMock()
        mock_context.set_default_navigation_timeout = MagicMock()

        profile = _make_profile(proxy="http://proxy:8080")

        mock_cb = MagicMock()
        mock_cb.ensure_binary = MagicMock()
        mock_cb.launch_async = AsyncMock(return_value=mock_browser)

        mock_ad = MagicMock()
        mock_ad.get_context_options = MagicMock(return_value={})

        with (
            patch.dict("sys.modules", {"cloakbrowser": mock_cb}),
            patch("apps.core.services.browser.cdp_connector.anti_detection", mock_ad),
        ):
            async with connect_cdp_browser(profile):
                pass

        call_kwargs = mock_cb.launch_async.call_args.kwargs
        assert call_kwargs["proxy"] == "http://proxy:8080"


class TestConnectCdpPage:
    """测试 connect_cdp_page 异步上下文管理器。"""

    @pytest.mark.asyncio
    async def test_yields_page_and_context(self) -> None:
        """正常启动时应 yield (page, context)。"""
        from apps.core.services.browser.anti_detection import anti_detection as real_ad

        from apps.core.services.browser.cdp_connector import connect_cdp_page

        mock_page = MagicMock()
        mock_page.on = MagicMock()
        mock_context = AsyncMock()
        mock_context.pages = [mock_page]
        mock_context.set_default_timeout = MagicMock()
        mock_context.set_default_navigation_timeout = MagicMock()

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        profile = _make_profile()

        mock_cb = MagicMock()
        mock_cb.ensure_binary = MagicMock()
        mock_cb.launch_async = AsyncMock(return_value=mock_browser)

        # Patch the method on the real anti_detection instance
        with (
            patch.dict("sys.modules", {"cloakbrowser": mock_cb}),
            patch.object(real_ad, "get_context_options", return_value={}),
            patch.object(real_ad, "apply_macos_patches_async", new_callable=AsyncMock),
        ):
            async with connect_cdp_page(profile) as (page, ctx):
                assert page is mock_page
                assert ctx is mock_context

    @pytest.mark.asyncio
    async def test_creates_new_page_when_no_pages(self) -> None:
        """context.pages 为空时应调用 new_page。"""
        from apps.core.services.browser.anti_detection import anti_detection as real_ad

        from apps.core.services.browser.cdp_connector import connect_cdp_page

        mock_new_page = MagicMock()
        mock_new_page.on = MagicMock()
        mock_context = AsyncMock()
        mock_context.pages = []
        mock_context.new_page = AsyncMock(return_value=mock_new_page)
        mock_context.set_default_timeout = MagicMock()
        mock_context.set_default_navigation_timeout = MagicMock()

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        profile = _make_profile()

        mock_cb = MagicMock()
        mock_cb.ensure_binary = MagicMock()
        mock_cb.launch_async = AsyncMock(return_value=mock_browser)

        with (
            patch.dict("sys.modules", {"cloakbrowser": mock_cb}),
            patch.object(real_ad, "get_context_options", return_value={}),
            patch.object(real_ad, "apply_macos_patches_async", new_callable=AsyncMock),
        ):
            async with connect_cdp_page(profile) as (page, ctx):
                assert page is mock_new_page

        mock_context.new_page.assert_awaited_once()
