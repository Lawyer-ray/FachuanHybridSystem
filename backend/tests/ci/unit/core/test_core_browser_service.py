"""core/browser 模块单元测试。"""

from __future__ import annotations

import os
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
        with patch.dict(os.environ, {"BROWSER_CUSTOM_HEADLESS": "false"}), \
             patch("apps.core.services.browser.profiles._apply_headless_override", lambda p: p):
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
        with patch("apps.core.services.browser.launcher.ensure_browser_binary", return_value="/bin/chrome"), \
             patch("cloakbrowser.launch_async", new=AsyncMock(return_value=browser)) as launch_mock:
            handle = await create_browser_async_manual(profile)

        assert isinstance(handle, BrowserSessionHandle)
        assert handle.browser is browser
        assert handle.context is context
        assert handle.page is page
        assert handle.playwright is None  # CloakBrowser: driver 停止内嵌在 browser.close()
        # 手动会话强制有头（半自动=人机协作），profile 的 headless=True 被豁免覆盖
        launch_mock.assert_awaited_once_with(headless=False, humanize=True)
        # 反检测上下文参数合并进 new_context
        _, kwargs = browser.new_context.await_args
        assert kwargs["locale"] == "zh-CN"
        assert kwargs["timezone_id"] == "Asia/Shanghai"
        context.set_default_timeout.assert_called_once_with(profile.timeout)
        context.set_default_navigation_timeout.assert_called_once_with(profile.navigation_timeout)
        page.on.assert_called_once()  # dialog 自动接受

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

        with patch("cloakbrowser.ensure_binary", side_effect=httpx.ConnectTimeout("timed out")), \
             patch("cloakbrowser.config.get_binary_path", return_value=Path("/.cloakbrowser/chromium/chrome.exe")):
            with pytest.raises(CloakBrowserInstallError) as ei:
                ensure_browser_binary()
        msg = str(ei.value)
        assert "下载失败" in msg
        assert "CLOAKBROWSER_DOWNLOAD_URL" in msg
        assert "CLOAKBROWSER_BINARY_PATH" in msg
        assert "timed out" in msg  # 保留原始错误便于排查

    def test_binary_path_non_existent_gives_hint(self) -> None:
        from apps.core.services.browser.launcher import CloakBrowserInstallError, ensure_browser_binary

        with patch("cloakbrowser.ensure_binary", side_effect=FileNotFoundError("no")), \
             patch("cloakbrowser.config.get_local_binary_override", return_value="C:/nope/chrome.exe"):
            with pytest.raises(CloakBrowserInstallError) as ei:
                ensure_browser_binary()
        assert "CLOAKBROWSER_BINARY_PATH" in str(ei.value)

    def test_runtime_error_preserves_message(self) -> None:
        from apps.core.services.browser.launcher import CloakBrowserInstallError, ensure_browser_binary

        with patch("cloakbrowser.ensure_binary", side_effect=RuntimeError("Unsupported platform")):
            with pytest.raises(CloakBrowserInstallError) as ei:
                ensure_browser_binary()
        assert "Unsupported platform" in str(ei.value)
