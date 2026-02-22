"""
验证码识别 API 属性测试

使用 Hypothesis 进行属性测试，验证 API 的正确性属性。
"""

import base64
from io import BytesIO

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from PIL import Image

from apps.automation.schemas import CaptchaRecognizeOut
from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService


class TestCaptchaRecognitionProperties:
    """验证码识别 API 属性测试"""

    @pytest.fixture
    def service(self):
        """创建服务实例"""
        return CaptchaRecognitionService()

    # ========================================================================
    # Property 1 & 2: Valid/Invalid Base64 handling
    # ========================================================================

    @given(st.binary(min_size=1, max_size=1000))
    @settings(max_examples=100, deadline=None)
    def test_property_1_2_valid_base64_returns_response(self, image_bytes):
        """
        **Feature: captcha-recognition-api, Property 1: Valid Base64 images return recognition results**
        **Feature: captcha-recognition-api, Property 2: Invalid input returns error response**

        属性测试：对于任何 Base64 编码的数据（有效或无效），
        API 应该返回一个响应对象，包含 success 字段，并且不抛出未捕获的异常。

        **Validates: Requirements 1.1, 1.2, 2.1, 2.2**
        """
        service = CaptchaRecognitionService()

        # 将字节数据编码为 Base64
        base64_str = base64.b64encode(image_bytes).decode("utf-8")

        try:
            # 调用识别服务
            result = service.recognize_from_base64(base64_str)

            # 验证返回类型
            assert isinstance(result, CaptchaRecognizeOut), (
                f"返回值应该是 CaptchaRecognizeOut 类型，但得到 {type(result)}"
            )

            # 验证必须包含 success 字段
            assert hasattr(result, "success"), "响应必须包含 success 字段"
            assert isinstance(result.success, bool), "success 字段必须是布尔值"

            # 验证必须包含 processing_time 字段
            assert hasattr(result, "processing_time"), "响应必须包含 processing_time 字段"

            # 如果成功，text 应该是字符串；如果失败，error 应该是字符串
            if result.success:
                assert result.text is None or isinstance(result.text, str), "成功时 text 应该是 None 或字符串"
            else:
                assert result.error is None or isinstance(result.error, str), "失败时 error 应该是 None 或字符串"

        except Exception as e:
            # 不应该抛出任何未捕获的异常
            pytest.fail(f"API 不应该抛出未捕获的异常，但抛出了 {type(e).__name__}: {e}")

    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=100, deadline=None)
    def test_property_2_invalid_base64_returns_error(self, invalid_text):
        """
        **Feature: captcha-recognition-api, Property 2: Invalid input returns error response**

        属性测试：对于任何无效的 Base64 字符串，
        API 应该返回 success=False 和描述性的错误消息。

        **Validates: Requirements 1.2**
        """
        service = CaptchaRecognitionService()

        # 过滤掉可能是有效 Base64 的字符串
        # Base64 只包含 A-Z, a-z, 0-9, +, /, =
        valid_base64_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
        if all(c in valid_base64_chars for c in invalid_text):
            # 这可能是有效的 Base64，跳过
            assume(False)

        try:
            result = service.recognize_from_base64(invalid_text)

            # 验证返回类型
            assert isinstance(result, CaptchaRecognizeOut), "返回值应该是 CaptchaRecognizeOut 类型"

            # 对于无效输入，应该返回失败
            assert result.success is False, f"无效输入应该返回 success=False，但得到 {result.success}"

            # 应该包含错误消息
            assert result.error is not None, "失败响应应该包含错误消息"
            assert isinstance(result.error, str), "错误消息应该是字符串"
            assert len(result.error) > 0, "错误消息不应该为空"

        except Exception as e:
            pytest.fail(f"API 不应该抛出未捕获的异常，但抛出了 {type(e).__name__}: {e}")

    def test_property_2_empty_input_returns_error(self, service):
        """
        **Feature: captcha-recognition-api, Property 2: Invalid input returns error response**

        测试空输入返回错误响应

        **Validates: Requirements 1.2**
        """
        # 测试空字符串
        result = service.recognize_from_base64("")
        assert result.success is False
        assert result.error is not None
        assert "空" in result.error or "不能为空" in result.error

        # 测试只有空白字符
        result = service.recognize_from_base64("   ")
        assert result.success is False
        assert result.error is not None

    # ========================================================================
    # Property 3 & 4: Response field requirements
    # ========================================================================

    def test_property_3_success_response_contains_required_fields(self, service):
        """
        **Feature: captcha-recognition-api, Property 3: Success response contains required fields**

        属性测试：对于成功的识别（模拟），响应应该包含所有必需字段。

        **Validates: Requirements 1.3, 3.2, 3.4**
        """
        # 创建一个简单的验证码图片
        img = Image.new("RGB", (100, 30), color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()
        base64_str = base64.b64encode(image_bytes).decode("utf-8")

        result = service.recognize_from_base64(base64_str)

        # 验证响应类型
        assert isinstance(result, CaptchaRecognizeOut)

        # 验证必需字段存在
        assert hasattr(result, "success"), "响应必须包含 success 字段"
        assert hasattr(result, "text"), "响应必须包含 text 字段"
        assert hasattr(result, "processing_time"), "响应必须包含 processing_time 字段"
        assert hasattr(result, "error"), "响应必须包含 error 字段"

        # 验证字段类型
        assert isinstance(result.success, bool), "success 必须是布尔值"
        assert result.processing_time is None or isinstance(result.processing_time, (int, float)), (
            "processing_time 必须是数字或 None"
        )

        # 如果成功，验证成功响应的字段
        if result.success:
            assert result.text is None or isinstance(result.text, str), "成功时 text 应该是字符串或 None"
            assert result.processing_time is not None, "成功时 processing_time 不应该为 None"
            assert result.processing_time >= 0, "processing_time 应该是非负数"

    def test_property_4_failure_response_contains_required_fields(self, service):
        """
        **Feature: captcha-recognition-api, Property 4: Failure response contains required fields**

        属性测试：对于失败的识别，响应应该包含所有必需字段。

        **Validates: Requirements 1.4, 3.3, 3.4**
        """
        # 使用无效的 Base64 触发失败
        result = service.recognize_from_base64("invalid_base64_!@#$")

        # 验证响应类型
        assert isinstance(result, CaptchaRecognizeOut)

        # 验证失败响应
        assert result.success is False, "应该返回失败状态"

        # 验证必需字段存在
        assert hasattr(result, "text"), "响应必须包含 text 字段"
        assert hasattr(result, "error"), "响应必须包含 error 字段"
        assert hasattr(result, "processing_time"), "响应必须包含 processing_time 字段"

        # 验证失败响应的字段值
        assert result.text is None, "失败时 text 应该为 None"
        assert result.error is not None, "失败时 error 不应该为 None"
        assert isinstance(result.error, str), "error 应该是字符串"
        assert len(result.error) > 0, "error 不应该为空字符串"
        assert result.processing_time is not None, "processing_time 不应该为 None"
        assert result.processing_time >= 0, "processing_time 应该是非负数"

    # ========================================================================
    # Property 5: Multiple image formats support
    # ========================================================================

    @given(st.sampled_from(["PNG", "JPEG", "GIF", "BMP"]))
    @settings(max_examples=100, deadline=None)
    def test_property_5_multiple_formats_supported(self, image_format):
        """
        **Feature: captcha-recognition-api, Property 5: Multiple image formats are supported**

        属性测试：对于任何支持的图片格式（PNG, JPEG, GIF, BMP），
        API 应该能够处理而不返回格式相关的错误。

        **Validates: Requirements 1.5**
        """
        service = CaptchaRecognitionService()

        # 创建指定格式的图片
        img = Image.new("RGB", (100, 30), color="white")
        buffer = BytesIO()

        # 保存为指定格式
        img.save(buffer, format=image_format)
        image_bytes = buffer.getvalue()
        base64_str = base64.b64encode(image_bytes).decode("utf-8")

        try:
            result = service.recognize_from_base64(base64_str)

            # 验证返回类型
            assert isinstance(result, CaptchaRecognizeOut)

            # 不应该有格式相关的错误
            if not result.success and result.error:
                assert "格式" not in result.error or "支持" in result.error, (
                    f"支持的格式 {image_format} 不应该返回格式错误: {result.error}"
                )
                # 如果失败，应该是识别失败，而不是格式问题
                assert "不支持" not in result.error.lower(), f"支持的格式 {image_format} 不应该被拒绝: {result.error}"

        except Exception as e:
            pytest.fail(f"处理 {image_format} 格式时不应该抛出异常: {type(e).__name__}: {e}")

    def test_property_5_unsupported_format_rejected(self, service):
        """
        **Feature: captcha-recognition-api, Property 5: Multiple image formats are supported**

        测试不支持的格式被正确拒绝

        **Validates: Requirements 1.5**
        """
        # 创建一个 TIFF 格式的图片（不支持）
        img = Image.new("RGB", (100, 30), color="white")
        buffer = BytesIO()
        img.save(buffer, format="TIFF")
        image_bytes = buffer.getvalue()
        base64_str = base64.b64encode(image_bytes).decode("utf-8")

        result = service.recognize_from_base64(base64_str)

        # 应该返回失败
        assert result.success is False
        assert result.error is not None
        # 错误消息应该提到格式问题
        assert "格式" in result.error or "支持" in result.error

    # ========================================================================
    # Property 6: Response schema consistency
    # ========================================================================

    @given(st.binary(min_size=10, max_size=500))
    @settings(max_examples=100, deadline=None)
    def test_property_6_response_schema_consistent(self, image_bytes):
        """
        **Feature: captcha-recognition-api, Property 6: Response schema is consistent**

        属性测试：对于任何输入，API 响应都应该符合 CaptchaRecognizeOut Schema，
        所有必需字段都存在且类型正确。

        **Validates: Requirements 3.1**
        """
        service = CaptchaRecognitionService()

        # 编码为 Base64
        base64_str = base64.b64encode(image_bytes).decode("utf-8")

        try:
            result = service.recognize_from_base64(base64_str)

            # 验证返回类型
            assert isinstance(result, CaptchaRecognizeOut), (
                f"返回值必须是 CaptchaRecognizeOut 类型，但得到 {type(result)}"
            )

            # 验证所有必需字段存在
            required_fields = ["success", "text", "processing_time", "error"]
            for field in required_fields:
                assert hasattr(result, field), f"响应必须包含 {field} 字段"

            # 验证字段类型
            assert isinstance(result.success, bool), f"success 必须是布尔值，但得到 {type(result.success)}"

            assert result.text is None or isinstance(result.text, str), (
                f"text 必须是 None 或字符串，但得到 {type(result.text)}"
            )

            assert result.error is None or isinstance(result.error, str), (
                f"error 必须是 None 或字符串，但得到 {type(result.error)}"
            )

            assert result.processing_time is None or isinstance(result.processing_time, (int, float)), (
                f"processing_time 必须是 None 或数字，但得到 {type(result.processing_time)}"
            )

            # 验证逻辑一致性
            if result.success:
                # 成功时，text 可能有值，error 应该为 None
                assert result.error is None, "成功时 error 应该为 None"
            else:
                # 失败时，text 应该为 None，error 应该有值
                assert result.text is None, "失败时 text 应该为 None"
                assert result.error is not None, "失败时 error 不应该为 None"

        except Exception as e:
            pytest.fail(f"API 不应该抛出未捕获的异常: {type(e).__name__}: {e}")

    # ========================================================================
    # Property 7: File size limit enforcement
    # ========================================================================

    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=100, deadline=None)
    def test_property_7_file_size_limit_enforced(self, size_mb):
        """
        **Feature: captcha-recognition-api, Property 7: File size limit is enforced**

        属性测试：对于不同大小的图片，API 应该正确执行 5MB 的大小限制。

        **Validates: Requirements 6.2, 6.3**
        """
        service = CaptchaRecognitionService()

        # 创建指定大小的图片数据
        # 注意：Base64 编码会增加约 33% 的大小
        target_size = size_mb * 1024 * 1024

        # 创建接近目标大小的数据
        # 使用简单的重复数据来控制大小
        image_data = b"\x89PNG\r\n\x1a\n" + b"x" * (target_size - 8)
        base64_str = base64.b64encode(image_data).decode("utf-8")

        result = service.recognize_from_base64(base64_str)

        # 验证返回类型
        assert isinstance(result, CaptchaRecognizeOut)

        # 验证大小限制逻辑
        if size_mb > 5:
            # 超过 5MB 应该被拒绝
            assert result.success is False, f"超过 5MB 的图片应该被拒绝，但 {size_mb}MB 的图片被接受了"
            assert result.error is not None, "应该返回错误消息"
            assert "5MB" in result.error or "大小" in result.error or "限制" in result.error, (
                f"错误消息应该提到大小限制: {result.error}"
            )
        # 注意：小于 5MB 的可能因为其他原因失败（如格式无效），这是正常的

    def test_property_7_exactly_5mb_boundary(self, service):
        """
        **Feature: captcha-recognition-api, Property 7: File size limit is enforced**

        测试恰好 5MB 的边界情况

        **Validates: Requirements 6.2, 6.3**
        """
        # 创建恰好 5MB 的数据
        exactly_5mb = 5 * 1024 * 1024
        image_data = b"\x89PNG\r\n\x1a\n" + b"x" * (exactly_5mb - 8)
        base64_str = base64.b64encode(image_data).decode("utf-8")

        result = service.recognize_from_base64(base64_str)

        # 恰好 5MB 应该被接受（不应该因为大小被拒绝）
        # 但可能因为格式无效而失败
        if not result.success and result.error:
            assert "5MB" not in result.error and "超过" not in result.error, (
                f"恰好 5MB 不应该因为大小被拒绝: {result.error}"
            )

    def test_property_7_over_5mb_rejected(self, service):
        """
        **Feature: captcha-recognition-api, Property 7: File size limit is enforced**

        测试超过 5MB 的图片被拒绝

        **Validates: Requirements 6.2, 6.3**
        """
        # 创建超过 5MB 的数据
        over_5mb = 6 * 1024 * 1024
        image_data = b"\x89PNG\r\n\x1a\n" + b"x" * (over_5mb - 8)
        base64_str = base64.b64encode(image_data).decode("utf-8")

        result = service.recognize_from_base64(base64_str)

        # 应该被拒绝
        assert result.success is False, "超过 5MB 的图片应该被拒绝"
        assert result.error is not None
        assert "5MB" in result.error or "大小" in result.error or "限制" in result.error
