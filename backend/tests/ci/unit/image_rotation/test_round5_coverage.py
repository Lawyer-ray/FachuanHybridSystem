"""Coverage tests for image_rotation: auto_rename_service, job_service, validation, export, storage."""

from __future__ import annotations

import io
import json
import os
import tempfile
import uuid
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path as PyPath

import pytest
from PIL import Image


def _make_test_image(width: int = 100, height: int = 100, color: str = "white", fmt: str = "PNG") -> bytes:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _make_jpeg_image() -> bytes:
    return _make_test_image(fmt="JPEG")


# =========================================================================
# auto_rename_service
# =========================================================================


class TestExtractionResult:
    def test_defaults(self):
        from apps.image_rotation.services.auto_rename_service import ExtractionResult

        r = ExtractionResult()
        assert r.date is None
        assert r.amount is None
        assert r.raw_date is None
        assert r.raw_amount is None

    def test_with_values(self):
        from apps.image_rotation.services.auto_rename_service import ExtractionResult

        r = ExtractionResult(date="20250630", amount="65500元", raw_date="2025年6月30日", raw_amount="65500元")
        assert r.date == "20250630"
        assert r.amount == "65500元"


class TestRenameSuggestion:
    def test_defaults(self):
        from apps.image_rotation.services.auto_rename_service import RenameSuggestion

        r = RenameSuggestion(original_filename="a.jpg", suggested_filename="b.jpg")
        assert r.success is True
        assert r.error is None

    def test_failure(self):
        from apps.image_rotation.services.auto_rename_service import RenameSuggestion

        r = RenameSuggestion(
            original_filename="a.jpg",
            suggested_filename="a.jpg",
            success=False,
            error="bad",
        )
        assert r.success is False


class TestAutoRenameServiceExtractInfo:
    @patch("apps.core.llm.config.LLMConfig")
    def test_init_defaults(self, mock_config):
        mock_config.get_ollama_model.return_value = "test-model"
        mock_config.get_ollama_base_url.return_value = "http://localhost:11434"
        from apps.image_rotation.services.auto_rename_service import AutoRenameService

        svc = AutoRenameService()
        assert svc._ollama_model == "test-model"
        assert svc._ollama_base_url == "http://localhost:11434"

    def test_init_custom(self):
        from apps.image_rotation.services.auto_rename_service import AutoRenameService

        with patch("apps.core.llm.config.LLMConfig") as mc:
            mc.get_ollama_model.return_value = "m"
            mc.get_ollama_base_url.return_value = "u"
            svc = AutoRenameService(ollama_model="custom", ollama_base_url="http://custom")
            assert svc._ollama_model == "custom"
            assert svc._ollama_base_url == "http://custom"

    def test_extract_info_empty_text(self):
        from apps.image_rotation.services.auto_rename_service import AutoRenameService

        with patch("apps.core.llm.config.LLMConfig") as mc:
            mc.get_ollama_model.return_value = "m"
            mc.get_ollama_base_url.return_value = "u"
            svc = AutoRenameService()
            result = svc.extract_info("")
            assert result.date is None
            assert result.amount is None

    def test_extract_info_whitespace_only(self):
        from apps.image_rotation.services.auto_rename_service import AutoRenameService

        with patch("apps.core.llm.config.LLMConfig") as mc:
            mc.get_ollama_model.return_value = "m"
            mc.get_ollama_base_url.return_value = "u"
            svc = AutoRenameService()
            result = svc.extract_info("   \n\t  ")
            assert result.date is None

    def test_extract_info_with_llm_client(self):
        from apps.image_rotation.services.auto_rename_service import AutoRenameService

        with patch("apps.core.llm.config.LLMConfig") as mc:
            mc.get_ollama_model.return_value = "m"
            mc.get_ollama_base_url.return_value = "u"
            llm_client = MagicMock()
            llm_client.complete.return_value = MagicMock(
                content='{"date": "20250630", "amount": "65500元", "raw_date": null, "raw_amount": null}'
            )
            svc = AutoRenameService(llm_client=llm_client)
            result = svc.extract_info("some ocr text")
            assert result.date == "20250630"
            assert result.amount == "65500元"

    def test_extract_info_llm_returns_empty(self):
        from apps.image_rotation.services.auto_rename_service import AutoRenameService

        with patch("apps.core.llm.config.LLMConfig") as mc:
            mc.get_ollama_model.return_value = "m"
            mc.get_ollama_base_url.return_value = "u"
            llm_client = MagicMock()
            llm_client.complete.return_value = MagicMock(content="")
            svc = AutoRenameService(llm_client=llm_client)
            result = svc.extract_info("some text")
            assert result.date is None

    def test_extract_info_llm_network_error(self):
        from apps.core.llm.exceptions import LLMNetworkError
        from apps.image_rotation.services.auto_rename_service import AutoRenameService

        with patch("apps.core.llm.config.LLMConfig") as mc:
            mc.get_ollama_model.return_value = "m"
            mc.get_ollama_base_url.return_value = "u"
            llm_client = MagicMock()
            llm_client.complete.side_effect = LLMNetworkError("fail")
            svc = AutoRenameService(llm_client=llm_client)
            result = svc.extract_info("text")
            assert result.date is None

    def test_extract_info_llm_timeout_error(self):
        from apps.core.llm.exceptions import LLMTimeoutError
        from apps.image_rotation.services.auto_rename_service import AutoRenameService

        with patch("apps.core.llm.config.LLMConfig") as mc:
            mc.get_ollama_model.return_value = "m"
            mc.get_ollama_base_url.return_value = "u"
            llm_client = MagicMock()
            llm_client.complete.side_effect = LLMTimeoutError("timeout")
            svc = AutoRenameService(llm_client=llm_client)
            result = svc.extract_info("text")
            assert result.date is None

    def test_extract_info_generic_exception(self):
        from apps.image_rotation.services.auto_rename_service import AutoRenameService

        with patch("apps.core.llm.config.LLMConfig") as mc:
            mc.get_ollama_model.return_value = "m"
            mc.get_ollama_base_url.return_value = "u"
            llm_client = MagicMock()
            llm_client.complete.side_effect = RuntimeError("unexpected")
            svc = AutoRenameService(llm_client=llm_client)
            result = svc.extract_info("text")
            assert result.date is None

    def test_extract_info_via_service_locator(self):
        from apps.image_rotation.services.auto_rename_service import AutoRenameService

        with patch("apps.core.llm.config.LLMConfig") as mc:
            mc.get_ollama_model.return_value = "m"
            mc.get_ollama_base_url.return_value = "u"
            svc = AutoRenameService()  # no llm_client
            mock_resp = MagicMock()
            mock_resp.content = '{"date":"20250630","amount":null,"raw_date":null,"raw_amount":null}'
            mock_llm = MagicMock()
            mock_llm.chat.return_value = mock_resp
            with patch("apps.core.interfaces.ServiceLocator") as sl:
                sl.get_llm_service.return_value = mock_llm
                result = svc.extract_info("some text about invoice")
                assert result.date == "20250630"


