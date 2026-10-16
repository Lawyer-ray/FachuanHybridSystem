"""core/browser 模块单元测试。"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.core.services.browser.profiles import BrowserProfile, get_profile, register_profile


def _make_manual_handle(
    connected: bool = True,
    close_raises: bool = False,
    fire_events_on_register: bool = True,
) -> BrowserSessionHandle:
    from apps.core.services.browser import BrowserSessionHandle

    browser = MagicMock()
    browser.is_connected.return_value = connected
    if fire_events_on_register:
        # 注册即触发，模拟"用户随后关闭浏览器"让 wait_user_closed 立即返回
        browser.on = MagicMock(side_effect=lambda _evt, handler: handler(browser))
    else:
        browser.on = MagicMock()
    browser.close = AsyncMock(side_effect=RuntimeError("boom") if close_raises else None)
    context = MagicMock()
    context.close = AsyncMock(side_effect=RuntimeError("boom") if close_raises else None)
    page = MagicMock()
    page.close = AsyncMock(side_effect=RuntimeError("boom") if close_raises else None)
    return BrowserSessionHandle(
        profile=BrowserProfile(name="jtn", headless=False),
        browser=browser,
        context=context,
        page=page,
    )


class TestBrowserProfile:
    """BrowserProfile 配置测试。"""

    def test_default_profile(self) -> None:
        p = BrowserProfile(name="test")
        assert p.name == "test"
        assert p.browser_type == "chromium"
        assert p.headless is True
        assert p.slow_mo == 0
        assert p.viewport == {"width": 1920, "height": 1080}
        assert p.anti_detection is True
        assert p.is_cdp is False
        assert p.is_remote is False
        assert p.is_persistent is False

    def test_cdp_profile(self) -> None:
        p = BrowserProfile(name="cdp_test", cdp_url="http://localhost:9222")
        assert p.is_cdp is True
        assert p.is_remote is False

    def test_remote_profile(self) -> None:
        p = BrowserProfile(name="remote", remote_url="ws://remote:3000")
        assert p.is_remote is True

    def test_persistent_profile(self) -> None:
        p = BrowserProfile(name="persist", user_data_dir="/tmp/chrome_data")
        assert p.is_persistent is True

    def test_to_launch_args(self) -> None:
        p = BrowserProfile(name="test", headless=False, slow_mo=500)
        args = p.to_launch_args()
        assert args["headless"] is False
        assert args["slow_mo"] == 500
        # CloakBrowser 内置反检测，不再需要 Chrome 启动参数
        assert "args" not in args or "--no-sandbox" not in args.get("args", [])

    def test_to_launch_args_with_proxy(self) -> None:
        p = BrowserProfile(name="test", proxy="http://proxy:8080")
        args = p.to_launch_args()
        assert args["proxy"] == {"server": "http://proxy:8080"}

    def test_to_context_args(self) -> None:
        p = BrowserProfile(name="test", user_agent="CustomAgent/1.0")
        args = p.to_context_args()
        assert args["viewport"] == {"width": 1920, "height": 1080}
        assert args["user_agent"] == "CustomAgent/1.0"

    def test_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "BROWSER_TEST_HEADLESS": "false",
                "BROWSER_TEST_SLOW_MO": "300",
                "BROWSER_TEST_CDP_URL": "http://localhost:9222",
            },
        ):
            p = BrowserProfile.from_env("test")
            assert p.headless is False
            assert p.slow_mo == 300
            assert p.cdp_url == "http://localhost:9222"

    def test_from_env_defaults(self) -> None:
        # 清除可能存在的环境变量
        env_keys = [k for k in os.environ if k.startswith("BROWSER_MYTEST_")]
        with patch.dict(os.environ, dict.fromkeys(env_keys, ""), clear=False):
            p = BrowserProfile.from_env("mytest")
            assert p.headless is True
            assert p.slow_mo == 0
            assert p.cdp_url is None


class TestGetProfile:
    """get_profile 测试。"""

    @pytest.mark.django_db
    def test_get_default(self) -> None:
        p = get_profile("default")
        assert p.name == "default"
        assert p.headless is True

    def test_get_predefined(self) -> None:
        p = get_profile("gsxt")
        assert p.name == "gsxt"
        assert p.cdp_url == "http://localhost:9222"

    @pytest.mark.django_db
    def test_get_unknown_fallback(self) -> None:
        p = get_profile("nonexistent")
        assert p.name == "default"

    def test_env_override(self) -> None:
        with (
            patch.dict(os.environ, {"BROWSER_CUSTOM_HEADLESS": "false"}),
            patch("apps.core.services.browser.profiles._apply_headless_override", lambda p: p),
        ):
            p = get_profile("custom")
            assert p.headless is False


class TestRegisterProfile:
    """register_profile 测试。"""

    @pytest.mark.django_db
    def test_register_and_get(self) -> None:
        custom = BrowserProfile(name="my_custom", headless=False, slow_mo=100)
        register_profile(custom)
        # get_profile 会用 SystemConfig PLAYWRIGHT_HEADED 覆盖 headless，而该配置的
        # 读取结果经 Redis 缓存在进程间/测试间泄漏（数据库事务回滚不会清缓存），
        # 使断言随运行顺序波动。按本文件既有做法屏蔽覆盖，只验证注册/查找语义。
        with patch("apps.core.services.browser.profiles._apply_headless_override", lambda p: p):
            p = get_profile("my_custom")
        assert p.name == "my_custom"
        assert p.headless is False
        assert p.slow_mo == 100


class TestChromeProcess:
    """chrome_process 工具测试。"""

    def test_is_cdp_ready_false(self) -> None:
        from apps.core.services.browser.chrome_process import is_cdp_ready

        # 没有 Chrome 运行时应该返回 False
        assert is_cdp_ready(port=19999) is False


class TestJtnProfile:
    """jtn 预定义 Profile（OA 半自动页面专用）测试。"""

    def test_jtn_profile_registered_headed(self) -> None:
        # 屏蔽 SystemConfig PLAYWRIGHT_HEADED 覆盖，避免 Redis 缓存在测试间泄漏导致断言波动
        with patch("apps.core.services.browser.profiles._apply_headless_override", lambda p: p):
            p = get_profile("jtn")
        assert p.name == "jtn"
        assert p.headless is False  # 半自动浏览器必须可见
        assert p.is_cdp is False
        assert p.timeout == 60_000
        assert p.navigation_timeout == 60_000


class TestManualSession:
    """手动生命周期浏览器会话（create_browser_async_manual）测试。"""

    @pytest.mark.asyncio
    async def test_rejects_cdp_profile_without_launch(self) -> None:
        from apps.core.services.browser import create_browser_async_manual

        cdp_profile = BrowserProfile(name="cdp_manual", cdp_url="http://localhost:9222")
        with patch("apps.core.services.browser.launcher.ensure_browser_binary") as ensure_mock:
            with pytest.raises(NotImplementedError, match="create_browser_async"):
                await create_browser_async_manual(cdp_profile)
        ensure_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_remote_profile(self) -> None:
        from apps.core.services.browser import create_browser_async_manual

        remote = BrowserProfile(name="remote_manual", remote_url="ws://remote:3000")
        with pytest.raises(NotImplementedError):
            await create_browser_async_manual(remote)

    @pytest.mark.asyncio
    async def test_launch_returns_handle(self) -> None:
        from apps.core.services.browser import BrowserSessionHandle, create_browser_async_manual

        browser = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.add_init_script = AsyncMock()
        browser.new_context = AsyncMock(return_value=context)
        context.new_page = AsyncMock(return_value=page)

        profile = BrowserProfile(name="manual_test", headless=True, anti_detection=True)
        with (
            patch("apps.core.services.browser.launcher.ensure_browser_binary", return_value="/bin/chrome"),
            patch("cloakbrowser.launch_async", new=AsyncMock(return_value=browser)) as launch_mock,
            patch(
                "apps.core.services.browser.manual_session._screen_geometry",
                return_value=((1920, 1080), (1920, 1040)),
            ),
        ):
            handle = await create_browser_async_manual(profile)

        assert isinstance(handle, BrowserSessionHandle)
        assert handle.browser is browser
        assert handle.context is context
        assert handle.page is page
        assert handle.playwright is None  # CloakBrowser: driver 停止内嵌在 browser.close()
        # 手动会话强制有头（半自动=人机协作），profile 的 headless=True 被豁免覆盖
        # 屏幕适配：窗口显式指定为屏幕可用区域（1920×1040）
        launch_mock.assert_awaited_once_with(headless=False, humanize=True, args=["--window-size=1920,1040"])
        # 反检测上下文参数合并进 new_context；屏幕适配时视口跟随窗口（no_viewport）
        _, kwargs = browser.new_context.await_args
        assert kwargs["locale"] == "zh-CN"
        assert kwargs["timezone_id"] == "Asia/Shanghai"
        assert kwargs["no_viewport"] is True
        assert "viewport" not in kwargs
        context.set_default_timeout.assert_called_once_with(profile.timeout)
        context.set_default_navigation_timeout.assert_called_once_with(profile.navigation_timeout)
        page.on.assert_called_once()  # dialog 自动接受

    @pytest.mark.asyncio
    async def test_explicit_viewport_skips_screen_fit(self) -> None:
        """显式传 viewport 时保持固定视口语义，不做屏幕适配。"""
        from apps.core.services.browser import create_browser_async_manual

        browser = MagicMock()
        context = MagicMock()
        page = MagicMock()
        page.add_init_script = AsyncMock()
        browser.new_context = AsyncMock(return_value=context)
        context.new_page = AsyncMock(return_value=page)

        profile = BrowserProfile(name="manual_fixed", headless=True, anti_detection=False)
        with (
            patch("apps.core.services.browser.launcher.ensure_browser_binary", return_value="/bin/chrome"),
            patch("cloakbrowser.launch_async", new=AsyncMock(return_value=browser)) as launch_mock,
        ):
            await create_browser_async_manual(profile, viewport={"width": 800, "height": 600})

        # 未做屏幕适配：无窗口尺寸参数，保持调用方指定的固定视口
        launch_mock.assert_awaited_once_with(headless=False, humanize=False)
        _, kwargs = browser.new_context.await_args
        assert kwargs["viewport"] == {"width": 800, "height": 600}
        assert "no_viewport" not in kwargs

    @pytest.mark.asyncio
    async def test_close_browser_session_closes_in_order(self) -> None:
        from apps.core.services.browser import BrowserSessionHandle, close_browser_session

        session = _make_manual_handle()
        await close_browser_session(session)

        session.page.close.assert_awaited_once()
        session.context.close.assert_awaited_once()
        session.browser.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_browser_session_best_effort_never_raises(self) -> None:
        from apps.core.services.browser import close_browser_session

        session = _make_manual_handle(close_raises=True)
        await close_browser_session(session)  # 不应抛

        session.page.close.assert_awaited_once()
        session.browser.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_browser_session_stops_raw_playwright_driver(self) -> None:
        from apps.core.services.browser import BrowserSessionHandle, close_browser_session

        session = _make_manual_handle()
        playwright = MagicMock()
        playwright.stop = AsyncMock()
        session.playwright = playwright

        await close_browser_session(session)

        playwright.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_helpers_delegate_to_browser(self) -> None:
        session = _make_manual_handle(connected=False)
        assert session.is_connected() is False

    @pytest.mark.asyncio
    async def test_wait_user_closed_blocks_until_close_event(self) -> None:
        """连接中的浏览器：wait_user_closed 挂起直到 close 事件触发，不提前返回。"""
        import asyncio

        session = _make_manual_handle(connected=True, fire_events_on_register=False)
        task = asyncio.create_task(session.wait_user_closed())
        await asyncio.sleep(0)  # 让协程跑到 await closed.wait()
        assert not task.done()

        handlers = {c.args[0]: c.args[1] for c in session.browser.on.call_args_list}
        assert "disconnected" in handlers
        handlers["disconnected"](session.browser)  # 模拟用户关闭窗口

        await asyncio.wait_for(task, timeout=1)

    @pytest.mark.asyncio
    async def test_wait_user_closed_skips_when_disconnected(self) -> None:
        session = _make_manual_handle(connected=False, fire_events_on_register=False)
        await session.wait_user_closed()  # 不应挂死
        # 已断开时仍先注册监听（防竞态），但不进入等待
        session.browser.on.assert_called_once()
        assert session.browser.on.call_args.args[0] == "disconnected"

    @pytest.mark.asyncio
    async def test_wait_user_closed_fires_when_last_page_closed(self) -> None:
        """macOS 关窗不退进程：最后一个页面被关闭必须触发会话结束信号。"""
        import asyncio

        session = _make_manual_handle(connected=True, fire_events_on_register=False)
        pages: list[Any] = [session.page]
        session.context.pages = pages
        handlers: dict[str, Any] = {}

        def _capture(prefix: str) -> Any:
            return lambda evt, cb: handlers.__setitem__(f"{prefix}:{evt}", cb)

        session.context.on = _capture("context")
        session.page.on = _capture("page")

        task = asyncio.create_task(session.wait_user_closed())
        await asyncio.sleep(0)
        assert not task.done()

        # 用户点红色关闭按钮：page close → context.pages 清空 → 会话结束
        pages.clear()
        handlers["page:close"](session.page)
        await asyncio.wait_for(task, timeout=1)

        # 会话期间新开的页面同样被跟踪（context.on("page") 注册 close 监听）
        new_page = MagicMock()
        handlers["context:page"](new_page)
        new_page.on.assert_called_once()
        assert new_page.on.call_args.args[0] == "close"

    @pytest.mark.asyncio
    async def test_wait_user_closed_keeps_waiting_while_tabs_remain(self) -> None:
        """多 tab 场景：只关其中一个 tab 不结束会话，关尽才结束。"""
        import asyncio

        session = _make_manual_handle(connected=True, fire_events_on_register=False)
        tab1, tab2 = MagicMock(), MagicMock()
        pages: list[Any] = [tab1, tab2]
        session.context.pages = pages
        close_handlers: dict[Any, Any] = {}

        def _capture_page(page: Any) -> Any:
            def _on(evt: str, cb: Any) -> None:
                if evt == "close":
                    close_handlers[page] = cb

            return _on

        tab1.on = _capture_page(tab1)
        tab2.on = _capture_page(tab2)
        session.context.on = MagicMock()

        task = asyncio.create_task(session.wait_user_closed())
        await asyncio.sleep(0)
        assert not task.done()

        pages.remove(tab1)  # 关掉第一个 tab，另一个还开着
        close_handlers[tab1](tab1)
        await asyncio.sleep(0)
        assert not task.done()

        pages.clear()  # 最后一个 tab 也关闭 → 会话结束
        close_handlers[tab2](tab2)
        await asyncio.wait_for(task, timeout=1)

    @pytest.mark.asyncio
    async def test_wait_user_closed_returns_when_no_pages_remain(self) -> None:
        """页面已全部关闭（注册前就关尽）时立即返回，不挂死。"""
        import time

        session = _make_manual_handle(connected=True, fire_events_on_register=False)
        session.context.pages = []
        started = time.monotonic()
        result = await asyncio.wait_for(session.wait_user_closed(), timeout=1)
        assert result is None
        assert time.monotonic() - started < 1  # 立即返回，而非等到超时


class TestAntiDetection:
    """AntiDetection 测试。"""

    def test_random_user_agent(self) -> None:
        """UA 由 CloakBrowser 自动处理，get_random_user_agent 保留兼容但返回空。"""
        from apps.core.services.browser.anti_detection import AntiDetection

        ad = AntiDetection()
        ua = ad.get_random_user_agent()
        assert isinstance(ua, str)

    def test_get_context_options(self) -> None:
        from apps.core.services.browser.anti_detection import AntiDetection

        ad = AntiDetection()
        opts = ad.get_context_options()
        assert "viewport" in opts
        assert "locale" in opts
        assert opts["locale"] == "zh-CN"
        assert "timezone_id" in opts

    def test_fingerprint_js_default_screen_spoof(self) -> None:
        """默认指纹 JS 伪装 1920×1080（与固定视口配套），无占位符残留。"""
        from apps.core.services.browser.anti_detection import AntiDetection

        js = AntiDetection()._fingerprint_js()
        assert "get: () => 1920" in js
        assert "get: () => 1080" in js
        assert "__SCREEN_WIDTH__" not in js
        assert "__SCREEN_HEIGHT__" not in js

    def test_fingerprint_js_screen_override_uses_real_screen(self) -> None:
        """传入真实屏幕尺寸时，screen 伪装切换为真实值（半自动屏幕适配路径）。"""
        from apps.core.services.browser.anti_detection import AntiDetection

        js = AntiDetection()._fingerprint_js((1800, 1169))
        assert "get: () => 1800" in js
        assert "get: () => 1169" in js
        assert "get: () => 1920" not in js
        assert "get: () => 1080" not in js


class TestScreenGeometry:
    """_screen_geometry 屏幕几何查询测试。"""

    def test_fallback_when_appkit_unavailable(self) -> None:
        """AppKit 不可用（非 macOS）时回退 1280×800 保守值。"""
        import sys

        from apps.core.services.browser.manual_session import _screen_geometry

        with patch.dict(sys.modules, {"AppKit": None}):
            screen_size, window_size = _screen_geometry()
        assert screen_size == (1280, 800)
        assert window_size == (1280, 800)

    def test_appkit_visible_frame_bounded_by_screen(self) -> None:
        """真实环境（macOS）：窗口可用区域不得大于整屏。"""
        from apps.core.services.browser.manual_session import _screen_geometry

        (screen_w, screen_h), (window_w, window_h) = _screen_geometry()
        assert 0 < window_w <= screen_w
        assert 0 < window_h <= screen_h


class TestModuleImports:
    """模块导入测试。"""

    def test_import_create_browser(self) -> None:
        from apps.core.services.browser import create_browser

        assert callable(create_browser)

    def test_import_create_browser_async(self) -> None:
        from apps.core.services.browser import create_browser_async

        assert callable(create_browser_async)

    def test_import_browser_profile(self) -> None:
        from apps.core.services.browser import BrowserProfile

        assert BrowserProfile is not None

    def test_import_chrome_process(self) -> None:
        from apps.core.services.browser import is_cdp_ready, kill_chrome, launch_chrome

        assert callable(launch_chrome)
        assert callable(kill_chrome)
        assert callable(is_cdp_ready)


class TestEnsureBrowserBinary:
    """ensure_browser_binary 智能报错封装测试。"""

    def test_returns_binary_path_when_ready(self) -> None:
        from apps.core.services.browser.launcher import ensure_browser_binary

        with patch("cloakbrowser.ensure_binary", return_value="/.cloakbrowser/chrome"):
            assert ensure_browser_binary() == "/.cloakbrowser/chrome"

    def test_network_error_gives_actionable_hint(self) -> None:
        from pathlib import Path

        import httpx

        from apps.core.services.browser.launcher import CloakBrowserInstallError, ensure_browser_binary

        with (
            patch("cloakbrowser.ensure_binary", side_effect=httpx.ConnectTimeout("timed out")),
            patch("cloakbrowser.config.get_binary_path", return_value=Path("/.cloakbrowser/chromium/chrome.exe")),
        ):
            with pytest.raises(CloakBrowserInstallError) as ei:
                ensure_browser_binary()
        msg = str(ei.value)
        assert "下载失败" in msg
        assert "CLOAKBROWSER_DOWNLOAD_URL" in msg
        assert "CLOAKBROWSER_BINARY_PATH" in msg
        assert "timed out" in msg  # 保留原始错误便于排查

    def test_binary_path_non_existent_gives_hint(self) -> None:
        from apps.core.services.browser.launcher import CloakBrowserInstallError, ensure_browser_binary

        with (
            patch("cloakbrowser.ensure_binary", side_effect=FileNotFoundError("no")),
            patch("cloakbrowser.config.get_local_binary_override", return_value="C:/nope/chrome.exe"),
        ):
            with pytest.raises(CloakBrowserInstallError) as ei:
                ensure_browser_binary()
        assert "CLOAKBROWSER_BINARY_PATH" in str(ei.value)

    def test_runtime_error_preserves_message(self) -> None:
        from apps.core.services.browser.launcher import CloakBrowserInstallError, ensure_browser_binary

        with patch("cloakbrowser.ensure_binary", side_effect=RuntimeError("Unsupported platform")):
            with pytest.raises(CloakBrowserInstallError) as ei:
                ensure_browser_binary()
        assert "Unsupported platform" in str(ei.value)
