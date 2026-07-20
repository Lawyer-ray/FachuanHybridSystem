"""apps/core/services/browser/cdp_connector.py 单元测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.core.services.browser.profiles import BrowserProfile

CHROME_PROCESS_MOD = "apps.core.services.browser.chrome_process"


def _make_profile(**overrides: object) -> BrowserProfile:
    """创建测试用 BrowserProfile 实例。"""
    defaults: dict[str, object] = {
        "name": "test",
        "headless": True,
        "anti_detection": False,
        "cdp_url": "http://localhost:9222",
    }
    defaults.update(overrides)
    return BrowserProfile(**defaults)  # type: ignore[arg-type]


def _mock_playwright_module() -> tuple[MagicMock, MagicMock, MagicMock]:
    """构造 async_playwright 的 mock 三件套。

    Returns:
        (mock_playwright_fn, mock_browser, mock_context)
    """
    mock_context = AsyncMock()
    mock_context.set_default_timeout = MagicMock()
    mock_context.set_default_navigation_timeout = MagicMock()

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.contexts = []
    mock_browser.close = AsyncMock()

    mock_pw = AsyncMock()
    mock_pw.chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)

    # async_playwright() returns a context manager whose __aenter__ returns mock_pw
    mock_playwright_fn = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_pw)
    cm.__aexit__ = AsyncMock(return_value=False)
    mock_playwright_fn.return_value = cm

    return mock_playwright_fn, mock_browser, mock_context


class TestConnectCdpBrowser:
    """测试 connect_cdp_browser 异步上下文管理器。"""

    @pytest.mark.asyncio
    async def test_yields_browser_and_context(self) -> None:
        """正常启动时应 yield (browser, context)。"""
        from apps.core.services.browser.cdp_connector import connect_cdp_browser

        mock_pw_fn, mock_browser, mock_context = _mock_playwright_module()
        profile = _make_profile()

        with (
            patch("playwright.async_api.async_playwright", mock_pw_fn),
            patch(f"{CHROME_PROCESS_MOD}.is_cdp_ready", return_value=True),
        ):
            async with connect_cdp_browser(profile) as (browser, ctx):
                assert browser is mock_browser
                assert ctx is mock_context

        # Assert connect_over_cdp was called on the mocked pw instance
        cm = mock_pw_fn.return_value  # the context manager returned by async_playwright()
        cm.__aenter__.return_value.chromium.connect_over_cdp.assert_awaited_once_with(
            "http://localhost:9222"
        )

    @pytest.mark.asyncio
    async def test_uses_existing_context_when_available(self) -> None:
        """browser.contexts 非空时应复用第一个 context，而非新建。"""
        from apps.core.services.browser.cdp_connector import connect_cdp_browser

        mock_pw_fn, mock_browser, _ = _mock_playwright_module()
        existing_context = AsyncMock()
        existing_context.set_default_timeout = MagicMock()
        existing_context.set_default_navigation_timeout = MagicMock()
        mock_browser.contexts = [existing_context]

        profile = _make_profile()

        with (
            patch("playwright.async_api.async_playwright", mock_pw_fn),
            patch(f"{CHROME_PROCESS_MOD}.is_cdp_ready", return_value=True),
        ):
            async with connect_cdp_browser(profile) as (browser, ctx):
                assert ctx is existing_context

        mock_browser.new_context.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sets_timeouts(self) -> None:
        """应设置 default_timeout 和 default_navigation_timeout。"""
        from apps.core.services.browser.cdp_connector import connect_cdp_browser

        mock_pw_fn, _, mock_context = _mock_playwright_module()
        profile = _make_profile(timeout=5000, navigation_timeout=10000)

        with (
            patch("playwright.async_api.async_playwright", mock_pw_fn),
            patch(f"{CHROME_PROCESS_MOD}.is_cdp_ready", return_value=True),
        ):
            async with connect_cdp_browser(profile):
                mock_context.set_default_timeout.assert_called_once_with(5000)
                mock_context.set_default_navigation_timeout.assert_called_once_with(10000)

    @pytest.mark.asyncio
    async def test_closes_browser_on_exit(self) -> None:
        """退出上下文时应关闭 browser。"""
        from apps.core.services.browser.cdp_connector import connect_cdp_browser

        mock_pw_fn, mock_browser, mock_context = _mock_playwright_module()
        profile = _make_profile()

        with (
            patch("playwright.async_api.async_playwright", mock_pw_fn),
            patch(f"{CHROME_PROCESS_MOD}.is_cdp_ready", return_value=True),
        ):
            async with connect_cdp_browser(profile):
                pass

        mock_browser.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_when_no_cdp_url(self) -> None:
        """profile.cdp_url 为 None 时应抛出 ValueError。"""
        from apps.core.services.browser.cdp_connector import connect_cdp_browser

        profile = _make_profile(cdp_url=None)

        import re
        with pytest.raises(ValueError, match=re.escape("CDP 模式需要设置 profile.cdp_url")):
            async with connect_cdp_browser(profile):
                pass  # pragma: no cover

    @pytest.mark.asyncio
    async def test_auto_launches_chrome_when_cdp_not_ready(self) -> None:
        """CDP 端口未就绪时应自动启动 Chrome 进程。"""
        from apps.core.services.browser.cdp_connector import connect_cdp_browser

        mock_pw_fn, mock_browser, mock_context = _mock_playwright_module()
        mock_process = MagicMock()

        profile = _make_profile(cdp_url="http://localhost:9333")

        with (
            patch("playwright.async_api.async_playwright", mock_pw_fn),
            patch(f"{CHROME_PROCESS_MOD}.is_cdp_ready", return_value=False),
            patch(f"{CHROME_PROCESS_MOD}.launch_chrome", return_value=mock_process) as mock_launch,
            patch(f"{CHROME_PROCESS_MOD}.kill_chrome") as mock_kill,
        ):
            async with connect_cdp_browser(profile):
                pass

        mock_launch.assert_called_once_with(port=9333)
        mock_kill.assert_called_once_with(mock_process)

    @pytest.mark.asyncio
    async def test_no_chrome_cleanup_when_cdp_ready(self) -> None:
        """CDP 已就绪时不应启动或清理 Chrome 进程。"""
        from apps.core.services.browser.cdp_connector import connect_cdp_browser

        mock_pw_fn, _, _ = _mock_playwright_module()
        profile = _make_profile()

        with (
            patch("playwright.async_api.async_playwright", mock_pw_fn),
            patch(f"{CHROME_PROCESS_MOD}.is_cdp_ready", return_value=True),
            patch(f"{CHROME_PROCESS_MOD}.launch_chrome") as mock_launch,
            patch(f"{CHROME_PROCESS_MOD}.kill_chrome") as mock_kill,
        ):
            async with connect_cdp_browser(profile):
                pass

        mock_launch.assert_not_called()
        mock_kill.assert_not_called()

    @pytest.mark.asyncio
    async def test_extracts_port_from_cdp_url(self) -> None:
        """应从 cdp_url 中正确提取端口号。"""
        from apps.core.services.browser.cdp_connector import connect_cdp_browser

        mock_pw_fn, _, _ = _mock_playwright_module()
        profile = _make_profile(cdp_url="http://127.0.0.1:9333")

        with (
            patch("playwright.async_api.async_playwright", mock_pw_fn),
            patch(
                f"{CHROME_PROCESS_MOD}.is_cdp_ready",
                side_effect=lambda port: port == 9333,
            ) as mock_ready,
            patch(f"{CHROME_PROCESS_MOD}.launch_chrome"),
        ):
            async with connect_cdp_browser(profile):
                pass

        mock_ready.assert_called_with(9333)


class TestConnectCdpPage:
    """测试 connect_cdp_page 异步上下文管理器。"""

    @pytest.mark.asyncio
    async def test_yields_page_and_context(self) -> None:
        """正常启动时应 yield (page, context)。"""
        from apps.core.services.browser.cdp_connector import connect_cdp_page

        mock_pw_fn, mock_browser, mock_context = _mock_playwright_module()
        mock_page = MagicMock()
        mock_page.on = MagicMock()
        mock_context.pages = [mock_page]

        profile = _make_profile()

        with (
            patch("playwright.async_api.async_playwright", mock_pw_fn),
            patch(f"{CHROME_PROCESS_MOD}.is_cdp_ready", return_value=True),
        ):
            async with connect_cdp_page(profile) as (page, ctx):
                assert page is mock_page
                assert ctx is mock_context

    @pytest.mark.asyncio
    async def test_creates_new_page_when_no_pages(self) -> None:
        """context.pages 为空时应调用 new_page。"""
        from apps.core.services.browser.cdp_connector import connect_cdp_page

        mock_pw_fn, _, mock_context = _mock_playwright_module()
        mock_new_page = MagicMock()
        mock_new_page.on = MagicMock()
        mock_context.pages = []
        mock_context.new_page = AsyncMock(return_value=mock_new_page)

        profile = _make_profile()

        with (
            patch("playwright.async_api.async_playwright", mock_pw_fn),
            patch(f"{CHROME_PROCESS_MOD}.is_cdp_ready", return_value=True),
        ):
            async with connect_cdp_page(profile) as (page, ctx):
                assert page is mock_new_page

        mock_context.new_page.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_registers_dialog_handler(self) -> None:
        """应为 page 注册 dialog 事件处理器。"""
        from apps.core.services.browser.cdp_connector import connect_cdp_page

        mock_pw_fn, _, mock_context = _mock_playwright_module()
        mock_page = MagicMock()
        mock_page.on = MagicMock()
        mock_context.pages = [mock_page]

        profile = _make_profile()

        with (
            patch("playwright.async_api.async_playwright", mock_pw_fn),
            patch(f"{CHROME_PROCESS_MOD}.is_cdp_ready", return_value=True),
        ):
            async with connect_cdp_page(profile):
                pass

        mock_page.on.assert_called_once()
        call_args = mock_page.on.call_args
        assert call_args[0][0] == "dialog"
        assert callable(call_args[0][1])

    @pytest.mark.asyncio
    async def test_passes_auto_launch_flag(self) -> None:
        """auto_launch 参数应传递给 connect_cdp_browser。"""
        from apps.core.services.browser.cdp_connector import connect_cdp_page

        mock_pw_fn, mock_browser, mock_context = _mock_playwright_module()
        mock_page = MagicMock()
        mock_page.on = MagicMock()
        mock_context.pages = [mock_page]

        profile = _make_profile()

        with (
            patch("playwright.async_api.async_playwright", mock_pw_fn),
            patch(f"{CHROME_PROCESS_MOD}.is_cdp_ready", return_value=True),
        ):
            # Should not raise regardless of auto_launch value
            async with connect_cdp_page(profile, auto_launch=False) as (page, ctx):
                assert page is mock_page