class TestAutoRenameServiceNormalizeDate:
    @patch("apps.core.llm.config.LLMConfig")
    def _svc(self, mock_config):
        mock_config.get_ollama_model.return_value = "m"
        mock_config.get_ollama_base_url.return_value = "u"
        from apps.image_rotation.services.auto_rename_service import AutoRenameService
        return AutoRenameService()

    def test_empty_date(self):
        svc = self._svc()
        assert svc._normalize_date("") is None
        assert svc._normalize_date(None) is None

    def test_eight_digit(self):
        svc = self._svc()
        assert svc._normalize_date("20250630") == "20250630"

    def test_date_with_separators(self):
        svc = self._svc()
        assert svc._normalize_date("2025-06-30") == "20250630"

    def test_six_digit_recent(self):
        svc = self._svc()
        assert svc._normalize_date("250630") == "20250630"

    def test_six_digit_old(self):
        svc = self._svc()
        assert svc._normalize_date("990630") == "19990630"

    def test_invalid_length(self):
        svc = self._svc()
        assert svc._normalize_date("20250") is None


class TestAutoRenameServiceExtractJsonBlock:
    @patch("apps.core.llm.config.LLMConfig")
    def _svc(self, mock_config):
        mock_config.get_ollama_model.return_value = "m"
        mock_config.get_ollama_base_url.return_value = "u"
        from apps.image_rotation.services.auto_rename_service import AutoRenameService
        return AutoRenameService()

    def test_markdown_json_block(self):
        svc = self._svc()
        text = '```json\n{"key": "value"}\n```'
        result = svc._extract_json_block(text)
        assert '"key"' in result

    def test_markdown_plain_block(self):
        svc = self._svc()
        text = '```\n{"key": "val"}\n```'
        result = svc._extract_json_block(text)
        assert '"key"' in result

    def test_brace_block(self):
        svc = self._svc()
        text = 'Here is the result: {"date": "20250630"} done.'
        result = svc._extract_json_block(text)
        assert '{"date"' in result

    def test_no_json_found(self):
        svc = self._svc()
        text = "no json here"
        result = svc._extract_json_block(text)
        assert result == "no json here"


