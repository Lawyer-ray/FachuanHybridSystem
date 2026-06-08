"""core/browser 模块单元测试。"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from apps.core.services.browser.profiles import BrowserProfile, get_profile, register_profile


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

    def test_get_default(self) -> None:
        p = get_profile("default")
        assert p.name == "default"
        assert p.headless is True

    def test_get_predefined(self) -> None:
        p = get_profile("gsxt")
        assert p.name == "gsxt"
        assert p.cdp_url == "http://localhost:9222"

    def test_get_unknown_fallback(self) -> None:
        p = get_profile("nonexistent")
        assert p.name == "default"

    def test_env_override(self) -> None:
        with patch.dict(os.environ, {"BROWSER_CUSTOM_HEADLESS": "false"}):
            p = get_profile("custom")
            assert p.headless is False


class TestRegisterProfile:
    """register_profile 测试。"""

    def test_register_and_get(self) -> None:
        custom = BrowserProfile(name="my_custom", headless=False, slow_mo=100)
        register_profile(custom)
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
