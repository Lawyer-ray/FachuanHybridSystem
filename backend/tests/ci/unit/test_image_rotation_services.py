"""Tests for image_rotation services."""

import base64
import json
from unittest.mock import MagicMock, patch

import pytest


# ============================================================
# auto_rename_service.py - ExtractionResult
# ============================================================

class TestExtractionResult:
    def test_default_values(self):
        from apps.image_rotation.services.auto_rename_service import ExtractionResult
        r = ExtractionResult()
        assert r.date is None
        assert r.amount is None
        assert r.raw_date is None
        assert r.raw_amount is None

    def test_with_values(self):
        from apps.image_rotation.services.auto_rename_service import ExtractionResult
        r = ExtractionResult(date="20250630", amount="65500元", raw_date="2025年6月30日", raw_amount="65,500元")
        assert r.date == "20250630"


# ============================================================
# auto_rename_service.py - RenameSuggestion
# ============================================================

class TestRenameSuggestion:
    def test_success_suggestion(self):
        from apps.image_rotation.services.auto_rename_service import RenameSuggestion
        r = RenameSuggestion(
            original_filename="scan.jpg",
            suggested_filename="20250630_65500元.jpg",
            date="20250630",
            amount="65500元",
            success=True,
        )
        assert r.success is True
        assert r.error is None

    def test_failure_suggestion(self):
        from apps.image_rotation.services.auto_rename_service import RenameSuggestion
        r = RenameSuggestion(
            original_filename="scan.jpg",
            suggested_filename="scan.jpg",
            success=False,
            error="LLM failed",
        )
        assert r.success is False


# ============================================================
# auto_rename_service.py - _normalize_date
# ============================================================

class TestNormalizeDate:
    def _make_service(self):
        from apps.image_rotation.services.auto_rename_service import AutoRenameService
        svc = AutoRenameService.__new__(AutoRenameService)
        svc._ocr_channel = None
        return svc

    def test_valid_8digit(self):
        svc = self._make_service()
        assert svc._normalize_date("20250630") == "20250630"

    def test_with_separators(self):
        svc = self._make_service()
        assert svc._normalize_date("2025-06-30") == "20250630"

    def test_with_slashes(self):
        svc = self._make_service()
        assert svc._normalize_date("2025/06/30") == "20250630"

    def test_6digit_expands(self):
        svc = self._make_service()
        assert svc._normalize_date("250630") == "20250630"

    def test_6digit_old_century(self):
        svc = self._make_service()
        assert svc._normalize_date("990630") == "19990630"

    def test_empty_returns_none(self):
        svc = self._make_service()
        assert svc._normalize_date("") is None

    def test_none_returns_none(self):
        svc = self._make_service()
        assert svc._normalize_date(None) is None

    def test_invalid_length_returns_none(self):
        svc = self._make_service()
        assert svc._normalize_date("202") is None


# ============================================================
# auto_rename_service.py - _extract_json_block
# ============================================================

class TestExtractJsonBlock:
    def _make_service(self):
        from apps.image_rotation.services.auto_rename_service import AutoRenameService
        return AutoRenameService.__new__(AutoRenameService)

    def test_json_code_block(self):
        svc = self._make_service()
        text = '```json\n{"date": "20250630"}\n```'
        result = svc._extract_json_block(text)
        assert '"date"' in result

    def test_plain_code_block(self):
        svc = self._make_service()
        text = '```\n{"date": "20250630"}\n```'
        result = svc._extract_json_block(text)
        assert '"date"' in result

    def test_bare_json(self):
        svc = self._make_service()
        text = 'Here is the result: {"date": "20250630"} done.'
        result = svc._extract_json_block(text)
        assert '{"date"' in result

    def test_no_json_returns_original(self):
        svc = self._make_service()
        text = "no json here"
        assert svc._extract_json_block(text) == text


# ============================================================
# auto_rename_service.py - generate_filename
# ============================================================

class TestGenerateFilename:
    def _make_service(self):
        from apps.image_rotation.services.auto_rename_service import AutoRenameService
        return AutoRenameService.__new__(AutoRenameService)

    def test_date_and_amount(self):
        svc = self._make_service()
        from apps.image_rotation.services.auto_rename_service import ExtractionResult
        result = svc.generate_filename("scan.jpg", ExtractionResult(date="20250630", amount="65500元"))
        assert result == "20250630_65500元.jpg"

    def test_date_only(self):
        svc = self._make_service()
        from apps.image_rotation.services.auto_rename_service import ExtractionResult
        result = svc.generate_filename("scan.jpg", ExtractionResult(date="20250630"))
        assert result == "20250630.jpg"

    def test_amount_only(self):
        svc = self._make_service()
        from apps.image_rotation.services.auto_rename_service import ExtractionResult
        result = svc.generate_filename("scan.jpg", ExtractionResult(amount="65500元"))
        assert result == "65500元.jpg"

    def test_neither_returns_original(self):
        svc = self._make_service()
        from apps.image_rotation.services.auto_rename_service import ExtractionResult
        result = svc.generate_filename("scan.jpg", ExtractionResult())
        assert result == "scan.jpg"