class TestAutoRenameServiceFallbackRegex:
    @patch("apps.core.llm.config.LLMConfig")
    def _svc(self, mock_config):
        mock_config.get_ollama_model.return_value = "m"
        mock_config.get_ollama_base_url.return_value = "u"
        from apps.image_rotation.services.auto_rename_service import AutoRenameService
        return AutoRenameService()

    def test_valid_json(self):
        svc = self._svc()
        text = '{"date": "20250630", "amount": "65500元", "raw_date": "2025-06-30", "raw_amount": "65500"}'
        result = svc._parse_extraction_response(text)
        assert result.date == "20250630"
        assert result.amount == "65500元"

    def test_invalid_json_fallback(self):
        svc = self._svc()
        text = 'not json, "date": "20250630", "amount": "65500元", "raw_date": "2025-06-30", "raw_amount": "abc"'
        result = svc._parse_extraction_response(text)
        assert result.date == "20250630"
        assert result.amount == "65500元"

    def test_fallback_null_date(self):
        svc = self._svc()
        text = '"date": "null", "amount": "100元", "raw_date": "null", "raw_amount": "100元"'
        result = svc._fallback_regex_extraction(text)
        assert result.date is None
        assert result.amount == "100元"

    def test_fallback_no_raw_amount(self):
        svc = self._svc()
        text = '"date": "20250630", "amount": null, "raw_date": null, "raw_amount": "null"'
        result = svc._fallback_regex_extraction(text)
        assert result.date == "20250630"
        assert result.amount is None
        assert result.raw_amount is None


class TestAutoRenameServiceGenerateFilename:
    @patch("apps.core.llm.config.LLMConfig")
    def _svc(self, mock_config):
        mock_config.get_ollama_model.return_value = "m"
        mock_config.get_ollama_base_url.return_value = "u"
        from apps.image_rotation.services.auto_rename_service import AutoRenameService
        return AutoRenameService()

    def test_date_and_amount(self):
        svc = self._svc()
        from apps.image_rotation.services.auto_rename_service import ExtractionResult
        result = ExtractionResult(date="20250630", amount="65500元")
        name = svc.generate_filename("test.jpg", result)
        assert name == "20250630_65500元.jpg"

    def test_date_only(self):
        svc = self._svc()
        from apps.image_rotation.services.auto_rename_service import ExtractionResult
        result = ExtractionResult(date="20250630")
        name = svc.generate_filename("photo.png", result)
        assert name == "20250630.png"

    def test_amount_only(self):
        svc = self._svc()
        from apps.image_rotation.services.auto_rename_service import ExtractionResult
        result = ExtractionResult(amount="100元")
        name = svc.generate_filename("scan.jpeg", result)
        assert name == "100元.jpeg"

    def test_neither(self):
        svc = self._svc()
        from apps.image_rotation.services.auto_rename_service import ExtractionResult
        result = ExtractionResult()
        name = svc.generate_filename("original.jpg", result)
        assert name == "original.jpg"

    def test_no_extension(self):
        svc = self._svc()
        from apps.image_rotation.services.auto_rename_service import ExtractionResult
        result = ExtractionResult(date="20250101")
        name = svc.generate_filename("noext", result)
        assert name == "20250101"


class TestAutoRenameServiceGetFileExtension:
    @patch("apps.core.llm.config.LLMConfig")
    def _svc(self, mock_config):
        mock_config.get_ollama_model.return_value = "m"
        mock_config.get_ollama_base_url.return_value = "u"
        from apps.image_rotation.services.auto_rename_service import AutoRenameService
        return AutoRenameService()

    def test_with_extension(self):
        svc = self._svc()
        assert svc._get_file_extension("file.jpg") == ".jpg"

    def test_no_extension(self):
        svc = self._svc()
        assert svc._get_file_extension("file") == ""

    def test_multiple_dots(self):
        svc = self._svc()
        assert svc._get_file_extension("archive.tar.gz") == ".gz"


class TestAutoRenameServiceGetOcrChannel:
    @patch("apps.core.llm.config.LLMConfig")
    def _svc(self, mock_config):
        mock_config.get_ollama_model.return_value = "m"
        mock_config.get_ollama_base_url.return_value = "u"
        from apps.image_rotation.services.auto_rename_service import AutoRenameService
        return AutoRenameService()

    def test_cached_channel(self):
        svc = self._svc()
        mock_channel = MagicMock()
        svc._ocr_channel = mock_channel
        assert svc._get_ocr_channel() is mock_channel

    def test_import_success(self):
        svc = self._svc()
        svc._ocr_channel = None
        mock_module = MagicMock()
        mock_module.RenameOCRChannel.return_value = MagicMock()
        with patch.dict("sys.modules", {"apps.image_rotation.services.rename_ocr": mock_module}):
            result = svc._get_ocr_channel()
            assert result is not None

    def test_import_failure(self):
        svc = self._svc()
        svc._ocr_channel = None
        with patch.dict("sys.modules", {"apps.image_rotation.services.rename_ocr": None}):
            result = svc._get_ocr_channel()
            assert result is None


