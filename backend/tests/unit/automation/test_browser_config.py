"""
BrowserConfig 属性测试

使用 Hypothesis 进行属性测试，验证 BrowserConfig 的正确性。
"""

import os

# Django setup
import django
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from apps.core.path import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
django.setup()

from apps.automation.services.scraper.config.browser_config import BrowserConfig, ConfigurationError

# =============================================================================
# Property Test 1.1: Configuration validation
# **Feature: automation-decoupling, Property 4: Configuration validation**
# **Validates: Requirements 2.5, 7.4**
# =============================================================================


class TestBrowserConfigValidation:
    """
    **Feature: automation-decoupling, Property 4: Configuration validation**

    验证：对于任何配置值，无效值应被拒绝并提供清晰的错误消息，
    有效值应被接受。
    """

    @given(
        slow_mo=st.integers(min_value=0, max_value=10000),
        viewport_width=st.integers(min_value=1, max_value=4096),
        viewport_height=st.integers(min_value=1, max_value=2160),
        timeout=st.integers(min_value=1, max_value=300000),
        navigation_timeout=st.integers(min_value=1, max_value=300000),
    )
    @settings(max_examples=100)
    def test_valid_config_passes_validation(
        self,
        slow_mo: int,
        viewport_width: int,
        viewport_height: int,
        timeout: int,
        navigation_timeout: int,
    ):
        """
        **Feature: automation-decoupling, Property 4: Configuration validation**

        对于任何有效的配置值组合，validate() 应该成功通过。
        """
        config = BrowserConfig(
            slow_mo=slow_mo,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            timeout=timeout,
            navigation_timeout=navigation_timeout,
        )

        # 有效配置应该通过验证
        config.validate()  # 不应抛出异常

    @given(slow_mo=st.integers(max_value=-1))
    @settings(max_examples=100)
    def test_negative_slow_mo_rejected(self, slow_mo: int):
        """
        **Feature: automation-decoupling, Property 4: Configuration validation**

        对于任何负数的 slow_mo 值，validate() 应该抛出 ConfigurationError。
        """
        config = BrowserConfig(slow_mo=slow_mo)

        with pytest.raises(ConfigurationError) as exc_info:
            config.validate()

        assert "slow_mo" in str(exc_info.value)
        assert str(slow_mo) in str(exc_info.value)

    @given(viewport_width=st.integers(max_value=0))
    @settings(max_examples=100)
    def test_non_positive_viewport_width_rejected(self, viewport_width: int):
        """
        **Feature: automation-decoupling, Property 4: Configuration validation**

        对于任何非正数的 viewport_width 值，validate() 应该抛出 ConfigurationError。
        """
        config = BrowserConfig(viewport_width=viewport_width)

        with pytest.raises(ConfigurationError) as exc_info:
            config.validate()

        assert "viewport_width" in str(exc_info.value)

    @given(viewport_height=st.integers(max_value=0))
    @settings(max_examples=100)
    def test_non_positive_viewport_height_rejected(self, viewport_height: int):
        """
        **Feature: automation-decoupling, Property 4: Configuration validation**

        对于任何非正数的 viewport_height 值，validate() 应该抛出 ConfigurationError。
        """
        config = BrowserConfig(viewport_height=viewport_height)

        with pytest.raises(ConfigurationError) as exc_info:
            config.validate()

        assert "viewport_height" in str(exc_info.value)

    @given(timeout=st.integers(max_value=0))
    @settings(max_examples=100)
    def test_non_positive_timeout_rejected(self, timeout: int):
        """
        **Feature: automation-decoupling, Property 4: Configuration validation**

        对于任何非正数的 timeout 值，validate() 应该抛出 ConfigurationError。
        """
        config = BrowserConfig(timeout=timeout)

        with pytest.raises(ConfigurationError) as exc_info:
            config.validate()

        assert "timeout" in str(exc_info.value)

    @given(navigation_timeout=st.integers(max_value=0))
    @settings(max_examples=100)
    def test_non_positive_navigation_timeout_rejected(self, navigation_timeout: int):
        """
        **Feature: automation-decoupling, Property 4: Configuration validation**

        对于任何非正数的 navigation_timeout 值，validate() 应该抛出 ConfigurationError。
        """
        config = BrowserConfig(navigation_timeout=navigation_timeout)

        with pytest.raises(ConfigurationError) as exc_info:
            config.validate()

        assert "navigation_timeout" in str(exc_info.value)

    @given(user_agent=st.sampled_from(["", "   ", "\t", "\n"]))
    @settings(max_examples=10)
    def test_empty_user_agent_rejected(self, user_agent: str):
        """
        **Feature: automation-decoupling, Property 4: Configuration validation**

        对于空或仅包含空白字符的 user_agent，validate() 应该抛出 ConfigurationError。
        """
        config = BrowserConfig(user_agent=user_agent)

        with pytest.raises(ConfigurationError) as exc_info:
            config.validate()

        assert "user_agent" in str(exc_info.value)


