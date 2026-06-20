"""Final coverage tests for core module — targeting uncovered service lines."""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from unittest.mock import MagicMock, Mock, PropertyMock, patch

import pytest

from apps.core.exceptions import ValidationException
from apps.core.services.storage_service import (
    _WINDOWS_ABS_PATH,
    _DefaultFileValidator,
    _get_media_root,
    delete_media_file,
    is_absolute_path,
    normalize_to_media_rel,
    sanitize_upload_filename,
    save_uploaded_file,
    to_media_abs,
)

# ============================================================================
# sanitize_upload_filename tests
# ============================================================================


class TestSanitizeUploadFilename:
    def test_normal_filename(self):
        result = sanitize_upload_filename("document.pdf")
        assert result == "document.pdf"

    def test_chinese_filename(self):
        result = sanitize_upload_filename("法律文书.docx")
        assert "法律文书" in result

    def test_empty_filename(self):
        result = sanitize_upload_filename("")
        assert result == "file"

    def test_path_prefix_stripped(self):
        result = sanitize_upload_filename("/some/path/file.txt")
        assert result == "file.txt"

    def test_backslash_path_stripped(self):
        result = sanitize_upload_filename("C:\\Users\\file.txt")
        assert result == "file.txt"

    def test_special_chars_replaced(self):
        result = sanitize_upload_filename("file name@#.txt")
        assert "@" not in result
        assert "#" not in result

    def test_multiple_underscores_preserved(self):
        # sanitize_filename 保留有效字符（包括下划线），不折叠连续下划线
        result = sanitize_upload_filename("file___name.txt")
        assert "file" in result
        assert "name" in result

    def test_dot_only_filename(self):
        result = sanitize_upload_filename(".")
        assert result  # should not be empty

    def test_long_filename_truncated(self):
        long_name = "a" * 200 + ".pdf"
        result = sanitize_upload_filename(long_name, max_length=50)
        assert len(result) <= 50
        assert result.endswith(".pdf")

    def test_no_extension(self):
        result = sanitize_upload_filename("README")
        assert "README" in result or result == "file"

    def test_dotfiles(self):
        result = sanitize_upload_filename(".hidden")
        assert result

    def test_windows_abs_path(self):
        result = sanitize_upload_filename("D:\\folder\\file.txt")
        assert result == "file.txt"


# ============================================================================
# is_absolute_path tests
# ============================================================================


class TestIsAbsolutePath:
    def test_unix_absolute(self):
        assert is_absolute_path("/home/user/file") is True

    def test_windows_absolute(self):
        assert is_absolute_path("C:\\Users\\file") is True

    def test_relative_path(self):
        assert is_absolute_path("relative/path") is False

    def test_empty_string(self):
        assert is_absolute_path("") is False

    def test_none_input(self):
        assert is_absolute_path(None) is False

    def test_backslash_root(self):
        assert is_absolute_path("\\\\server\\share") is True

    def test_unix_root_only(self):
        assert is_absolute_path("/") is True

    def test_windows_d_drive(self):
        assert is_absolute_path("D:\\file") is True

    def test_whitespace_only(self):
        assert is_absolute_path("   ") is False


# ============================================================================
# to_media_abs tests
# ============================================================================