class TestAutoRenameServiceSuggestRename:
    @patch("apps.core.llm.config.LLMConfig")
    def _svc(self, mock_config):
        mock_config.get_ollama_model.return_value = "m"
        mock_config.get_ollama_base_url.return_value = "u"
        from apps.image_rotation.services.auto_rename_service import AutoRenameService
        return AutoRenameService()

    def test_exception_returns_error(self):
        from apps.image_rotation.services.auto_rename_service import RenameSuggestion
        svc = self._svc()
        svc.extract_info = MagicMock(side_effect=RuntimeError("boom"))
        result = svc.suggest_rename("test.jpg", "text")
        assert result.success is False
        assert "boom" in result.error

    def test_success(self):
        from apps.image_rotation.services.auto_rename_service import ExtractionResult, RenameSuggestion
        svc = self._svc()
        er = ExtractionResult(date="20250630", amount=None)
        svc.extract_info = MagicMock(return_value=er)
        svc.generate_filename = MagicMock(return_value="20250630.jpg")
        result = svc.suggest_rename("test.jpg", "some text")
        assert result.success is True
        assert result.suggested_filename == "20250630.jpg"

    def test_with_image_data(self):
        from apps.image_rotation.services.auto_rename_service import ExtractionResult, RenameSuggestion
        svc = self._svc()
        svc._get_ocr_channel = MagicMock(return_value=None)
        er = ExtractionResult(date=None, amount=None)
        svc.extract_info = MagicMock(return_value=er)
        svc.generate_filename = MagicMock(return_value="original.jpg")
        result = svc.suggest_rename_with_image("orig.jpg", "ocr text", b"image bytes", 0)
        assert result.success is True


class TestAutoRenameServiceSuggestRenameBatch:
    @patch("apps.core.llm.config.LLMConfig")
    def _svc(self, mock_config):
        mock_config.get_ollama_model.return_value = "m"
        mock_config.get_ollama_base_url.return_value = "u"
        from apps.image_rotation.services.auto_rename_service import AutoRenameService
        return AutoRenameService()

    def test_batch_with_image_data(self):
        from apps.image_rotation.services.auto_rename_service import RenameSuggestion
        svc = self._svc()
        item = MagicMock()
        item.filename = "test.jpg"
        item.ocr_text = "text"
        item.image_data = b"img"
        item.rotation = 0
        svc.suggest_rename_with_image = MagicMock(return_value=RenameSuggestion(
            original_filename="test.jpg", suggested_filename="new.jpg", success=True
        ))
        result = svc.suggest_rename_batch([item])
        assert len(result) == 1
        svc.suggest_rename_with_image.assert_called_once()

    def test_batch_without_image_data(self):
        from apps.image_rotation.services.auto_rename_service import RenameSuggestion
        svc = self._svc()
        item = MagicMock()
        item.filename = "test.jpg"
        item.ocr_text = "text"
        item.image_data = None
        item.rotation = 0
        svc.suggest_rename = MagicMock(return_value=RenameSuggestion(
            original_filename="test.jpg", suggested_filename="new.jpg"
        ))
        result = svc.suggest_rename_batch([item])
        assert len(result) == 1
        svc.suggest_rename.assert_called_once()

    def test_batch_empty(self):
        svc = self._svc()
        result = svc.suggest_rename_batch([])
        assert result == []


# =========================================================================
# validation
# =========================================================================


class TestDecodeBase64Payload:
    def test_plain_base64(self):
        from apps.image_rotation.services.validation import decode_base64_payload
        import base64
        data = base64.b64encode(b"hello").decode()
        result = decode_base64_payload(data)
        assert result == b"hello"

    def test_data_url_prefix(self):
        from apps.image_rotation.services.validation import decode_base64_payload
        import base64
        encoded = base64.b64encode(b"hello").decode()
        result = decode_base64_payload(f"data:image/png;base64,{encoded}")
        assert result == b"hello"

    def test_empty_string(self):
        from apps.image_rotation.services.validation import decode_base64_payload
        result = decode_base64_payload("")
        assert result == b""

    def test_none_input(self):
        from apps.image_rotation.services.validation import decode_base64_payload
        result = decode_base64_payload(None)
        assert result == b""

    def test_invalid_base64(self):
        from apps.image_rotation.services.validation import decode_base64_payload
        with pytest.raises(Exception):
            decode_base64_payload("!!!invalid!!!")


class TestValidateImageFormat:
    def test_valid_format(self):
        from apps.image_rotation.services.validation import validate_image_format
        result = validate_image_format(img_format="jpeg", supported_formats={"jpeg", "png"})
        assert result == "jpeg"

    def test_uppercase_normalized(self):
        from apps.image_rotation.services.validation import validate_image_format
        result = validate_image_format(img_format="JPEG", supported_formats={"jpeg"})
        assert result == "jpeg"

    def test_default_format(self):
        from apps.image_rotation.services.validation import validate_image_format
        result = validate_image_format(img_format="", supported_formats={"jpeg"})
        assert result == "jpeg"

    def test_invalid_format(self):
        from apps.image_rotation.services.validation import validate_image_format
        with pytest.raises(Exception) as exc_info:
            validate_image_format(img_format="bmp", supported_formats={"jpeg", "png"})
        assert "不支持" in str(exc_info.value)


