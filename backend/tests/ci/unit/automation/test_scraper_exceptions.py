"""爬虫核心服务测试。"""

from __future__ import annotations

from apps.automation.services.scraper.core.exceptions import (
    ScraperException,
    BrowserCreationError,
    BrowserConfigurationError,
    CaptchaRecognitionError,
    CookieLoadError,
    LoginError,
)


class TestScraperExceptions:
    """爬虫异常类测试。"""

    def test_scraper_exception(self) -> None:
        """基础异常。"""
        e = ScraperException("测试错误")
        assert str(e) == "测试错误"
        assert isinstance(e, Exception)

    def test_browser_creation_error_basic(self) -> None:
        """浏览器创建失败异常。"""
        e = BrowserCreationError("无法启动浏览器")
        assert "浏览器创建失败" in str(e)
        assert e.config is None
        assert e.original_error is None

    def test_browser_creation_error_with_config(self) -> None:
        """带配置的浏览器创建失败异常。"""
        config = {"headless": True, "timeout": 30}
        e = BrowserCreationError("无法启动浏览器", config=config)
        assert "headless" in str(e)
        assert "timeout" in str(e)

    def test_browser_creation_error_with_original(self) -> None:
        """带原始异常的浏览器创建失败异常。"""
        original = ConnectionError("连接超时")
        e = BrowserCreationError("无法启动浏览器", original_error=original)
        assert "ConnectionError" in str(e)

    def test_browser_configuration_error(self) -> None:
        """浏览器配置错误异常。"""
        e = BrowserConfigurationError("timeout", -1, "不能为负数")
        assert e.field == "timeout"
        assert e.value == -1
        assert e.reason == "不能为负数"
        assert "timeout" in str(e)

    def test_captcha_recognition_error_basic(self) -> None:
        """验证码识别失败异常。"""
        e = CaptchaRecognitionError("识别失败")
        assert "验证码识别失败" in str(e)
        assert e.attempts == 0
        assert e.selector is None

    def test_captcha_recognition_error_with_attempts(self) -> None:
        """带尝试次数的验证码识别失败异常。"""
        e = CaptchaRecognitionError("识别失败", attempts=3, selector="#captcha")
        assert "3" in str(e)
        assert "#captcha" in str(e)

    def test_cookie_load_error_basic(self) -> None:
        """Cookie 加载失败异常。"""
        e = CookieLoadError("Cookie 无效")
        assert "Cookie 加载失败" in str(e)
        assert e.site_name is None
        assert e.account is None

    def test_cookie_load_error_with_details(self) -> None:
        """带详情的 Cookie 加载失败异常。"""
        e = CookieLoadError("Cookie 无效", site_name="court_zxfw", account="test")
        assert "court_zxfw" in str(e)
        assert "test" in str(e)

    def test_login_error_basic(self) -> None:
        """登录失败异常。"""
        e = LoginError("登录失败")
        assert "登录失败" in str(e)
        assert e.account is None
        assert e.reason is None
        assert e.screenshot_path is None

    def test_login_error_with_details(self) -> None:
        """带详情的登录失败异常。"""
        e = LoginError(
            "登录失败",
            account="test_user",
            reason="密码错误",
            screenshot_path="/tmp/error.png",
        )
        assert "test_user" in str(e)
        assert "密码错误" in str(e)
        assert "/tmp/error.png" in str(e)

    def test_exception_inheritance(self) -> None:
        """异常继承关系。"""
        assert issubclass(BrowserCreationError, ScraperException)
        assert issubclass(BrowserConfigurationError, ScraperException)
        assert issubclass(CaptchaRecognitionError, ScraperException)
        assert issubclass(CookieLoadError, ScraperException)
        assert issubclass(LoginError, ScraperException)
        assert issubclass(ScraperException, Exception)
