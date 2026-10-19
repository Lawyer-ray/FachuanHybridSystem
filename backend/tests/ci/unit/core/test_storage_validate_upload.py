"""storage_service.validate_upload 单元测试（解耦（2026-10-19）统一上传校验）。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.core.exceptions import ValidationException
from apps.core.services.storage_service import validate_upload


def _file(name: str, size: int) -> MagicMock:
    f = MagicMock()
    f.name = name
    f.size = size
    return f


class TestValidateUpload:
    def test_valid_file_passes(self) -> None:
        assert validate_upload(_file("a.pdf", 1024), allowed_extensions=[".pdf"], max_size_bytes=2048) is None

    def test_extension_case_insensitive(self) -> None:
        assert validate_upload(_file("A.PDF", 1), allowed_extensions=[".pdf"], max_size_bytes=None) is None

    def test_disallowed_extension_raises_invalid_file_type(self) -> None:
        with pytest.raises(ValidationException) as exc_info:
            validate_upload(_file("x.exe", 1), allowed_extensions=[".pdf", ".jpg"], max_size_bytes=None)
        assert exc_info.value.code == "INVALID_FILE_TYPE"
        assert ".exe" in exc_info.value.message
        assert "允许的格式" in str(exc_info.value.errors.get("file", ""))

    def test_no_extension_raises_invalid_file_type(self) -> None:
        with pytest.raises(ValidationException) as exc_info:
            validate_upload(_file("noext", 1), allowed_extensions=[".pdf"], max_size_bytes=None)
        assert exc_info.value.code == "INVALID_FILE_TYPE"
        assert "无扩展名" in exc_info.value.message

    def test_oversize_raises_file_too_large(self) -> None:
        with pytest.raises(ValidationException) as exc_info:
            validate_upload(_file("big.pdf", 100), allowed_extensions=[".pdf"], max_size_bytes=99)
        assert exc_info.value.code == "FILE_TOO_LARGE"
        assert "文件过大" in exc_info.value.message

    def test_none_limits_skip_checks(self) -> None:
        """allowed_extensions / max_size_bytes 均为 None 时只做空文件检查。"""
        assert validate_upload(_file("anything.xyz", 10**9)) is None

    def test_empty_file_rejected(self) -> None:
        with pytest.raises(ValidationException, match="请选择要上传的文件"):
            validate_upload(None)  # type: ignore[arg-type]

    def test_custom_field_name(self) -> None:
        with pytest.raises(ValidationException) as exc_info:
            validate_upload(_file("x.exe", 1), allowed_extensions=[".pdf"], max_size_bytes=None, field="avatar")
        assert "avatar" in exc_info.value.errors

    def test_mime_consistency_not_enforced_here(self) -> None:
        """轻量校验不做 MIME 一致性检查（那是 save_uploaded_file 的职责）。"""
        f = _file("a.docx", 10)
        f.content_type = "application/octet-stream"
        assert validate_upload(f, allowed_extensions=[".docx"], max_size_bytes=None) is None
