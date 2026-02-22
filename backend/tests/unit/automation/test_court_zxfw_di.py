"""
测试 CourtZxfwService 依赖注入

**Feature: automation-decoupling, Property 8: Dependency injection**

验证：对于任何 CaptchaRecognizer 实现，当注入到 CourtZxfwService 时，
服务应该使用该识别器进行所有验证码识别操作。
"""

from typing import Optional

import pytest

from apps.automation.services.scraper.core.captcha_recognizer import CaptchaRecognizer, DdddocrRecognizer
from apps.automation.services.scraper.core.cookie_service import CookieService
from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService


class MockCaptchaRecognizer(CaptchaRecognizer):
    """Mock 验证码识别器用于测试"""

    def __init__(self, return_value: str = "MOCK1234"):
        self.return_value = return_value
        self.recognize_called = False
        self.recognize_from_element_called = False
        self.recognize_call_count = 0
        self.recognize_from_element_call_count = 0

    def recognize(self, image_bytes: bytes) -> str | None:
        self.recognize_called = True
        self.recognize_call_count += 1
        return self.return_value

    def recognize_from_element(self, page, selector: str) -> str | None:
        self.recognize_from_element_called = True
        self.recognize_from_element_call_count += 1
        return self.return_value


class MockCookieService:
    """Mock Cookie 服务用于测试"""

    def __init__(self):
        self.load_called = False
        self.save_called = False


class MockPage:
    """Mock Page 对象"""

    def locator(self, selector):
        return MockLocator()


class MockLocator:
    """Mock Locator 对象"""

    def wait_for(self, state, timeout):
        pass

    def screenshot(self):
        return b"mock screenshot data"


class MockContext:
    """Mock BrowserContext 对象"""

    pass


class TestDependencyInjection:
    """测试依赖注入"""

    def test_default_dependencies(self):
        """测试默认依赖"""
        mock_page = MockPage()
        mock_context = MockContext()

        service = CourtZxfwService(mock_page, mock_context)  # type: ignore[arg-type]

        assert hasattr(service, "captcha_recognizer")
        assert hasattr(service, "cookie_service")
        assert isinstance(service.captcha_recognizer, DdddocrRecognizer)
        assert isinstance(service.cookie_service, CookieService)

    def test_inject_custom_captcha_recognizer(self):
        """测试注入自定义验证码识别器"""
        mock_page = MockPage()
        mock_context = MockContext()
        mock_recognizer = MockCaptchaRecognizer("TEST5678")

        service = CourtZxfwService(mock_page, mock_context, captcha_recognizer=mock_recognizer)  # type: ignore[arg-type]

        assert service.captcha_recognizer is mock_recognizer
        assert service.captcha_recognizer.return_value == "TEST5678"  # type: ignore[attr-defined]

    def test_inject_custom_cookie_service(self):
        """测试注入自定义 Cookie 服务"""
        mock_page = MockPage()
        mock_context = MockContext()
        mock_cookie_service = MockCookieService()

        service = CourtZxfwService(mock_page, mock_context, cookie_service=mock_cookie_service)  # type: ignore[arg-type]

        assert service.cookie_service is mock_cookie_service

    def test_inject_both_dependencies(self):
        """测试同时注入两个依赖"""
        mock_page = MockPage()
        mock_context = MockContext()
        mock_recognizer = MockCaptchaRecognizer()
        mock_cookie_service = MockCookieService()

        service = CourtZxfwService(
            mock_page, mock_context, captcha_recognizer=mock_recognizer, cookie_service=mock_cookie_service  # type: ignore[arg-type]
        )

        assert service.captcha_recognizer is mock_recognizer
        assert service.cookie_service is mock_cookie_service

    def test_custom_site_name(self):
        """测试自定义 site_name"""
        mock_page = MockPage()
        mock_context = MockContext()

        service = CourtZxfwService(mock_page, mock_context, site_name="custom_site")  # type: ignore[arg-type]

        assert service.site_name == "custom_site"

    def test_default_site_name(self):
        """测试默认 site_name"""
        mock_page = MockPage()
        mock_context = MockContext()

        service = CourtZxfwService(mock_page, mock_context)  # type: ignore[arg-type]

        assert service.site_name == "court_zxfw"

    def test_property_injected_recognizer_is_used(self):
        """
        **Feature: automation-decoupling, Property 8: Dependency injection**

        属性测试：验证注入的识别器被实际使用

        **Validates: Requirements 3.5**
        """
        mock_page = MockPage()
        mock_context = MockContext()
        mock_recognizer = MockCaptchaRecognizer("INJECTED")

        service = CourtZxfwService(mock_page, mock_context, captcha_recognizer=mock_recognizer)  # type: ignore[arg-type]

        # 调用内部方法来触发验证码识别
        result = service._recognize_captcha(save_debug=False)

        # 验证：
        # 1. 注入的识别器被调用
        assert mock_recognizer.recognize_from_element_called, "注入的识别器应该被调用"

        # 2. 返回值来自注入的识别器
        assert result == "INJECTED", f"应该返回注入识别器的值 'INJECTED'，但得到 '{result}'"

        # 3. 调用次数正确
        assert mock_recognizer.recognize_from_element_call_count == 1, "识别器应该被调用一次"

    def test_multiple_recognizer_calls_use_same_instance(self):
        """测试多次调用使用同一个识别器实例"""
        mock_page = MockPage()
        mock_context = MockContext()
        mock_recognizer = MockCaptchaRecognizer()

        service = CourtZxfwService(mock_page, mock_context, captcha_recognizer=mock_recognizer)  # type: ignore[arg-type]

        # 多次调用
        service._recognize_captcha(save_debug=False)
        service._recognize_captcha(save_debug=False)
        service._recognize_captcha(save_debug=False)

        # 验证同一个实例被调用了 3 次
        assert mock_recognizer.recognize_from_element_call_count == 3, "识别器应该被调用 3 次"
