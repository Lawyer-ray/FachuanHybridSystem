"""Tests for captcha recognition service."""

import base64
import time
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

try:
    from plugins import has_court_login_plugin
    _HAS_LOGIN = has_court_login_plugin()
except ImportError:
    _HAS_LOGIN = False

pytestmark = pytest.mark.skipif(not _HAS_LOGIN, reason="court_login plugin not installed")


# ============================================================
# CaptchaResult dataclass
# ============================================================

class TestCaptchaResult:
    def test_success_result(self):
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaResult
        r = CaptchaResult(success=True, text="abc123", processing_time=0.5, error=None)
        assert r.success is True
        assert r.text == "abc123"
        assert r.error is None

    def test_failure_result(self):
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaResult
        r = CaptchaResult(success=False, text=None, processing_time=0.1, error="invalid image")
        assert r.success is False
        assert r.text is None


# ============================================================
# CaptchaRecognitionService._decode_base64_image
# ============================================================

class TestDecodeBase64Image:
    def _make_service(self):
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService
        return CaptchaRecognitionService.__new__(CaptchaRecognitionService)

    def test_decode_plain_base64(self):
        svc = self._make_service()
        data = b"hello image data"
        b64 = base64.b64encode(data).decode()
        result = svc._decode_base64_image(b64)
        assert result == data

    def test_decode_data_url_prefix(self):
        svc = self._make_service()
        data = b"hello image data"
        b64 = "data:image/png;base64," + base64.b64encode(data).decode()
        result = svc._decode_base64_image(b64)
        assert result == data

    def test_decode_strips_whitespace(self):
        svc = self._make_service()
        data = b"hello"
        b64 = "  " + base64.b64encode(data).decode() + "  "
        result = svc._decode_base64_image(b64)
        assert result == data

    def test_decode_invalid_raises(self):
        svc = self._make_service()
        with pytest.raises(ValueError, match="无效的 Base64"):
            svc._decode_base64_image("not-valid-base64!!!")


# ============================================================
# CaptchaRecognitionService._validate_image_size
# ============================================================

class TestValidateImageSize:
    def _make_service(self, max_size=5 * 1024 * 1024):
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService
        svc = CaptchaRecognitionService.__new__(CaptchaRecognitionService)
        svc.MAX_FILE_SIZE = max_size
        return svc

    def test_small_image_passes(self):
        svc = self._make_service()
        svc._validate_image_size(b"x" * 1024)  # 1KB

    def test_oversized_image_raises(self):
        svc = self._make_service(max_size=100)
        with pytest.raises(ValueError, match="5MB"):
            svc._validate_image_size(b"x" * 200)


# ============================================================
# CaptchaRecognitionService._validate_image_format
# ============================================================

class TestValidateImageFormat:
    def _make_service(self):
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService
        svc = CaptchaRecognitionService.__new__(CaptchaRecognitionService)
        svc.SUPPORTED_FORMATS = {"PNG", "JPEG", "GIF", "BMP"}
        return svc

    def test_non_image_raises(self):
        svc = self._make_service()
        with pytest.raises(ValueError, match="无法识别图片格式"):
            svc._validate_image_format(b"not an image at all")

    def test_valid_png_passes(self):
        svc = self._make_service()
        # Minimal PNG header
        png_bytes = (
            b'\x89PNG\r\n\x1a\n'
            b'\x00\x00\x00\rIHDR'
            b'\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x02\x00\x00\x00\x90wS\xde'
            b'\x00\x00\x00\x0cIDATx'
            b'\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05'
            b'\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        svc._validate_image_format(png_bytes)


# ============================================================
# CaptchaRecognitionService.recognize_from_base64
# ============================================================

class TestRecognizeFromBase64:
    def _make_service(self, recognizer=None):
        from apps.automation.services.captcha.captcha_recognition_service import CaptchaRecognitionService
        svc = CaptchaRecognitionService.__new__(CaptchaRecognitionService)
        svc._recognizer = recognizer
        svc._config = {}
        svc.MAX_FILE_SIZE = 5 * 1024 * 1024
        svc.SUPPORTED_FORMATS = {"PNG", "JPEG", "GIF", "BMP"}
        svc.TIMEOUT_WARNING_SECONDS = 5.0
        return svc

    def test_empty_input_returns_failure(self):
        svc = self._make_service()
        result = svc.recognize_from_base64("")
        assert result.success is False
        assert result.error == "图片数据不能为空"

    def test_none_input_returns_failure(self):
        svc = self._make_service()
        result = svc.recognize_from_base64(None)
        assert result.success is False


# ============================================================
# CaptchaServiceAdapter
# ============================================================

class TestCaptchaServiceAdapter:
    def test_recognize_internal_success(self):
        from apps.automation.services.captcha.captcha_recognition_service import (
            CaptchaRecognitionService,
            CaptchaServiceAdapter,
            CaptchaResult,
        )
        mock_service = MagicMock(spec=CaptchaRecognitionService)
        mock_service.recognize_from_base64.return_value = CaptchaResult(
            success=True, text="abc123", processing_time=0.1, error=None
        )
        adapter = CaptchaServiceAdapter(service=mock_service)
        result = adapter.recognize(b"image_data")
        assert result == "abc123"

    def test_recognize_internal_failure_raises(self):
        from apps.automation.services.captcha.captcha_recognition_service import (
            CaptchaRecognitionService,
            CaptchaServiceAdapter,
            CaptchaResult,
        )
        mock_service = MagicMock(spec=CaptchaRecognitionService)
        mock_service.recognize_from_base64.return_value = CaptchaResult(
            success=False, text=None, processing_time=0.1, error="bad image"
        )
        adapter = CaptchaServiceAdapter(service=mock_service)
        from apps.core.exceptions import ValidationException
        with pytest.raises(ValidationException):
            adapter.recognize(b"bad_image")