# ============================================================
# auto_rename_service.py - _get_file_extension
# ============================================================

class TestGetFileExtension:
    def _make_service(self):
        from apps.image_rotation.services.auto_rename_service import AutoRenameService
        return AutoRenameService.__new__(AutoRenameService)

    def test_with_extension(self):
        svc = self._make_service()
        assert svc._get_file_extension("photo.jpg") == ".jpg"

    def test_multiple_dots(self):
        svc = self._make_service()
        assert svc._get_file_extension("archive.tar.gz") == ".gz"

    def test_no_extension(self):
        svc = self._make_service()
        assert svc._get_file_extension("Makefile") == ""


# ============================================================
# auto_rename_service.py - _fallback_regex_extraction
# ============================================================

class TestFallbackRegexExtraction:
    def _make_service(self):
        from apps.image_rotation.services.auto_rename_service import AutoRenameService
        return AutoRenameService.__new__(AutoRenameService)

    def test_extract_date_and_amount(self):
        svc = self._make_service()
        text = '{"date": "2025-06-30", "amount": "65500元"}'
        result = svc._fallback_regex_extraction(text)
        assert result.date == "20250630"
        assert result.amount == "65500元"

    def test_extract_null_date(self):
        svc = self._make_service()
        text = '{"date": "null", "amount": "100元"}'
        result = svc._fallback_regex_extraction(text)
        assert result.date is None
        assert result.amount == "100元"


# ============================================================
# pdf_extraction_service.py - _validate_page_count
# ============================================================

class TestValidatePageCount:
    def _make_service(self):
        from apps.image_rotation.services.pdf_extraction_service import PDFExtractionService
        svc = PDFExtractionService.__new__(PDFExtractionService)
        svc._orientation_service = None
        return svc

    def test_over_limit(self):
        svc = self._make_service()
        result = svc._validate_page_count(101, "test.pdf")
        assert result is not None
        assert result["success"] is False
        assert "100" in result["message"]

    def test_zero_pages(self):
        svc = self._make_service()
        result = svc._validate_page_count(0, "test.pdf")
        assert result is not None
        assert result["success"] is False

    def test_valid_count(self):
        svc = self._make_service()
        assert svc._validate_page_count(10, "test.pdf") is None


# ============================================================
# facade.py - _get_unique_filename
# ============================================================

class TestGetUniqueFilename:
    def _make_service(self):
        from apps.image_rotation.services.facade import ImageRotationService
        return ImageRotationService()

    def test_unique_name_unchanged(self):
        svc = self._make_service()
        used = {}
        assert svc._get_unique_filename("photo.jpg", used) == "photo.jpg"

    def test_duplicate_name_gets_suffix(self):
        svc = self._make_service()
        used = {"photo.jpg": 1}
        assert svc._get_unique_filename("photo.jpg", used) == "photo_1.jpg"
        assert used["photo.jpg"] == 2

    def test_empty_name_generates(self):
        svc = self._make_service()
        used = {}
        result = svc._get_unique_filename("", used)
        assert result.startswith("image_")
        assert result.endswith(".jpg")

    def test_no_extension(self):
        svc = self._make_service()
        used = {"Makefile": 1}
        result = svc._get_unique_filename("Makefile", used)
        assert result == "Makefile_1"


# ============================================================
# facade.py - _process_page_for_pdf rotation validation
# ============================================================

class TestProcessPageForPdf:
    def _make_service(self):
        from apps.image_rotation.services.facade import ImageRotationService
        svc = ImageRotationService.__new__(ImageRotationService)
        svc.SUPPORTED_FORMATS = {"jpeg", "jpg", "png"}
        svc.MAX_FILE_SIZE = 20 * 1024 * 1024
        svc.PAPER_SIZES = {"original": None}
        svc.DEFAULT_DPI = 150
        return svc

    def test_invalid_rotation_defaults_to_zero(self):
        svc = self._make_service()
        data = base64.b64encode(b"fake_image").decode()
        with patch("apps.image_rotation.services.facade.validation") as mock_val:
            mock_val.decode_base64_payload.return_value = b"fake_image"
            result = svc._process_page_for_pdf({"data": data, "rotation": 45})
            assert result is not None
            assert result[1] == 0

    def test_valid_rotation_preserved(self):
        svc = self._make_service()
        data = base64.b64encode(b"fake_image").decode()
        with patch("apps.image_rotation.services.facade.validation") as mock_val:
            mock_val.decode_base64_payload.return_value = b"fake_image"
            result = svc._process_page_for_pdf({"data": data, "rotation": 90})
            assert result is not None
            assert result[1] == 90