# =============================================================================
# Property Test 1.2: Environment variable loading
# **Feature: automation-decoupling, Property 5: Environment variable loading**
# **Validates: Requirements 2.1**
# =============================================================================


class TestBrowserConfigEnvLoading:
    """
    **Feature: automation-decoupling, Property 5: Environment variable loading**

    验证：对于任何环境变量集合，当 BrowserConfig 从环境加载时，
    结果配置应反映这些环境变量，或对缺失的变量使用默认值。
    """

    @given(
        headless=st.booleans(),
        slow_mo=st.integers(min_value=0, max_value=5000),
        viewport_width=st.integers(min_value=100, max_value=4096),
        viewport_height=st.integers(min_value=100, max_value=2160),
        timeout=st.integers(min_value=1000, max_value=120000),
    )
    @settings(max_examples=100)
    def test_env_vars_are_loaded(
        self,
        headless: bool,
        slow_mo: int,
        viewport_width: int,
        viewport_height: int,
        timeout: int,
    ):
        """
        **Feature: automation-decoupling, Property 5: Environment variable loading**

        对于任何有效的环境变量值，from_env() 应该正确加载这些值。
        """
        # 保存原始环境变量
        original_env = {
            "BROWSER_HEADLESS": os.environ.get("BROWSER_HEADLESS"),
            "BROWSER_SLOW_MO": os.environ.get("BROWSER_SLOW_MO"),
            "BROWSER_VIEWPORT_WIDTH": os.environ.get("BROWSER_VIEWPORT_WIDTH"),
            "BROWSER_VIEWPORT_HEIGHT": os.environ.get("BROWSER_VIEWPORT_HEIGHT"),
            "BROWSER_TIMEOUT": os.environ.get("BROWSER_TIMEOUT"),
        }

        try:
            # 设置环境变量
            os.environ["BROWSER_HEADLESS"] = "true" if headless else "false"
            os.environ["BROWSER_SLOW_MO"] = str(slow_mo)
            os.environ["BROWSER_VIEWPORT_WIDTH"] = str(viewport_width)
            os.environ["BROWSER_VIEWPORT_HEIGHT"] = str(viewport_height)
            os.environ["BROWSER_TIMEOUT"] = str(timeout)

            # 从环境变量加载配置
            config = BrowserConfig.from_env()

            # 验证配置值与环境变量一致
            assert config.headless == headless
            assert config.slow_mo == slow_mo
            assert config.viewport_width == viewport_width
            assert config.viewport_height == viewport_height
            assert config.timeout == timeout

        finally:
            # 恢复原始环境变量
            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_missing_env_vars_use_defaults(self):
        """
        **Feature: automation-decoupling, Property 5: Environment variable loading**

        当环境变量缺失时，from_env() 应该使用默认值。
        """
        # 保存并清除相关环境变量
        env_keys = [
            "BROWSER_HEADLESS",
            "BROWSER_SLOW_MO",
            "BROWSER_VIEWPORT_WIDTH",
            "BROWSER_VIEWPORT_HEIGHT",
            "BROWSER_TIMEOUT",
            "BROWSER_NAVIGATION_TIMEOUT",
            "BROWSER_USER_AGENT",
            "BROWSER_SAVE_SCREENSHOTS",
            "BROWSER_SCREENSHOT_DIR",
        ]
        original_env = {key: os.environ.get(key) for key in env_keys}

        try:
            # 清除所有相关环境变量
            for key in env_keys:
                os.environ.pop(key, None)

            # 从环境变量加载配置
            config = BrowserConfig.from_env()
            defaults = BrowserConfig()

            # 验证使用了默认值
            assert config.headless == defaults.headless
            assert config.slow_mo == defaults.slow_mo
            assert config.viewport_width == defaults.viewport_width
            assert config.viewport_height == defaults.viewport_height
            assert config.timeout == defaults.timeout
            assert config.navigation_timeout == defaults.navigation_timeout
            assert config.user_agent == defaults.user_agent
            assert config.save_screenshots == defaults.save_screenshots

        finally:
            # 恢复原始环境变量
            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    @given(
        headless_str=st.sampled_from(["true", "True", "TRUE", "1", "yes", "on"]),
    )
    @settings(max_examples=10)
    def test_truthy_headless_values(self, headless_str: str):
        """
        **Feature: automation-decoupling, Property 5: Environment variable loading**

        对于任何表示 true 的字符串，headless 应该被解析为 True。
        """
        original = os.environ.get("BROWSER_HEADLESS")

        try:
            os.environ["BROWSER_HEADLESS"] = headless_str
            config = BrowserConfig.from_env()
            assert config.headless is True
        finally:
            if original is None:
                os.environ.pop("BROWSER_HEADLESS", None)
            else:
                os.environ["BROWSER_HEADLESS"] = original

    @given(
        headless_str=st.sampled_from(["false", "False", "FALSE", "0", "no", "off", "random"]),
    )
    @settings(max_examples=10)
    def test_falsy_headless_values(self, headless_str: str):
        """
        **Feature: automation-decoupling, Property 5: Environment variable loading**

        对于任何不表示 true 的字符串，headless 应该被解析为 False。
        """
        original = os.environ.get("BROWSER_HEADLESS")

        try:
            os.environ["BROWSER_HEADLESS"] = headless_str
            config = BrowserConfig.from_env()
            assert config.headless is False
        finally:
            if original is None:
                os.environ.pop("BROWSER_HEADLESS", None)
            else:
                os.environ["BROWSER_HEADLESS"] = original

    def test_invalid_int_env_var_uses_default(self):
        """
        **Feature: automation-decoupling, Property 5: Environment variable loading**

        当整数环境变量包含无效值时，应该使用默认值。
        """
        original = os.environ.get("BROWSER_SLOW_MO")

        try:
            os.environ["BROWSER_SLOW_MO"] = "not_a_number"
            config = BrowserConfig.from_env()
            defaults = BrowserConfig()
            assert config.slow_mo == defaults.slow_mo
        finally:
            if original is None:
                os.environ.pop("BROWSER_SLOW_MO", None)
            else:
                os.environ["BROWSER_SLOW_MO"] = original


