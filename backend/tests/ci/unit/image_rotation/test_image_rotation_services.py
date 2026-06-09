"""
Tests for apps.image_rotation.services — 图片旋转、方向检测、重命名
"""

from __future__ import annotations

import base64
import io
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# OrientationDetectionService 测试
# ============================================================


class TestOrientationDetectionService:
    """OrientationDetectionService 测试"""

    def test_detect_orientation_no_ocr(self) -> None:
        from apps.image_rotation.services.orientation.service import OrientationDetectionService

        svc = OrientationDetectionService()
        svc._ocr_service = None
        with patch.object(type(svc), 'ocr_service', new_callable=lambda: property(lambda self: None)):
            result = svc.detect_orientation(b"fake_image_data")
            assert result["rotation"] == 0
            assert result["method"] == "none"

    def test_detect_orientation_with_text_no_ocr(self) -> None:
        from apps.image_rotation.services.orientation.service import OrientationDetectionService

        svc = OrientationDetectionService()
        svc._ocr_service = None
        with patch.object(type(svc), 'ocr_service', new_callable=lambda: property(lambda self: None)):
            result = svc.detect_orientation_with_text(b"fake_image_data")
            assert result["rotation"] == 0
            assert "ocr_text" in result

    def test_detect_orientation_exception(self) -> None:
        from apps.image_rotation.services.orientation.service import OrientationDetectionService

        svc = OrientationDetectionService()
        mock_ocr = MagicMock()
        svc._ocr_service = mock_ocr
        # Invalid image data should cause exception
        result = svc.detect_orientation(b"invalid_image")
        assert result["rotation"] == 0
        assert result["confidence"] == 0

    def test_detect_batch_empty(self) -> None:
        from apps.image_rotation.services.orientation.service import OrientationDetectionService

        svc = OrientationDetectionService()
        svc._ocr_service = None
        with patch.object(type(svc), 'ocr_service', new_callable=lambda: property(lambda self: None)):
            result = svc.detect_batch([])
            assert result == []

    def test_detect_batch_with_data(self) -> None:
        from apps.image_rotation.services.orientation.service import OrientationDetectionService

        svc = OrientationDetectionService()
        svc._ocr_service = None
        with patch.object(type(svc), 'ocr_service', new_callable=lambda: property(lambda self: None)):
            fake_img = base64.b64encode(b"fake_data").decode()
            result = svc.detect_batch([{"data": fake_img, "filename": "test.jpg"}])
            assert len(result) == 1
            assert result[0]["filename"] == "test.jpg"

    def test_detect_batch_exception_handling(self) -> None:
        from apps.image_rotation.services.orientation.service import OrientationDetectionService

        svc = OrientationDetectionService()
        result = svc.detect_batch([{"data": "not_base64!!!", "filename": "bad.jpg"}])
        assert len(result) == 1
        assert result[0]["filename"] == "bad.jpg"
        assert "error" in result[0]


# ============================================================
# Validation 测试
# ============================================================


class TestImageValidation:
    """图片验证测试"""

    def test_decode_base64_payload_simple(self) -> None:
        from apps.image_rotation.services.validation import decode_base64_payload

        data = base64.b64encode(b"hello").decode()
        result = decode_base64_payload(data)
        assert result == b"hello"

    def test_decode_base64_payload_with_prefix(self) -> None:
        from apps.image_rotation.services.validation import decode_base64_payload

        data = "data:image/jpeg;base64," + base64.b64encode(b"hello").decode()
        result = decode_base64_payload(data)
        assert result == b"hello"

    def test_decode_base64_payload_empty(self) -> None:
        from apps.image_rotation.services.validation import decode_base64_payload

        result = decode_base64_payload("")
        assert result == b""

    def test_decode_base64_payload_invalid(self) -> None:
        from apps.image_rotation.services.validation import decode_base64_payload
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException):
            decode_base64_payload("not_valid_base64!!!")

    def test_validate_image_format_valid(self) -> None:
        from apps.image_rotation.services.validation import validate_image_format

        result = validate_image_format(img_format="jpeg", supported_formats={"jpeg", "png"})
        assert result == "jpeg"

    def test_validate_image_format_case_insensitive(self) -> None:
        from apps.image_rotation.services.validation import validate_image_format

        result = validate_image_format(img_format="JPEG", supported_formats={"jpeg"})
        assert result == "jpeg"

    def test_validate_image_format_invalid(self) -> None:
        from apps.image_rotation.services.validation import validate_image_format
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException):
            validate_image_format(img_format="bmp", supported_formats={"jpeg", "png"})

    def test_validate_image_format_default(self) -> None:
        from apps.image_rotation.services.validation import validate_image_format

        result = validate_image_format(img_format="", supported_formats={"jpeg"})
        assert result == "jpeg"

    def test_validate_file_size_ok(self) -> None:
        from apps.image_rotation.services.validation import validate_file_size

        # Should not raise
        validate_file_size(image_bytes=b"x" * 100, max_file_size=1000)

    def test_validate_file_size_exceeded(self) -> None:
        from apps.image_rotation.services.validation import validate_file_size
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException):
            validate_file_size(image_bytes=b"x" * 1000, max_file_size=100)


# ============================================================
# AutoRenameService 测试
# ============================================================