class TestToMediaAbs:
    def test_empty_path_raises(self):
        with pytest.raises(ValidationException):
            to_media_abs("")

    @patch("apps.core.services.storage_service._get_media_root", return_value=None)
    def test_no_media_root_raises(self, mock_root):
        with pytest.raises(ValidationException, match="MEDIA_ROOT"):
            to_media_abs("some/file.txt")

    @patch("apps.core.services.storage_service._get_media_root")
    def test_relative_path_resolved(self, mock_root, tmp_path):
        mock_root.return_value = str(tmp_path)
        result = to_media_abs("subdir/file.txt")
        assert result.is_absolute()
        assert "subdir" in str(result)

    @patch("apps.core.services.storage_service._get_media_root")
    def test_absolute_path_within_root(self, mock_root, tmp_path):
        mock_root.return_value = str(tmp_path)
        abs_file = tmp_path / "file.txt"
        abs_file.touch()
        result = to_media_abs(str(abs_file))
        assert result == abs_file.resolve()

    @patch("apps.core.services.storage_service._get_media_root")
    def test_absolute_path_outside_root_raises(self, mock_root, tmp_path):
        mock_root.return_value = str(tmp_path)
        with pytest.raises(ValidationException, match="不在 MEDIA_ROOT"):
            to_media_abs("/etc/passwd")


# ============================================================================
# normalize_to_media_rel tests
# ============================================================================


class TestNormalizeToMediaRel:
    def test_empty_path_raises(self):
        with pytest.raises(ValidationException):
            normalize_to_media_rel("")

    def test_relative_path_returned(self):
        result = normalize_to_media_rel("subdir/file.txt")
        assert result == "subdir/file.txt"

    def test_relative_backslash_normalized(self):
        result = normalize_to_media_rel("subdir\\file.txt")
        assert "/" in result
        assert "\\" not in result

    @patch("apps.core.services.storage_service._get_media_root", return_value=None)
    def test_absolute_no_media_root_raises(self, mock_root):
        with pytest.raises(ValidationException, match="MEDIA_ROOT"):
            normalize_to_media_rel("/some/path")

    @patch("apps.core.services.storage_service._get_media_root")
    def test_absolute_within_root(self, mock_root, tmp_path):
        mock_root.return_value = str(tmp_path)
        abs_path = str(tmp_path / "sub" / "file.txt")
        result = normalize_to_media_rel(abs_path)
        assert result == "sub/file.txt"

    @patch("apps.core.services.storage_service._get_media_root")
    def test_absolute_outside_root_raises(self, mock_root, tmp_path):
        mock_root.return_value = str(tmp_path)
        with pytest.raises(ValidationException, match="不在 MEDIA_ROOT"):
            normalize_to_media_rel("/etc/hosts")


# ============================================================================
# _DefaultFileValidator tests
# ============================================================================


class TestDefaultFileValidator:
    def setup_method(self):
        self.validator = _DefaultFileValidator()

    def test_validate_none_raises(self):
        with pytest.raises(ValidationException):
            self.validator.validate_uploaded_file(None)

    def test_validate_wrong_extension(self):
        f = Mock()
        f.name = "file.exe"
        f.size = 100
        f.content_type = ""
        f.read.return_value = b"PK\x03\x04"
        f.seek.return_value = None
        with pytest.raises(ValidationException, match="不支持的文件格式"):
            self.validator.validate_uploaded_file(f, allowed_extensions=[".pdf", ".docx"])

    def test_validate_too_large(self):
        f = Mock()
        f.name = "file.pdf"
        f.size = 100 * 1024 * 1024
        f.content_type = ""
        f.read.return_value = b"%PDF"
        f.seek.return_value = None
        with pytest.raises(ValidationException, match="文件大小超限"):
            self.validator.validate_uploaded_file(f, max_size_bytes=1024)

    def test_validate_executable_rejected(self):
        f = Mock()
        f.name = "file.pdf"
        f.size = 100
        f.content_type = ""
        f.read.return_value = b"MZ\x90\x00"
        f.seek.return_value = None
        with pytest.raises(ValidationException, match="可执行文件"):
            self.validator.validate_uploaded_file(f)

    def test_validate_ok(self):
        f = Mock()
        f.name = "file.pdf"
        f.size = 100
        f.content_type = ""
        f.read.return_value = b"%PDF-1.4"
        f.seek.return_value = None
        result = self.validator.validate_uploaded_file(f)
        assert result == f

    def test_validate_elf_rejected(self):
        f = Mock()
        f.name = "file.bin"
        f.size = 50
        f.content_type = ""
        f.read.return_value = b"\x7fELF"
        f.seek.return_value = None
        with pytest.raises(ValidationException, match="可执行文件"):
            self.validator.validate_uploaded_file(f)


