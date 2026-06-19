"""Tests for core/services/storage_service.validate_file().

Covers: validate_file — all validation branches (size, extension, MIME, mismatch).
Originally tested FileUploadService.validate_file(), now tests the merged
storage_service.validate_file() function.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.core.exceptions import ValidationException
from apps.core.services.storage_service import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    validate_file,
)


class TestValidateFile:
    def _make_file(self, *, name: str = "test.pdf", size: int = 1000, content_type: str = "application/pdf"):
        f = MagicMock()
        f.name = name
        f.size = size
        f.content_type = content_type
        return f

    def test_valid_pdf(self):
        f = self._make_file()
        validate_file(f)  # should not raise

    def test_valid_jpg(self):
        f = self._make_file(name="photo.jpg", content_type="image/jpeg")
        validate_file(f)

    def test_valid_png(self):
        f = self._make_file(name="image.png", content_type="image/png")
        validate_file(f)

    def test_valid_docx(self):
        f = self._make_file(name="report.docx", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        validate_file(f)

    def test_valid_doc(self):
        f = self._make_file(name="report.doc", content_type="application/msword")
        validate_file(f)

    def test_file_too_large(self):
        f = self._make_file(size=20 * 1024 * 1024 + 1)
        with pytest.raises(ValidationException) as exc_info:
            validate_file(f)
        assert exc_info.value.code == "FILE_TOO_LARGE"

    def test_file_exactly_max_size(self):
        f = self._make_file(size=20 * 1024 * 1024)
        validate_file(f)

    def test_invalid_extension(self):
        f = self._make_file(name="script.exe", content_type="application/octet-stream")
        with pytest.raises(ValidationException) as exc_info:
            validate_file(f)
        assert exc_info.value.code == "INVALID_FILE_TYPE"

    def test_invalid_mime_type(self):
        f = self._make_file(name="test.pdf", content_type="application/x-executable")
        with pytest.raises(ValidationException) as exc_info:
            validate_file(f)
        assert exc_info.value.code == "INVALID_MIME_TYPE"

    def test_mime_extension_mismatch(self):
        # .pdf extension but .doc MIME type
        f = self._make_file(name="test.pdf", content_type="application/msword")
        with pytest.raises(ValidationException) as exc_info:
            validate_file(f)
        assert exc_info.value.code == "MIME_EXTENSION_MISMATCH"

    def test_no_content_type(self):
        f = self._make_file(name="test.pdf", content_type=None)
        with pytest.raises(ValidationException) as exc_info:
            validate_file(f)
        assert exc_info.value.code == "INVALID_MIME_TYPE"

    def test_no_file_name(self):
        f = self._make_file(name=None, content_type="application/pdf")
        # Path("").suffix == "" which is not in ALLOWED_EXTENSIONS
        with pytest.raises(ValidationException) as exc_info:
            validate_file(f)
        assert exc_info.value.code == "INVALID_FILE_TYPE"

    def test_zero_size(self):
        f = self._make_file(size=0)
        validate_file(f)

    def test_uppercase_extension_treated_as_lowercase(self):
        f = self._make_file(name="test.PDF", content_type="application/pdf")
        validate_file(f)


class TestStorageServiceConstants:
    def test_allowed_extensions(self):
        assert ".pdf" in ALLOWED_EXTENSIONS
        assert ".jpg" in ALLOWED_EXTENSIONS
        assert ".png" in ALLOWED_EXTENSIONS
        assert ".doc" in ALLOWED_EXTENSIONS
        assert ".docx" in ALLOWED_EXTENSIONS

    def test_allowed_mime_types(self):
        assert "application/pdf" in ALLOWED_MIME_TYPES
        assert "image/jpeg" in ALLOWED_MIME_TYPES
        assert "image/png" in ALLOWED_MIME_TYPES
