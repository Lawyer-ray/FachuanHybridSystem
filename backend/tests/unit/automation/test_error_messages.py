"""
测试错误消息清晰度

**Feature: automation-decoupling, Property 13: Error message clarity**

验证：对于任何错误条件（浏览器创建失败、验证码失败、Cookie 失败、登录失败），
系统应该提供清晰、描述性的错误消息，包含足够的调试上下文。
"""
import pytest
from apps.automation.services.scraper.core.exceptions import (
    BrowserCreationError,
    BrowserConfigurationError,
    CaptchaRecognitionError,
    CookieLoadError,
    LoginError,
)


class TestErrorMessageClarity:
    """
    测试错误消息清晰度
    
    **Feature: automation-decoupling, Property 13: Error message clarity**
    """
    
    def test_property_browser_creation_error_clarity(self):
        """
        **Feature: automation-decoupling, Property 13: Error message clarity**
        
        属性测试：浏览器创建错误应该包含清晰的错误消息和调试上下文
        
        **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**
        """
        # 创建一个浏览器创建错误
        error = BrowserCreationError(
            message="无法启动 Chromium",
            config={"headless": True, "slow_mo": 500},
            original_error=RuntimeError("端口 9222 已被占用")
        )
        
        error_msg = str(error)
        
        # 验证：错误消息应该包含关键信息
        assert "无法启动 Chromium" in error_msg, \
            "错误消息应该包含主要错误描述"
        
        assert "headless" in error_msg, \
            "错误消息应该包含配置信息"
        
        assert "RuntimeError" in error_msg, \
            "错误消息应该包含原始错误类型"
        
        assert "端口 9222" in error_msg, \
            "错误消息应该包含原始错误详情"
        
        # 验证：错误对象应该保存上下文
        assert error.config is not None, \
            "错误对象应该保存配置信息"
        
        assert error.original_error is not None, \
            "错误对象应该保存原始错误"
    
    def test_browser_configuration_error_clarity(self):
        """测试配置错误消息清晰度"""
        error = BrowserConfigurationError(
            field="viewport_width",
            value=-100,
            reason="宽度必须为正数"
        )
        
        error_msg = str(error)
        
        # 验证关键信息
        assert "viewport_width" in error_msg
        assert "-100" in error_msg
        assert "正数" in error_msg
        
        # 验证上下文保存
        assert error.field == "viewport_width"
        assert error.value == -100
        assert error.reason == "宽度必须为正数"
    
    def test_captcha_recognition_error_clarity(self):
        """测试验证码识别错误消息清晰度"""
        error = CaptchaRecognitionError(
            message="OCR 引擎返回空结果",
            attempts=3,
            selector="#captcha-image"
        )
        
        error_msg = str(error)
        
        # 验证关键信息
        assert "OCR 引擎返回空结果" in error_msg
        assert "3" in error_msg
        assert "#captcha-image" in error_msg
        
        # 验证上下文保存
        assert error.attempts == 3
        assert error.selector == "#captcha-image"
    
    def test_cookie_load_error_clarity(self):
        """测试 Cookie 加载错误消息清晰度"""
        error = CookieLoadError(
            message="Cookie 格式无效",
            site_name="court_zxfw",
            account="user@example.com"
        )
        
        error_msg = str(error)
        
        # 验证关键信息
        assert "Cookie 格式无效" in error_msg
        assert "court_zxfw" in error_msg
        assert "user@example.com" in error_msg
        
        # 验证上下文保存
        assert error.site_name == "court_zxfw"
        assert error.account == "user@example.com"
    
    def test_login_error_clarity(self):
        """测试登录错误消息清晰度"""
        error = LoginError(
            message="登录失败",
            account="test_user",
            reason="验证码识别错误",
            screenshot_path="/tmp/error_screenshot.png"
        )
        
        error_msg = str(error)
        
        # 验证关键信息
        assert "登录失败" in error_msg
        assert "test_user" in error_msg
        assert "验证码识别错误" in error_msg
        assert "error_screenshot.png" in error_msg
        
        # 验证上下文保存
        assert error.account == "test_user"
        assert error.reason == "验证码识别错误"
        assert error.screenshot_path == "/tmp/error_screenshot.png"
    
    def test_error_messages_are_descriptive(self):
        """测试所有错误消息都是描述性的"""
        errors = [
            BrowserCreationError("测试", config={"test": "value"}),
            BrowserConfigurationError("field", "value", "reason"),
            CaptchaRecognitionError("测试", attempts=1),
            CookieLoadError("测试", site_name="site"),
            LoginError("测试", account="user"),
        ]
        
        for error in errors:
            error_msg = str(error)
            # 错误消息不应该为空
            assert len(error_msg) > 0, \
                f"{type(error).__name__} 错误消息不应该为空"
            
            # 错误消息应该包含错误类型的关键词
            error_type = type(error).__name__
            # 至少应该包含一些描述性文本
            assert len(error_msg) > 10, \
                f"{error_type} 错误消息应该足够详细"
    
    def test_error_context_preservation(self):
        """测试错误上下文被正确保存"""
        # BrowserCreationError 应该保存配置和原始错误
        browser_error = BrowserCreationError(
            "test",
            config={"key": "value"},
            original_error=ValueError("original")
        )
        assert browser_error.config == {"key": "value"}
        assert isinstance(browser_error.original_error, ValueError)
        
        # BrowserConfigurationError 应该保存字段信息
        config_error = BrowserConfigurationError("field", 123, "reason")
        assert config_error.field == "field"
        assert config_error.value == 123
        assert config_error.reason == "reason"
        
        # CaptchaRecognitionError 应该保存尝试次数和选择器
        captcha_error = CaptchaRecognitionError("test", attempts=5, selector="#id")
        assert captcha_error.attempts == 5
        assert captcha_error.selector == "#id"
        
        # CookieLoadError 应该保存网站和账号
        cookie_error = CookieLoadError("test", site_name="site", account="acc")
        assert cookie_error.site_name == "site"
        assert cookie_error.account == "acc"
        
        # LoginError 应该保存账号、原因和截图路径
        login_error = LoginError("test", account="user", reason="why", screenshot_path="/path")
        assert login_error.account == "user"
        assert login_error.reason == "why"
        assert login_error.screenshot_path == "/path"