class TestValidateFileSize:
    def test_ok(self):
        from apps.image_rotation.services.validation import validate_file_size
        validate_file_size(image_bytes=b"x" * 100, max_file_size=1000)

    def test_too_large(self):
        from apps.image_rotation.services.validation import validate_file_size
        with pytest.raises(Exception) as exc_info:
            validate_file_size(image_bytes=b"x" * 200, max_file_size=100)
        assert "超过" in str(exc_info.value)


# =========================================================================
# storage
# =========================================================================


class TestStorage:
    def test_build_zip_filename(self):
        from apps.image_rotation.services.storage import build_zip_filename
        result = build_zip_filename()
        assert result.startswith("rotated_images_")
        assert result.endswith(".zip")

    def test_build_zip_filename_custom_prefix(self):
        from apps.image_rotation.services.storage import build_zip_filename
        result = build_zip_filename(prefix="custom")
        assert result.startswith("custom_")

    def test_build_pdf_filename(self):
        from apps.image_rotation.services.storage import build_pdf_filename
        result = build_pdf_filename()
        assert result.startswith("rotated_pages_")
        assert result.endswith(".pdf")

    def test_build_pdf_filename_custom_prefix(self):
        from apps.image_rotation.services.storage import build_pdf_filename
        result = build_pdf_filename(prefix="myprefix")
        assert result.startswith("myprefix_")

    def test_to_media_url(self):
        from apps.image_rotation.services.storage import to_media_url
        result = to_media_url("test.zip")
        assert result == "/media/image_rotation/test.zip"

    def test_ensure_output_dir_no_media_root(self):
        from apps.image_rotation.services.storage import ensure_output_dir
        with patch("apps.image_rotation.services.storage.Path") as mock_path_cls:
            mock_settings = MagicMock()
            mock_settings.MEDIA_ROOT = None
            with patch("apps.core.utils.path.Path", return_value=mock_path_cls):
                with patch("django.conf.settings", mock_settings):
                    with pytest.raises(RuntimeError, match="MEDIA_ROOT"):
                        ensure_output_dir()


# =========================================================================
# job_service (mocked models, no DB)
# =========================================================================


class TestGuessExt:
    def test_known_extension(self):
        from apps.image_rotation.services.job_service import _guess_ext
        assert _guess_ext("photo.jpg") == ".jpg"
        assert _guess_ext("photo.JPEG") == ".jpeg"
        assert _guess_ext("photo.PNG") == ".png"
        assert _guess_ext("photo.webp") == ".webp"
        assert _guess_ext("photo.tiff") == ".tiff"
        assert _guess_ext("photo.bmp") == ".bmp"
        assert _guess_ext("photo.gif") == ".gif"

    def test_unknown_extension(self):
        from apps.image_rotation.services.job_service import _guess_ext
        assert _guess_ext("file.xyz") == ".jpg"

    def test_no_extension(self):
        from apps.image_rotation.services.job_service import _guess_ext
        assert _guess_ext("noext") == ".jpg"


class TestImageRotationJobService:
    def test_get_job_not_found(self):
        from apps.image_rotation.services.job_service import ImageRotationJobService
        from apps.core.exceptions import NotFoundError
        from apps.image_rotation.models import ImageRotationJob

        with patch.object(ImageRotationJob.objects, "get", side_effect=ImageRotationJob.DoesNotExist()):
            with pytest.raises(NotFoundError):
                ImageRotationJobService.get_job(uuid.uuid4())


# =========================================================================
# export unique filename
# =========================================================================


class TestExportUniqueFilename:
    def test_empty_name(self):
        from apps.image_rotation.services.export.zip_exporter import _get_unique_filename
        result = _get_unique_filename("", {})
        assert result.endswith(".jpg")

    def test_no_ext_conflict(self):
        from apps.image_rotation.services.export.zip_exporter import _get_unique_filename
        used = {"file": 1}
        result = _get_unique_filename("file", used)
        assert result == "file_1"


# =========================================================================
# orientation service (full coverage)
# =========================================================================