# ============================================================================
# save_uploaded_file tests
# ============================================================================


class TestSaveUploadedFile:
    def test_missing_name_raises(self):
        f = object()
        with pytest.raises(ValidationException, match="缺少文件名"):
            save_uploaded_file(f, "uploads")

    @patch("apps.core.services.storage_service.default_storage")
    @patch("apps.core.services.storage_service._get_media_root")
    def test_save_with_uuid(self, mock_root, mock_storage, tmp_path):
        mock_root.return_value = str(tmp_path)
        f = Mock()
        f.name = "test.pdf"
        f.size = 100
        f.content_type = ""
        f.read.return_value = b"%PDF"
        f.seek.return_value = None
        f.chunks.return_value = [b"%PDF"]

        validator = Mock()
        validator.validate_uploaded_file.return_value = f

        rel_path, safe_name = save_uploaded_file(
            f, "uploads", file_validator=validator, use_uuid_name=True
        )
        assert rel_path.startswith("uploads/")
        assert safe_name == "test.pdf"

    @patch("apps.core.services.storage_service.default_storage")
    @patch("apps.core.services.storage_service._get_media_root")
    def test_save_without_uuid(self, mock_root, mock_storage, tmp_path):
        mock_root.return_value = str(tmp_path)
        f = Mock()
        f.name = "report.docx"
        f.size = 200
        f.content_type = ""
        f.read.return_value = b"content"
        f.seek.return_value = None
        f.chunks.return_value = [b"content"]

        validator = Mock()
        validator.validate_uploaded_file.return_value = f

        rel_path, safe_name = save_uploaded_file(
            f, "docs", file_validator=validator, use_uuid_name=False
        )
        assert "report" in safe_name

    @patch("apps.core.services.storage_service._get_media_root", return_value=None)
    def test_save_no_media_root_raises(self, mock_root):
        f = Mock()
        f.name = "test.pdf"
        validator = Mock()
        validator.validate_uploaded_file.return_value = f
        with pytest.raises(ValidationException, match="MEDIA_ROOT"):
            save_uploaded_file(f, "dir", file_validator=validator)


# ============================================================================
# delete_media_file tests
# ============================================================================


class TestDeleteMediaFile:
    def test_empty_path(self):
        assert delete_media_file("") is False

    @patch("apps.core.services.storage_service._get_media_root", return_value=None)
    def test_no_media_root(self, mock_root):
        assert delete_media_file("file.txt") is False

    @patch("apps.core.services.storage_service._get_media_root")
    def test_delete_existing_file(self, mock_root, tmp_path):
        mock_root.return_value = str(tmp_path)
        f = tmp_path / "test.txt"
        f.write_text("content")
        assert delete_media_file("test.txt") is True
        assert not f.exists()

    @patch("apps.core.services.storage_service._get_media_root")
    def test_delete_nonexistent_file(self, mock_root, tmp_path):
        mock_root.return_value = str(tmp_path)
        assert delete_media_file("nonexistent.txt") is True

    @patch("apps.core.services.storage_service._get_media_root")
    def test_delete_outside_root(self, mock_root, tmp_path):
        mock_root.return_value = str(tmp_path)
        assert delete_media_file("/etc/passwd") is False


# ============================================================================
# OCR regex constants tests
# ============================================================================


class TestStorageRegex:
    def test_windows_abs_path_regex(self):
        assert _WINDOWS_ABS_PATH.match("C:\\path")
        assert _WINDOWS_ABS_PATH.match("D:\\path")
        assert not _WINDOWS_ABS_PATH.match("/unix/path")
        assert not _WINDOWS_ABS_PATH.match("relative")
