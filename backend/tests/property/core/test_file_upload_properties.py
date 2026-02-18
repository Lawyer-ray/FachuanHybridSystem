"""
FileUploadService 属性测试

# Feature: backend-perfect-score, Property 1: 文件类型白名单一致性
# Feature: backend-perfect-score, Property 2: 文件名安全性
Validates: Requirements 4.4, 6.1, 6.3
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import HealthCheck, given, settings

from apps.core.exceptions import ValidationException
from apps.core.services.file_upload_service import ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES, FileUploadService
from tests.strategies.file_strategies import allowed_file, arbitrary_filename, disallowed_extension_file

# ---------------------------------------------------------------------------
# Property 1: 文件类型白名单一致性
# ---------------------------------------------------------------------------


class TestFileTypeWhitelistConsistencyProperty:
    """
    Property 1: 文件类型白名单一致性

    # Feature: backend-perfect-score, Property 1: 文件类型白名单一致性
    Validates: Requirements 4.4, 6.1
    """

    @given(file=allowed_file())
    @settings(max_examples=100)
    def test_allowed_extension_has_allowed_mime(self, file: object) -> None:
        """
        Property 1a: 白名单扩展名对应的 MIME 类型必须在 ALLOWED_MIME_TYPES 中。

        # Feature: backend-perfect-score, Property 1: 文件类型白名单一致性
        Validates: Requirements 4.4, 6.1
        """
        from unittest.mock import MagicMock

        assert isinstance(file, MagicMock)
        ext = Path(file.name).suffix.lower()
        assert ext in ALLOWED_EXTENSIONS, f"扩展名 {ext} 不在白名单中"
        assert file.content_type in ALLOWED_MIME_TYPES, f"MIME 类型 {file.content_type} 不在白名单中（扩展名 {ext}）"

    @given(file=allowed_file())
    @settings(max_examples=100)
    def test_allowed_file_passes_validation(self, file: object) -> None:
        """
        Property 1b: 白名单内的合法文件应通过 validate_file 验证，不抛出异常。

        # Feature: backend-perfect-score, Property 1: 文件类型白名单一致性
        Validates: Requirements 4.4, 6.1
        """
        service = FileUploadService()
        # 不应抛出 ValidationException
        service.validate_file(file)  # type: ignore[arg-type]

    @given(file=disallowed_extension_file())
    @settings(max_examples=100)
    def test_disallowed_extension_raises_validation_exception(self, file: object) -> None:
        """
        Property 1c: 扩展名不在白名单中时，validate_file 必须抛出 ValidationException。

        # Feature: backend-perfect-score, Property 1: 文件类型白名单一致性
        Validates: Requirements 4.4, 6.1
        """
        service = FileUploadService()
        with pytest.raises(ValidationException) as exc_info:
            service.validate_file(file)  # type: ignore[arg-type]
        # 必须是文件类型相关的错误（扩展名或 MIME 类型）
        assert exc_info.value.code in (
            "INVALID_FILE_TYPE",
            "INVALID_MIME_TYPE",
            "MIME_EXTENSION_MISMATCH",
        )


# ---------------------------------------------------------------------------
# Property 2: 文件名安全性
# ---------------------------------------------------------------------------


class TestFilenameSafetyProperty:
    """
    Property 2: 文件名安全性

    # Feature: backend-perfect-score, Property 2: 文件名安全性
    Validates: Requirements 6.3
    """

    @given(filename=arbitrary_filename())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_saved_filename_no_path_traversal(self, filename: str) -> None:
        """
        Property 2a: save_file 生成的文件名不应包含路径遍历字符（..、/、\\）。

        # Feature: backend-perfect-score, Property 2: 文件名安全性
        Validates: Requirements 6.3
        """
        from unittest.mock import MagicMock

        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            return

        _ext_to_mime: dict[str, str] = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        mime = _ext_to_mime.get(ext, "application/pdf")

        mock_file = MagicMock()
        mock_file.name = filename
        mock_file.size = 100
        mock_file.content_type = mime
        mock_file.chunks.return_value = [b"content"]

        service = FileUploadService()
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("apps.core.services.file_upload_service.settings") as mock_settings:
                mock_settings.MEDIA_ROOT = tmp_dir
                try:
                    saved_path = service.save_file(mock_file, "uploads", preserve_name=True)
                except ValidationException:
                    return

        saved_name = saved_path.name
        assert ".." not in saved_name, f"文件名包含路径遍历字符 '..': {saved_name}"
        assert "/" not in saved_name, f"文件名包含 '/': {saved_name}"
        assert "\\" not in saved_name, f"文件名包含 '\\': {saved_name}"

    @given(filename=arbitrary_filename())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_saved_filename_starts_with_uuid(self, filename: str) -> None:
        """
        Property 2b: save_file（默认模式）生成的文件名应以 UUID（32位十六进制）开头。

        # Feature: backend-perfect-score, Property 2: 文件名安全性
        Validates: Requirements 6.3
        """
        from unittest.mock import MagicMock

        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            return

        _ext_to_mime: dict[str, str] = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        mime = _ext_to_mime.get(ext, "application/pdf")

        mock_file = MagicMock()
        mock_file.name = filename
        mock_file.size = 100
        mock_file.content_type = mime
        mock_file.chunks.return_value = [b"content"]

        service = FileUploadService()
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("apps.core.services.file_upload_service.settings") as mock_settings:
                mock_settings.MEDIA_ROOT = tmp_dir
                try:
                    saved_path = service.save_file(mock_file, "uploads")
                except ValidationException:
                    return

        stem = saved_path.stem
        assert len(stem) == 32, f"文件名 stem 长度不为 32: {stem!r}"
        try:
            int(stem, 16)
        except ValueError:
            pytest.fail(f"文件名 stem 不是有效的十六进制字符串: {stem!r}")