class TestOrientationDetectionServiceFull:
    def test_ocr_service_property_lazy_init(self):
        from apps.image_rotation.services.orientation.service import OrientationDetectionService
        svc = OrientationDetectionService()
        with patch("apps.automation.services.ocr.ocr_service.OCRService") as mock_ocr:
            mock_ocr.return_value = MagicMock()
            result = svc.ocr_service
            assert result is not None

    def test_ocr_service_import_error(self):
        from apps.image_rotation.services.orientation.service import OrientationDetectionService
        svc = OrientationDetectionService()
        svc._ocr_service = None
        with patch.dict("sys.modules", {"apps.automation.services.ocr.ocr_service": None}):
            result = svc.ocr_service
            assert result is None

    def test_detect_orientation_with_ocr_success(self):
        from apps.image_rotation.services.orientation.service import OrientationDetectionService
        svc = OrientationDetectionService()
        mock_ocr = MagicMock()
        # Score = text_count * avg_confidence. Need > 10.0 for ocr_voting.
        # 15 texts * 0.9 avg = 13.5
        texts = [f"word{i}" for i in range(15)]
        mock_result = MagicMock()
        mock_result.txts = texts
        mock_result.scores = [0.9] * 15
        mock_ocr.ocr.return_value = mock_result
        svc._ocr_service = mock_ocr
        result = svc.detect_orientation(_make_test_image())
        assert "rotation" in result
        assert "confidence" in result
        assert result["method"] == "ocr_voting"

    def test_detect_orientation_ocr_returns_none(self):
        from apps.image_rotation.services.orientation.service import OrientationDetectionService
        svc = OrientationDetectionService()
        mock_ocr = MagicMock()
        mock_ocr.ocr.return_value = None
        svc._ocr_service = mock_ocr
        result = svc.detect_orientation(_make_test_image())
        assert result["rotation"] == 0

    def test_detect_orientation_low_score(self):
        from apps.image_rotation.services.orientation.service import OrientationDetectionService
        svc = OrientationDetectionService()
        mock_ocr = MagicMock()
        mock_result = MagicMock()
        mock_result.txts = ["x"]
        mock_result.scores = [0.1]
        mock_ocr.ocr.return_value = mock_result
        svc._ocr_service = mock_ocr
        result = svc.detect_orientation(_make_test_image())
        assert result["method"] == "ocr_voting_low_score"

    def test_detect_orientation_with_text_low_score(self):
        from apps.image_rotation.services.orientation.service import OrientationDetectionService
        svc = OrientationDetectionService()
        mock_ocr = MagicMock()
        mock_result = MagicMock()
        mock_result.txts = ["x"]
        mock_result.scores = [0.1]
        mock_ocr.ocr.return_value = mock_result
        svc._ocr_service = mock_ocr
        result = svc.detect_orientation_with_text(_make_test_image())
        assert result["method"] == "ocr_voting_low_score"
        assert "ocr_text" in result

    def test_detect_orientation_with_text_success(self):
        from apps.image_rotation.services.orientation.service import OrientationDetectionService
        svc = OrientationDetectionService()
        mock_ocr = MagicMock()
        texts = [f"word{i}" for i in range(15)]
        mock_result = MagicMock()
        mock_result.txts = texts
        mock_result.scores = [0.9] * 15
        mock_ocr.ocr.return_value = mock_result
        svc._ocr_service = mock_ocr
        result = svc.detect_orientation_with_text(_make_test_image())
        assert result["method"] == "ocr_voting"
        assert "ocr_text" in result

    def test_detect_orientation_exception(self):
        from apps.image_rotation.services.orientation.service import OrientationDetectionService
        svc = OrientationDetectionService()
        mock_ocr = MagicMock()
        mock_ocr.ocr.side_effect = RuntimeError("ocr fail")
        svc._ocr_service = mock_ocr
        result = svc.detect_orientation(b"not an image")
        assert result["rotation"] == 0
        assert result["method"] == "none"

    def test_detect_orientation_with_text_exception(self):
        from apps.image_rotation.services.orientation.service import OrientationDetectionService
        svc = OrientationDetectionService()
        mock_ocr = MagicMock()
        mock_ocr.ocr.side_effect = RuntimeError("fail")
        svc._ocr_service = mock_ocr
        result = svc.detect_orientation_with_text(b"bad data")
        assert result["rotation"] == 0
        assert "ocr_text" in result

    def test_detect_batch_multiple(self):
        from apps.image_rotation.services.orientation.service import OrientationDetectionService
        import base64
        svc = OrientationDetectionService()
        svc._ocr_service = None
        img_b64 = base64.b64encode(_make_test_image()).decode()
        results = svc.detect_batch([
            {"filename": "a.png", "data": img_b64},
            {"filename": "b.png", "data": f"data:image/png;base64,{img_b64}"},
        ])
        assert len(results) == 2
        assert results[0]["filename"] == "a.png"

    def test_detect_batch_exception(self):
        from apps.image_rotation.services.orientation.service import OrientationDetectionService
        svc = OrientationDetectionService()
        svc._ocr_service = None
        results = svc.detect_batch([{"filename": "bad.png", "data": "!!!invalid!!!"}])
        assert len(results) == 1
        assert results[0]["rotation"] == 0


# =========================================================================
# facade full coverage
# =========================================================================


