"""
测试 CaptchaRecognizer 和 DdddocrRecognizer

**Feature: automation-decoupling, Property 7: Captcha recognition error handling**

验证：对于任何无法识别的图片，当 CaptchaRecognizer 尝试识别时，
应该返回 None 并记录错误，而不是抛出异常。
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.automation.services.scraper.core.captcha_recognizer import DdddocrRecognizer


class TestCaptchaRecognizerErrorHandling:
    """测试验证码识别器的错误处理"""

    @pytest.fixture
    def recognizer(self):
        """创建 DdddocrRecognizer 实例"""
        return DdddocrRecognizer(show_ad=False)

    def test_empty_bytes_returns_none(self, recognizer):
        """测试空字节流返回 None"""
        result = recognizer.recognize(b"")
        assert result is None, "空字节流应该返回 None"

    def test_invalid_image_returns_none(self, recognizer):
        """测试无效图片数据返回 None"""
        result = recognizer.recognize(b"not an image")
        assert result is None, "无效图片数据应该返回 None"

    def test_none_bytes_returns_none(self, recognizer):
        """测试 None 输入返回 None"""
        # 虽然类型提示要求 bytes，但我们测试健壮性
        try:
            result = recognizer.recognize(None)
            # 如果没有抛出异常，应该返回 None
            assert result is None, "None 输入应该返回 None"
        except (TypeError, AttributeError):
            # 如果抛出类型错误，这也是可以接受的
            pass

    @given(st.binary(min_size=1, max_size=100))
    @settings(max_examples=100, deadline=None)
    def test_property_unrecognizable_images_return_none(self, image_bytes):
        """
        **Feature: automation-decoupling, Property 7: Captcha recognition error handling**

        属性测试：对于任何随机字节流（很可能不是有效图片），
        识别器应该返回 None 或字符串，但不应该抛出异常。

        **Validates: Requirements 3.4, 8.2**
        """
        # 在测试内部创建识别器实例
        recognizer = DdddocrRecognizer(show_ad=False)

        try:
            result = recognizer.recognize(image_bytes)
            # 结果应该是 None 或字符串
            assert result is None or isinstance(result, str), f"识别结果应该是 None 或 str，但得到 {type(result)}"
        except Exception as e:
            # 不应该抛出任何异常
            pytest.fail(f"识别器不应该抛出异常，但抛出了 {type(e).__name__}: {e}")

    def test_corrupted_image_data_returns_none(self, recognizer):
        """测试损坏的图片数据返回 None"""
        # 创建一些看起来像图片但实际上损坏的数据
        corrupted_data = b"\x89PNG\r\n\x1a\n" + b"corrupted data"
        result = recognizer.recognize(corrupted_data)
        assert result is None, "损坏的图片数据应该返回 None"

    def test_recognize_from_element_with_invalid_selector(self, recognizer):
        """测试使用无效选择器时返回 None"""

        # 创建一个 mock page 对象
        class MockPage:
            def locator(self, selector):
                raise Exception("Element not found")

        mock_page = MockPage()
        result = recognizer.recognize_from_element(mock_page, "#invalid-selector")
        assert result is None, "无效选择器应该返回 None"


class TestDdddocrRecognizerImplementation:
    """测试 DdddocrRecognizer 的具体实现"""

    def test_recognizer_initialization(self):
        """测试识别器可以正常初始化"""
        recognizer = DdddocrRecognizer(show_ad=False)
        assert recognizer is not None
        assert hasattr(recognizer, "ocr")

    def test_recognizer_has_required_methods(self):
        """测试识别器有必需的方法"""
        recognizer = DdddocrRecognizer(show_ad=False)
        assert hasattr(recognizer, "recognize")
        assert hasattr(recognizer, "recognize_from_element")
        assert callable(recognizer.recognize)
        assert callable(recognizer.recognize_from_element)