class TestAutoRenameService:
    """AutoRenameService 测试"""

    def _make_service(self, llm_client=None):
        from apps.image_rotation.services.auto_rename_service import AutoRenameService

        return AutoRenameService(ollama_model="test", ollama_base_url="http://test", llm_client=llm_client)

    def test_extract_info_empty_text(self) -> None:
        svc = self._make_service()
        result = svc.extract_info("")
        assert result.date is None
        assert result.amount is None

    def test_extract_info_whitespace_only(self) -> None:
        svc = self._make_service()
        result = svc.extract_info("   ")
        assert result.date is None

    def test_extract_info_with_llm_client(self) -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = '{"date": "20250630", "amount": "65500元", "raw_date": "2025年6月30日", "raw_amount": "65500元"}'
        mock_client.complete.return_value = mock_resp
        svc = self._make_service(llm_client=mock_client)
        result = svc.extract_info("2025年6月30日 费用65500元")
        assert result.date == "20250630"
        assert result.amount == "65500元"

    def test_extract_info_llm_empty_response(self) -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = ""
        mock_client.complete.return_value = mock_resp
        svc = self._make_service(llm_client=mock_client)
        result = svc.extract_info("some text")
        assert result.date is None

    def test_extract_info_llm_exception(self) -> None:
        mock_client = MagicMock()
        mock_client.complete.side_effect = Exception("LLM down")
        svc = self._make_service(llm_client=mock_client)
        result = svc.extract_info("some text")
        assert result.date is None

    def test_parse_extraction_response_valid_json(self) -> None:
        svc = self._make_service()
        result = svc._parse_extraction_response('{"date": "20250630", "amount": "100元"}')
        assert result.date == "20250630"
        assert result.amount == "100元"

    def test_parse_extraction_response_markdown_code_block(self) -> None:
        svc = self._make_service()
        result = svc._parse_extraction_response('```json\n{"date": "20250630", "amount": "100元"}\n```')
        assert result.date == "20250630"

    def test_parse_extraction_response_invalid_json(self) -> None:
        svc = self._make_service()
        result = svc._parse_extraction_response('not json')
        assert result.date is None

    def test_normalize_date_8_digits(self) -> None:
        svc = self._make_service()
        assert svc._normalize_date("20250630") == "20250630"

    def test_normalize_date_6_digits(self) -> None:
        svc = self._make_service()
        result = svc._normalize_date("250630")
        assert result == "20250630"

    def test_normalize_date_with_separators(self) -> None:
        svc = self._make_service()
        assert svc._normalize_date("2025-06-30") == "20250630"

    def test_normalize_date_empty(self) -> None:
        svc = self._make_service()
        assert svc._normalize_date("") is None

    def test_normalize_date_invalid(self) -> None:
        svc = self._make_service()
        assert svc._normalize_date("abc") is None

    def test_extract_json_block_with_code_block(self) -> None:
        svc = self._make_service()
        result = svc._extract_json_block('```json\n{"key": "value"}\n```')
        assert '"key"' in result

    def test_extract_json_block_with_braces(self) -> None:
        svc = self._make_service()
        result = svc._extract_json_block('some text {"key": "value"} more text')
        assert '"key"' in result

    def test_extract_json_block_plain_text(self) -> None:
        svc = self._make_service()
        result = svc._extract_json_block("plain text")
        assert result == "plain text"

    def test_generate_filename_date_and_amount(self) -> None:
        from apps.image_rotation.services.auto_rename_service import ExtractionResult

        svc = self._make_service()
        result = svc.generate_filename("original.jpg", ExtractionResult(date="20250630", amount="65500元"))
        assert result == "20250630_65500元.jpg"

    def test_generate_filename_date_only(self) -> None:
        from apps.image_rotation.services.auto_rename_service import ExtractionResult

        svc = self._make_service()
        result = svc.generate_filename("original.jpg", ExtractionResult(date="20250630"))
        assert result == "20250630.jpg"

    def test_generate_filename_amount_only(self) -> None:
        from apps.image_rotation.services.auto_rename_service import ExtractionResult

        svc = self._make_service()
        result = svc.generate_filename("original.jpg", ExtractionResult(amount="100元"))
        assert result == "100元.jpg"

    def test_generate_filename_nothing(self) -> None:
        from apps.image_rotation.services.auto_rename_service import ExtractionResult

        svc = self._make_service()
        result = svc.generate_filename("original.jpg", ExtractionResult())
        assert result == "original.jpg"

    def test_get_file_extension(self) -> None:
        svc = self._make_service()
        assert svc._get_file_extension("test.jpg") == ".jpg"
        assert svc._get_file_extension("test") == ""
        assert svc._get_file_extension("test.tar.gz") == ".gz"

    def test_suggest_rename_success(self) -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.content = '{"date": "20250630", "amount": "100元", "raw_date": "6月30日", "raw_amount": "100元"}'
        mock_client.complete.return_value = mock_resp
        svc = self._make_service(llm_client=mock_client)
        result = svc.suggest_rename("original.jpg", "2025年6月30日 100元")
        assert result.success is True
        assert "20250630" in result.suggested_filename

    def test_suggest_rename_exception(self) -> None:
        mock_client = MagicMock()
        mock_client.complete.side_effect = Exception("fail")
        svc = self._make_service(llm_client=mock_client)
        result = svc.suggest_rename("original.jpg", "text")
        # extract_info catches exceptions and returns empty ExtractionResult
        # generate_filename returns original filename when nothing extracted
        assert result.original_filename == "original.jpg"
        assert result.date is None

    def test_fallback_regex_extraction(self) -> None:
        svc = self._make_service()
        result = svc._fallback_regex_extraction('"date": "20250630", "amount": "100元"')
        assert result.date == "20250630"
        assert result.amount == "100元"

    def test_fallback_regex_extraction_null_values(self) -> None:
        svc = self._make_service()
        result = svc._fallback_regex_extraction('"date": "null", "amount": "null"')
        assert result.date is None
        assert result.amount is None
