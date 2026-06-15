"""Coverage tests for captcha_recognition_service."""

from __future__ import annotations

import base64
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from apps.automation.services.captcha.captcha_recognition_service import (
    CaptchaRecognitionService,
    CaptchaResult,
    CaptchaServiceAdapter,
    _is_auto_recognize_enabled,
)


def _make_valid_png_base64() -> str:
    """Create a minimal valid PNG image encoded as base64."""
    img = Image.new("RGB", (100, 30), color=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class TestIsAutoRecognizeEnabled:
    def test_enabled(self):
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = "true"
        mock_config_cls = MagicMock(return_value=mock_svc)
        with patch.dict("sys.modules", {"plugins": MagicMock(has_captcha_ocr_plugin=lambda: True)}):
            with patch("apps.core.services.system_config_service.SystemConfigService", mock_config_cls):
                assert _is_auto_recognize_enabled() is True

    def test_plugin_not_installed(self):
        import sys
        old = sys.modules.pop("plugins", None)
        try:
            with patch("apps.core.services.system_config_service.SystemConfigService") as MockConfig:
                MockConfig.return_value.get_value.return_value = "false"
                assert _is_auto_recognize_enabled() is False
        finally:
            if old is not None:
                sys.modules["plugins"] = old

    def test_config_false(self):
        mock_svc = MagicMock()
        mock_svc.get_value.return_value = "false"
        mock_config_cls = MagicMock(return_value=mock_svc)
        with patch.dict("sys.modules", {"plugins": MagicMock(has_captcha_ocr_plugin=lambda: True)}):
            with patch("apps.core.services.system_config_service.SystemConfigService", mock_config_cls):
                assert _is_auto_recognize_enabled() is False


class TestCaptchaRecognitionServiceInit:
    def test_defaults(self):
        svc = CaptchaRecognitionService()
        assert svc.MAX_FILE_SIZE == 5 * 1024 * 1024
        assert "PNG" in svc.SUPPORTED_FORMATS

    def test_custom_config(self):
        svc = CaptchaRecognitionService(config={"max_file_size": 1000, "supported_formats": {"JPEG"}})
        assert svc.MAX_FILE_SIZE == 1000
        assert {"JPEG"} == svc.SUPPORTED_FORMATS


class TestRecognizerProperty:
    def test_injected_recognizer(self):
        rec = MagicMock()
        svc = CaptchaRecognitionService(recognizer=rec)
        assert svc.recognizer is rec


class TestDecodeBase64Image:
    def test_valid_base64(self):
        svc = CaptchaRecognitionService()
        data = base64.b64encode(b"hello").decode()
        with patch("apps.automation.utils.logging.AutomationLogger"):
            result = svc._decode_base64_image(data)
            assert result == b"hello"

    def test_with_data_url_prefix(self):
        svc = CaptchaRecognitionService()
        data = base64.b64encode(b"image_data").decode()
        with patch("apps.automation.utils.logging.AutomationLogger"):
            result = svc._decode_base64_image(f"data:image/png;base64,{data}")
            assert result == b"image_data"

    def test_invalid_base64(self):
        svc = CaptchaRecognitionService()
        with pytest.raises(ValueError, match="无效的 Base64 编码"):
            svc._decode_base64_image("not_valid_base64!!!")


class TestValidateImageSize:
    def test_valid_size(self):
        svc = CaptchaRecognitionService()
        svc._validate_image_size(b"x" * 100)  # no raise

    def test_too_large(self):
        svc = CaptchaRecognitionService(config={"max_file_size": 100})
        with pytest.raises(ValueError, match="超过"):
            svc._validate_image_size(b"x" * 200)


class TestValidateImageFormat:
    def test_valid_png(self):
        svc = CaptchaRecognitionService()
        img = Image.new("RGB", (10, 10), color=(255, 255, 255))
        buf = BytesIO()
        img.save(buf, format="PNG")
        svc._validate_image_format(buf.getvalue())  # no raise

    def test_invalid_format(self):
        svc = CaptchaRecognitionService(config={"supported_formats": {"PNG"}})
        # Create a BMP image but only allow PNG
        img = Image.new("RGB", (10, 10), color=(255, 255, 255))
        buf = BytesIO()
        img.save(buf, format="BMP")
        with pytest.raises(ValueError, match="不支持"):
            svc._validate_image_format(buf.getvalue())

    def test_corrupt_image(self):
        svc = CaptchaRecognitionService()
        with pytest.raises(ValueError, match="无法识别"):
            svc._validate_image_format(b"not_an_image")


class TestRecognizeFromBase64:
    def test_empty_input(self):
        svc = CaptchaRecognitionService()
        result = svc.recognize_from_base64("")
        assert result.success is False
        assert "不能为空" in result.error

    def test_whitespace_input(self):
        svc = CaptchaRecognitionService()
        result = svc.recognize_from_base64("   ")
        assert result.success is False

    @patch("apps.automation.services.captcha.captcha_recognition_service._is_auto_recognize_enabled", return_value=False)
    def test_auto_recognize_disabled(self, _mock):
        svc = CaptchaRecognitionService()
        result = svc.recognize_from_base64(_make_valid_png_base64())
        assert result.success is False
        assert "已关闭" in result.error

    @patch("apps.automation.services.captcha.captcha_recognition_service._is_auto_recognize_enabled", return_value=True)
    def test_decode_failure(self, _mock):
        svc = CaptchaRecognitionService()
        result = svc.recognize_from_base64("invalid_base64!!!")
        assert result.success is False

    @patch("apps.automation.services.captcha.captcha_recognition_service._is_auto_recognize_enabled", return_value=True)
    def test_size_exceeded(self, _mock):
        svc = CaptchaRecognitionService(config={"max_file_size": 10})
        result = svc.recognize_from_base64(_make_valid_png_base64())
        assert result.success is False

    @patch("apps.automation.services.captcha.captcha_recognition_service._is_auto_recognize_enabled", return_value=True)
    def test_successful_recognition(self, _mock):
        svc = CaptchaRecognitionService()
        mock_rec = MagicMock()
        mock_rec.recognize.return_value = "ABCD"
        svc._recognizer = mock_rec
        with patch("apps.automation.utils.logging.AutomationLogger"):
            result = svc.recognize_from_base64(_make_valid_png_base64())
            assert result.success is True
            assert result.text == "ABCD"

    @patch("apps.automation.services.captcha.captcha_recognition_service._is_auto_recognize_enabled", return_value=True)
    def test_recognition_returns_empty(self, _mock):
        svc = CaptchaRecognitionService()
        mock_rec = MagicMock()
        mock_rec.recognize.return_value = ""
        svc._recognizer = mock_rec
        with patch("apps.automation.utils.logging.AutomationLogger"):
            result = svc.recognize_from_base64(_make_valid_png_base64())
            assert result.success is False
            assert "无法识别" in result.error


class TestCaptchaServiceAdapter:
    def test_init_defaults(self):
        adapter = CaptchaServiceAdapter()
        assert adapter._service is None

    def test_init_with_service(self):
        svc = MagicMock()
        adapter = CaptchaServiceAdapter(service=svc)
        assert adapter._service is svc

    def test_service_property(self):
        adapter = CaptchaServiceAdapter()
        with patch.object(CaptchaRecognitionService, "__init__", return_value=None):
            svc = adapter.service
            assert isinstance(svc, CaptchaRecognitionService)

    def test_recognize_success(self):
        svc = MagicMock()
        adapter = CaptchaServiceAdapter(service=svc)
        result = MagicMock()
        result.success = True
        result.text = "ABCD"
        svc.recognize_from_base64.return_value = result
        # recognize_internal calls recognize_from_base64 with base64 encoded data
        with patch.object(adapter, "recognize_internal", return_value="ABCD"):
            text = adapter.recognize(b"image_data")
            assert text == "ABCD"

    def test_recognize_internal_success(self):
        svc = MagicMock()
        adapter = CaptchaServiceAdapter(service=svc)
        result = MagicMock()
        result.success = True
        result.text = "XYZ"
        svc.recognize_from_base64.return_value = result
        text = adapter.recognize_internal(b"image_data")
        assert text == "XYZ"

    def test_recognize_internal_failure(self):
        from apps.core.exceptions import ValidationException

        svc = MagicMock()
        adapter = CaptchaServiceAdapter(service=svc)
        result = MagicMock()
        result.success = False
        result.text = None
        result.error = "识别失败"
        result.processing_time = 1.0
        svc.recognize_from_base64.return_value = result
        with pytest.raises(ValidationException, match="验证码识别失败"):
            adapter.recognize_internal(b"image_data")

    def test_recognize_from_base64_delegates(self):
        svc = MagicMock()
        adapter = CaptchaServiceAdapter(service=svc)
        expected = MagicMock()
        svc.recognize_from_base64.return_value = expected
        result = adapter.recognize_from_base64("base64data")
        assert result is expected