class TestImageRotationServiceFull:
    def test_export_images_success(self):
        from apps.image_rotation.services.facade import ImageRotationService
        svc = ImageRotationService()
        img_b64 = __import__("base64").b64encode(_make_test_image()).decode()
        images = [{"filename": "test.jpg", "data": img_b64, "format": "jpeg", "rotation": 0}]
        with patch.object(svc, "_get_output_dir") as mock_dir, \
             patch("apps.image_rotation.services.facade.generate_zip") as mock_zip:
            mock_dir.return_value = PyPath("/tmp/test")
            mock_zip.return_value = "/media/test.zip"
            result = svc.export_images(images)
            assert result["success"] is True

    def test_export_images_all_fail(self):
        from apps.image_rotation.services.facade import ImageRotationService
        svc = ImageRotationService()
        images = [{"filename": "bad.jpg", "data": "!!!", "format": "jpeg"}]
        with patch("apps.image_rotation.services.facade.logger"):
            result = svc.export_images(images)
            assert result["success"] is False

    def test_export_images_zip_error(self):
        from apps.image_rotation.services.facade import ImageRotationService
        from apps.core.exceptions import ValidationException
        svc = ImageRotationService()
        img_b64 = __import__("base64").b64encode(_make_test_image()).decode()
        images = [{"filename": "test.jpg", "data": img_b64, "format": "jpeg", "rotation": 0}]
        with patch.object(svc, "_get_output_dir") as mock_dir, \
             patch("apps.image_rotation.services.facade.generate_zip", side_effect=RuntimeError("zip fail")):
            mock_dir.return_value = PyPath("/tmp/test")
            result = svc.export_images(images)
            assert result["success"] is False
            assert "ZIP 生成失败" in result["message"]

    def test_export_as_pdf_success(self):
        from apps.image_rotation.services.facade import ImageRotationService
        svc = ImageRotationService()
        img_b64 = __import__("base64").b64encode(_make_test_image()).decode()
        pages = [{"data": img_b64, "rotation": 0}]
        with patch.object(svc, "_get_output_dir") as mock_dir, \
             patch("apps.image_rotation.services.facade.generate_pdf") as mock_pdf:
            mock_dir.return_value = PyPath("/tmp/test")
            mock_pdf.return_value = "/media/test.pdf"
            result = svc.export_as_pdf(pages)
            assert result["success"] is True

    def test_export_as_pdf_all_fail(self):
        from apps.image_rotation.services.facade import ImageRotationService
        svc = ImageRotationService()
        pages = [{"data": "!!!", "rotation": 0}]
        with patch("apps.image_rotation.services.facade.logger"):
            result = svc.export_as_pdf(pages)
            assert result["success"] is False

    def test_export_as_pdf_error(self):
        from apps.image_rotation.services.facade import ImageRotationService
        svc = ImageRotationService()
        img_b64 = __import__("base64").b64encode(_make_test_image()).decode()
        pages = [{"data": img_b64, "rotation": 0}]
        with patch.object(svc, "_get_output_dir") as mock_dir, \
             patch("apps.image_rotation.services.facade.generate_pdf", side_effect=RuntimeError("pdf err")):
            mock_dir.return_value = PyPath("/tmp/test")
            result = svc.export_as_pdf(pages)
            assert result["success"] is False
            assert "PDF 生成失败" in result["message"]

    def test_process_single_image_with_rotation(self):
        from apps.image_rotation.services.facade import ImageRotationService
        svc = ImageRotationService()
        img_b64 = __import__("base64").b64encode(_make_test_image()).decode()
        item = {"filename": "rot.jpg", "data": img_b64, "format": "jpeg", "rotation": 90}
        result = svc._process_single_image(item, "original")
        assert result is not None
        assert result[0] == "rot.jpg"

    def test_process_single_image_paper_size(self):
        from apps.image_rotation.services.facade import ImageRotationService
        svc = ImageRotationService()
        img_b64 = __import__("base64").b64encode(_make_test_image()).decode()
        item = {"filename": "a4.jpg", "data": img_b64, "format": "jpeg"}
        result = svc._process_single_image(item, "a4")
        assert result is not None

    def test_process_page_for_pdf_with_paper_size(self):
        from apps.image_rotation.services.facade import ImageRotationService
        svc = ImageRotationService()
        img_b64 = __import__("base64").b64encode(_make_test_image()).decode()
        result = svc._process_page_for_pdf({"data": img_b64, "rotation": 90}, "a4")
        assert result is not None

    def test_process_all_images_with_rename(self):
        from apps.image_rotation.services.facade import ImageRotationService
        svc = ImageRotationService()
        img_b64 = __import__("base64").b64encode(_make_test_image()).decode()
        images = [{"filename": "test.jpg", "data": img_b64, "format": "jpeg", "rotation": 0}]
        rename_map = {"test.jpg": "renamed.jpg"}
        processed, errors = svc._process_all_images(images, "original", rename_map)
        assert len(processed) == 1
        assert processed[0][0] == "renamed.jpg"

    def test_process_all_images_validation_error(self):
        from apps.image_rotation.services.facade import ImageRotationService
        svc = ImageRotationService()
        images = [{"filename": "bad.png", "data": "!!!", "format": "bmp"}]
        with patch("apps.image_rotation.services.facade.logger"):
            processed, errors = svc._process_all_images(images, "original", None)
            assert len(errors) > 0


# =========================================================================
# pdf_transform full coverage
# =========================================================================


