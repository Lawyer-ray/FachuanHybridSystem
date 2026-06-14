"""Tests for apps.client.adapters.file_validator_adapter."""
from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest

from apps.client.adapters.file_validator_adapter import FileValidatorAdapter
from apps.core.exceptions import ValidationException


class TestFileValidatorAdapter:
    def setup_method(self) -> None:
        self.adapter = FileValidatorAdapter()

    def _make_file(self, name: str, content: bytes = b"hello", size: int | None = None) -> Any:
        """Create a minimal file-like object for testing."""
        buf = BytesIO(content)
        file_obj = SimpleNamespace(
            name=name,
            size=size if size is not None else len(content),
            read=buf.read,
            seek=buf.seek,
        )
        return file_obj

    def test_none_file_raises(self) -> None:
        with pytest.raises(ValidationException, match="请选择要上传的文件"):
            self.adapter.validate_uploaded_file(None)

    def test_empty_file_raises(self) -> None:
        with pytest.raises(ValidationException, match="请选择要上传的文件"):
            self.adapter.validate_uploaded_file("")

    def test_valid_pdf(self) -> None:
        f = self._make_file("doc.pdf")
        result = self.adapter.validate_uploaded_file(f, allowed_extensions=[".pdf", ".jpg"])
        assert result is f

    def test_invalid_extension_raises(self) -> None:
        f = self._make_file("virus.exe")
        with pytest.raises(ValidationException, match="不支持的文件格式"):
            self.adapter.validate_uploaded_file(f, allowed_extensions=[".pdf"])

    def test_no_extension(self) -> None:
        f = self._make_file("noext")
        # No dot in filename, ext will be empty string
        # "" not in [".pdf"] so it should raise
        with pytest.raises(ValidationException, match="不支持的文件格式"):
            self.adapter.validate_uploaded_file(f, allowed_extensions=[".pdf"])

    def test_file_too_large(self) -> None:
        f = self._make_file("big.pdf", size=10000)
        with pytest.raises(ValidationException, match="文件大小超限"):
            self.adapter.validate_uploaded_file(f, max_size_bytes=100)

    def test_file_within_size_limit(self) -> None:
        f = self._make_file("small.pdf", size=50)
        result = self.adapter.validate_uploaded_file(f, max_size_bytes=100)
        assert result is f

    def test_executable_mz_detected(self) -> None:
        f = self._make_file("malware.pdf", content=b"MZ\x90\x00\x03\x00\x00\x00")
        with pytest.raises(ValidationException, match="可执行文件"):
            self.adapter.validate_uploaded_file(f)

    def test_executable_elf_detected(self) -> None:
        f = self._make_file("elf.pdf", content=b"\x7fELF\x02\x01\x01\x00")
        with pytest.raises(ValidationException, match="可执行文件"):
            self.adapter.validate_uploaded_file(f)

    def test_executable_macho_64_detected(self) -> None:
        f = self._make_file("app.pdf", content=b"\xcf\xfa\xed\xfe" + b"\x00" * 4)
        with pytest.raises(ValidationException, match="可执行文件"):
            self.adapter.validate_uploaded_file(f)

    def test_normal_file_not_flagged(self) -> None:
        f = self._make_file("normal.pdf", content=b"%PDF-1.4 normal content")
        result = self.adapter.validate_uploaded_file(f)
        assert result is f

    def test_no_limit_when_max_size_none(self) -> None:
        f = self._make_file("huge.pdf", size=999999999)
        result = self.adapter.validate_uploaded_file(f, max_size_bytes=None)
        assert result is f

    def test_no_restrictions_when_params_none(self) -> None:
        f = self._make_file("any.xyz")
        result = self.adapter.validate_uploaded_file(f)
        assert result is f