# =============================================================================
# Additional unit tests for to_playwright_args
# =============================================================================


class TestBrowserConfigPlaywrightArgs:
    """测试 to_playwright_args 方法"""

    def test_to_playwright_args_structure(self):
        """验证 to_playwright_args 返回正确的结构"""
        config = BrowserConfig(
            headless=True,
            slow_mo=500,
            viewport_width=1920,
            viewport_height=1080,
            timeout=60000,
            navigation_timeout=45000,
        )

        args = config.to_playwright_args()

        # 验证结构
        assert "launch_args" in args
        assert "context_args" in args
        assert "timeout" in args
        assert "navigation_timeout" in args

        # 验证 launch_args
        assert args["launch_args"]["headless"] is True
        assert args["launch_args"]["slow_mo"] == 500
        assert "--disable-blink-features=AutomationControlled" in args["launch_args"]["args"]

        # 验证 context_args
        assert args["context_args"]["viewport"]["width"] == 1920
        assert args["context_args"]["viewport"]["height"] == 1080

        # 验证超时
        assert args["timeout"] == 60000
        assert args["navigation_timeout"] == 45000

    def test_slow_mo_zero_not_included(self):
        """当 slow_mo 为 0 时，不应包含在 launch_args 中"""
        config = BrowserConfig(slow_mo=0)
        args = config.to_playwright_args()

        assert "slow_mo" not in args["launch_args"]