class TestPdfTransformFull:
    def test_apply_rotation_0_png(self):
        from apps.image_rotation.services.transform.pdf_transform import apply_rotation_for_pdf
        img = Image.new("RGB", (100, 100), "green")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        result = apply_rotation_for_pdf(buf.getvalue(), 0)
        assert isinstance(result, bytes)

    def test_apply_rotation_270(self):
        from apps.image_rotation.services.transform.pdf_transform import apply_rotation_for_pdf
        img = Image.new("RGB", (100, 100), "blue")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        result = apply_rotation_for_pdf(buf.getvalue(), 270)
        assert isinstance(result, bytes)

    def test_ensure_rgb_p_mode(self):
        from apps.image_rotation.services.transform.pdf_transform import _ensure_rgb
        img = Image.new("P", (50, 50))
        result = _ensure_rgb(img)
        assert result.mode == "RGB"

    def test_ensure_rgb_l_mode(self):
        from apps.image_rotation.services.transform.pdf_transform import _ensure_rgb
        img = Image.new("L", (50, 50))
        result = _ensure_rgb(img)
        assert result.mode == "RGB"

    def test_apply_rotation_exception_returns_original(self):
        from apps.image_rotation.services.transform.pdf_transform import apply_rotation_for_pdf
        result = apply_rotation_for_pdf(b"not an image at all!!!", 90)
        assert result == b"not an image at all!!!"

    def test_apply_rotation_0_exception(self):
        from apps.image_rotation.services.transform.pdf_transform import apply_rotation_for_pdf
        # JPEG format will pass through quickly, but test exception in _ensure_rgb path
        with patch("apps.image_rotation.services.transform.pdf_transform.Image.open", side_effect=RuntimeError("bad")):
            result = apply_rotation_for_pdf(b"data", 0)
            assert result == b"data"


# =========================================================================
# image_transform full coverage
# =========================================================================


class TestImageTransformFull:
    def test_remove_exif_orientation_rgba(self):
        from apps.image_rotation.services.transform.image_transform import remove_exif_orientation
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
        exif = img.getexif()
        exif[0x0112] = 3  # rotated
        img.info["exif"] = exif.tobytes()
        result = remove_exif_orientation(img, exif_orientation_tag=0x0112)
        assert result is not None

    def test_remove_exif_orientation_exception(self):
        from apps.image_rotation.services.transform.image_transform import remove_exif_orientation
        img = MagicMock()
        img.getexif.side_effect = RuntimeError("exif fail")
        result = remove_exif_orientation(img, exif_orientation_tag=0x0112)
        assert result is img  # returns original on exception

    def test_clean_image_jpeg_with_exif(self):
        from apps.image_rotation.services.transform.image_transform import clean_image
        img = Image.new("RGB", (100, 100))
        exif = img.getexif()
        exif[0x0112] = 6  # rotated
        img.info["exif"] = exif.tobytes()
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        result = clean_image(buf.getvalue(), img_format="jpeg", exif_orientation_tag=0x0112)
        assert isinstance(result, bytes)

    def test_clean_image_png_p_mode(self):
        from apps.image_rotation.services.transform.image_transform import clean_image
        img = Image.new("P", (50, 50))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        # Need to save as JPEG to trigger JPEG path
        result = clean_image(buf.getvalue(), img_format="jpeg", exif_orientation_tag=0x0112)
        assert isinstance(result, bytes)

    def test_clean_image_jpeg_grayscale(self):
        from apps.image_rotation.services.transform.image_transform import clean_image
        img = Image.new("L", (50, 50))  # grayscale
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        result = clean_image(buf.getvalue(), img_format="jpeg", exif_orientation_tag=0x0112)
        assert isinstance(result, bytes)

    def test_rotate_image_for_output_jpeg_rgba(self):
        from apps.image_rotation.services.transform.image_transform import rotate_image_for_output
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        result = rotate_image_for_output(buf.getvalue(), rotation=90, img_format="jpeg")
        assert isinstance(result, bytes)

    def test_rotate_image_for_output_jpeg_p_mode(self):
        from apps.image_rotation.services.transform.image_transform import rotate_image_for_output
        img = Image.new("P", (100, 100))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        result = rotate_image_for_output(buf.getvalue(), rotation=90, img_format="jpeg")
        assert isinstance(result, bytes)

    def test_rotate_image_for_output_jpeg_grayscale(self):
        from apps.image_rotation.services.transform.image_transform import rotate_image_for_output
        img = Image.new("L", (100, 100))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        result = rotate_image_for_output(buf.getvalue(), rotation=90, img_format="jpeg")
        assert isinstance(result, bytes)

    def test_resize_to_paper_size_landscape(self):
        from apps.image_rotation.services.transform.image_transform import resize_to_paper_size
        img_data = _make_test_image(800, 400)
        sizes = {"a4": (210, 297)}
        result = resize_to_paper_size(img_data, paper_size="a4", paper_sizes=sizes, dpi=150)
        assert isinstance(result, bytes)
