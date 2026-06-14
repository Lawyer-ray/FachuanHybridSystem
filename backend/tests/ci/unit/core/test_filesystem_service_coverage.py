"""Coverage tests for core/filesystem/filesystem_service.py.

Covers:
  - FolderFilesystemService.__init__ and validator property
  - ensure_subdirectories
  - _get_unique_path
  - extract_zip_bytes
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.core.filesystem.filesystem_service import FolderFilesystemService
from apps.core.filesystem.path_validator import FolderPathValidator


class TestFolderFilesystemServiceInit:
    def test_init_defaults(self):
        svc = FolderFilesystemService()
        assert svc._validator is None

    def test_init_with_validator(self):
        validator = MagicMock(spec=FolderPathValidator)
        svc = FolderFilesystemService(validator=validator)
        assert svc.validator is validator

    def test_validator_property_creates_default(self):
        svc = FolderFilesystemService()
        v = svc.validator
        assert isinstance(v, FolderPathValidator)
        # Second access returns same instance
        assert svc.validator is v


class TestEnsureSubdirectories:
    def test_success(self, tmp_path):
        svc = FolderFilesystemService()
        result = svc.ensure_subdirectories(str(tmp_path), ["sub1", "sub2"])
        assert result is True
        assert (tmp_path / "sub1").is_dir()
        assert (tmp_path / "sub2").is_dir()

    def test_failure_returns_false(self):
        svc = FolderFilesystemService()
        result = svc.ensure_subdirectories("/nonexistent/path/that/should/not/exist", ["sub1"])
        assert result is False


class TestGetUniquePath:
    def test_unique_path_new_file(self, tmp_path):
        svc = FolderFilesystemService()
        result = svc._get_unique_path(tmp_path, "new_file.txt")
        assert str(result).endswith("new_file.txt")

    def test_unique_path_existing_file(self, tmp_path):
        svc = FolderFilesystemService()
        (tmp_path / "existing.txt").write_text("content")
        result = svc._get_unique_path(tmp_path, "existing.txt")
        assert str(result).endswith("existing_1.txt")

    def test_unique_path_multiple_existing(self, tmp_path):
        svc = FolderFilesystemService()
        (tmp_path / "file.txt").write_text("a")
        (tmp_path / "file_1.txt").write_text("b")
        result = svc._get_unique_path(tmp_path, "file.txt")
        assert str(result).endswith("file_2.txt")


class TestSaveBytes:
    def test_save_creates_file(self, tmp_path):
        svc = FolderFilesystemService()
        result = svc.save_bytes(str(tmp_path), [], "test.txt", b"hello")
        assert Path(result).exists()
        assert Path(result).read_bytes() == b"hello"

    def test_save_with_subdirs(self, tmp_path):
        svc = FolderFilesystemService()
        result = svc.save_bytes(str(tmp_path), ["sub"], "test.txt", b"data")
        assert "sub" in result
        assert Path(result).exists()

    def test_save_duplicate_name(self, tmp_path):
        svc = FolderFilesystemService()
        svc.save_bytes(str(tmp_path), [], "file.txt", b"first")
        result2 = svc.save_bytes(str(tmp_path), [], "file.txt", b"second")
        assert "file_1" in result2


class TestExtractZipBytes:
    def test_extract_valid_zip(self, tmp_path):
        svc = FolderFilesystemService()
        # Create a zip in memory
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("hello.txt", "hello world")
            zf.writestr("dir/nested.txt", "nested content")
        zip_bytes = buf.getvalue()

        result = svc.extract_zip_bytes(str(tmp_path), zip_bytes)
        assert (tmp_path / "hello.txt").exists()
        assert (tmp_path / "hello.txt").read_text() == "hello world"
        assert (tmp_path / "dir" / "nested.txt").exists()

    def test_extract_invalid_zip_raises(self, tmp_path):
        svc = FolderFilesystemService()
        with pytest.raises(Exception):
            svc.extract_zip_bytes(str(tmp_path), b"not a zip")
