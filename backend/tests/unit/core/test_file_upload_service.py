"""
FileUploadService 单元测试

Requirements: 4.4, 4.5, 6.1, 6.2, 6.3
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException
from apps.core.services.file_upload_service import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE,
    FileUploadService,
)


def make_mock_file(
    name: str = "test.pdf",
    size: int = 1024,
    content_type: str = "application/pdf",
    content: bytes = b"%PDF-1.7",
) -> MagicMock:
    """创建模拟 UploadedFile 对象"""
    mock_file = MagicMock()
    mock_file.name = name
    mock_file.size = size
    mock_file.content_type = content_type
    mock_file.chunks.return_value = [content]
    return mock_file


# ─── 文件大小验证 ────────────────────────────────────────────────────────────


class TestFileSizeValidation:
    def test_valid_file_size_passes(self) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(size=1024)
        # 不应抛出异常
        service.validate_file(mock_file)

    def test_file_at_max_size_passes(self) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(size=MAX_FILE_SIZE)
        service.validate_file(mock_file)

    def test_file_exceeds_max_size_raises(self) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(size=MAX_FILE_SIZE + 1)
        with pytest.raises(ValidationException) as exc_info:
            service.validate_file(mock_file)
        assert exc_info.value.code == "FILE_TOO_LARGE"

    def test_file_size_zero_passes(self) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(size=0)
        # 0 字节文件大小合法（不超限）
        service.validate_file(mock_file)

    def test_file_size_none_treated_as_zero(self) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(size=None)  # type: ignore[arg-type]
        # size=None 应被当作 0 处理，不超限
        service.validate_file(mock_file)

    def test_error_message_contains_max_mb(self) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(size=MAX_FILE_SIZE + 1)
        with pytest.raises(ValidationException) as exc_info:
            service.validate_file(mock_file)
        assert "20MB" in str(exc_info.value)


# ─── 文件类型白名单验证 ──────────────────────────────────────────────────────


class TestFileTypeWhitelistValidation:
    @pytest.mark.parametrize(
        "ext,mime",
        [
            (".pdf", "application/pdf"),
            (".jpg", "image/jpeg"),
            (".jpeg", "image/jpeg"),
            (".png", "image/png"),
            (".doc", "application/msword"),
            (".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ],
    )
    def test_allowed_extensions_pass(self, ext: str, mime: str) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name=f"file{ext}", content_type=mime)
        service.validate_file(mock_file)

    @pytest.mark.parametrize("ext", [".exe", ".sh", ".py", ".js", ".txt", ".zip", ".csv", ""])
    def test_disallowed_extensions_raise(self, ext: str) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name=f"file{ext}", content_type="application/octet-stream")
        with pytest.raises(ValidationException) as exc_info:
            service.validate_file(mock_file)
        assert exc_info.value.code == "INVALID_FILE_TYPE"

    def test_error_includes_allowed_types(self) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name="file.exe", content_type="application/octet-stream")
        with pytest.raises(ValidationException) as exc_info:
            service.validate_file(mock_file)
        assert exc_info.value.errors is not None
        assert "allowed_types" in exc_info.value.errors

    def test_extension_check_is_case_insensitive(self) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name="FILE.PDF", content_type="application/pdf")
        service.validate_file(mock_file)

    def test_allowed_extensions_constant_contains_expected(self) -> None:
        assert ".pdf" in ALLOWED_EXTENSIONS
        assert ".jpg" in ALLOWED_EXTENSIONS
        assert ".jpeg" in ALLOWED_EXTENSIONS
        assert ".png" in ALLOWED_EXTENSIONS
        assert ".doc" in ALLOWED_EXTENSIONS
        assert ".docx" in ALLOWED_EXTENSIONS


# ─── MIME 类型验证 ───────────────────────────────────────────────────────────


class TestMimeTypeValidation:
    @pytest.mark.parametrize("mime", list(ALLOWED_MIME_TYPES))
    def test_allowed_mime_types_pass(self, mime: str) -> None:
        service = FileUploadService()
        # 选择与 MIME 匹配的扩展名
        mime_to_ext: dict[str, str] = {
            "application/pdf": ".pdf",
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "application/msword": ".doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        }
        ext = mime_to_ext.get(mime, ".pdf")
        mock_file = make_mock_file(name=f"file{ext}", content_type=mime)
        service.validate_file(mock_file)

    def test_disallowed_mime_type_raises(self) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name="file.pdf", content_type="text/html")
        with pytest.raises(ValidationException) as exc_info:
            service.validate_file(mock_file)
        assert exc_info.value.code == "INVALID_MIME_TYPE"

    def test_empty_mime_type_raises(self) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name="file.pdf", content_type="")
        with pytest.raises(ValidationException) as exc_info:
            service.validate_file(mock_file)
        assert exc_info.value.code == "INVALID_MIME_TYPE"

    def test_mime_extension_mismatch_raises(self) -> None:
        """MIME 类型与扩展名不匹配时应抛出异常"""
        service = FileUploadService()
        # .png 扩展名但声明为 PDF MIME 类型
        mock_file = make_mock_file(name="file.png", content_type="application/pdf")
        with pytest.raises(ValidationException) as exc_info:
            service.validate_file(mock_file)
        assert exc_info.value.code == "MIME_EXTENSION_MISMATCH"

    def test_jpeg_extension_with_jpeg_mime_passes(self) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name="photo.jpeg", content_type="image/jpeg")
        service.validate_file(mock_file)

    def test_jpg_extension_with_jpeg_mime_passes(self) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name="photo.jpg", content_type="image/jpeg")
        service.validate_file(mock_file)


# ─── 文件名清理 ──────────────────────────────────────────────────────────────


class TestFilenameSanitization:
    def test_preserve_name_removes_path_traversal_dots(self, tmp_path: Path) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name="../../../etc/passwd.pdf", content_type="application/pdf")
        with patch("apps.core.services.file_upload_service.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            saved_path = service.save_file(mock_file, "uploads", preserve_name=True)
        # 保存的文件名不应包含 ..
        assert ".." not in saved_path.name

    def test_preserve_name_removes_forward_slash(self, tmp_path: Path) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name="sub/dir/file.pdf", content_type="application/pdf")
        with patch("apps.core.services.file_upload_service.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            saved_path = service.save_file(mock_file, "uploads", preserve_name=True)
        assert "/" not in saved_path.name

    def test_preserve_name_removes_backslash(self, tmp_path: Path) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name="sub\\dir\\file.pdf", content_type="application/pdf")
        with patch("apps.core.services.file_upload_service.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            saved_path = service.save_file(mock_file, "uploads", preserve_name=True)
        assert "\\" not in saved_path.name

    def test_preserve_name_keeps_original_extension(self, tmp_path: Path) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name="document.pdf", content_type="application/pdf")
        with patch("apps.core.services.file_upload_service.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            saved_path = service.save_file(mock_file, "uploads", preserve_name=True)
        assert saved_path.suffix == ".pdf"

    def test_preserve_name_includes_original_filename(self, tmp_path: Path) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name="myreport.pdf", content_type="application/pdf")
        with patch("apps.core.services.file_upload_service.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            saved_path = service.save_file(mock_file, "uploads", preserve_name=True)
        assert "myreport.pdf" in saved_path.name


# ─── UUID 文件名生成 ──────────────────────────────────────────────────────────


class TestUUIDFilenameGeneration:
    def test_default_save_uses_uuid_filename(self, tmp_path: Path) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name="original.pdf", content_type="application/pdf")
        with patch("apps.core.services.file_upload_service.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            saved_path = service.save_file(mock_file, "uploads")
        # 文件名应为 32 位 hex（uuid4().hex）+ 扩展名
        stem = saved_path.stem
        assert len(stem) == 32
        # 应为有效的十六进制字符串
        int(stem, 16)

    def test_default_save_preserves_extension(self, tmp_path: Path) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name="photo.png", content_type="image/png")
        with patch("apps.core.services.file_upload_service.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            saved_path = service.save_file(mock_file, "uploads")
        assert saved_path.suffix == ".png"

    def test_two_saves_produce_different_filenames(self, tmp_path: Path) -> None:
        service = FileUploadService()
        mock_file1 = make_mock_file(name="file.pdf", content_type="application/pdf")
        mock_file2 = make_mock_file(name="file.pdf", content_type="application/pdf")
        with patch("apps.core.services.file_upload_service.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            path1 = service.save_file(mock_file1, "uploads")
            path2 = service.save_file(mock_file2, "uploads")
        assert path1.name != path2.name

    def test_preserve_name_uses_short_uuid_prefix(self, tmp_path: Path) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name="doc.pdf", content_type="application/pdf")
        with patch("apps.core.services.file_upload_service.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            saved_path = service.save_file(mock_file, "uploads", preserve_name=True)
        # preserve_name 模式：{8位hex}_{原始文件名}
        parts = saved_path.name.split("_", 1)
        assert len(parts) == 2
        assert len(parts[0]) == 8
        int(parts[0], 16)  # 应为有效十六进制

    def test_save_file_creates_target_directory(self, tmp_path: Path) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name="file.pdf", content_type="application/pdf")
        with patch("apps.core.services.file_upload_service.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            saved_path = service.save_file(mock_file, "new/nested/dir")
        assert saved_path.parent.exists()

    def test_save_file_returns_absolute_path(self, tmp_path: Path) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name="file.pdf", content_type="application/pdf")
        with patch("apps.core.services.file_upload_service.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            saved_path = service.save_file(mock_file, "uploads")
        assert saved_path.is_absolute()

    def test_save_file_writes_content(self, tmp_path: Path) -> None:
        service = FileUploadService()
        content = b"%PDF-1.7 test content"
        mock_file = make_mock_file(name="file.pdf", content_type="application/pdf", content=content)
        with patch("apps.core.services.file_upload_service.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            saved_path = service.save_file(mock_file, "uploads")
        assert saved_path.read_bytes() == content

    def test_save_file_raises_on_invalid_file(self, tmp_path: Path) -> None:
        service = FileUploadService()
        mock_file = make_mock_file(name="virus.exe", content_type="application/octet-stream")
        with patch("apps.core.services.file_upload_service.settings") as mock_settings:
            mock_settings.MEDIA_ROOT = str(tmp_path)
            with pytest.raises(ValidationException):
                service.save_file(mock_file, "uploads")
