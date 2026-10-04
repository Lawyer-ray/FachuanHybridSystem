"""Coverage tests for core/filesystem/filesystem_service.py.

Covers:
  - FolderFilesystemService.__init__ and validator property
  - ensure_subdirectories
  - _get_unique_path
  - extract_zip_bytes
  - ensure_zip_within_limits（解压炸弹防护）
"""

from __future__ import annotations

import io
import struct
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException
from apps.core.filesystem.filesystem_service import (
    ZIP_MAX_MEMBER_COUNT,
    ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES,
    FolderFilesystemService,
    ensure_zip_within_limits,
)
from apps.core.filesystem.path_validator import FolderPathValidator


def _make_zip_with_fake_declared_size(declared_size: int) -> bytes:
    """构造 ZIP：central directory 头声明的解压后大小为 declared_size（数据极小）。

    模拟解压炸弹：头声明超大、实际数据极小，无需真实生成 GB 级内容。
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("huge.bin", b"tiny")
    data = buf.getvalue()
    cd_offset = data.rfind(b"PK\x01\x02")
    assert cd_offset != -1
    # central directory entry: uncompressed size 位于偏移 +24（4 字节小端）
    return data[: cd_offset + 24] + struct.pack("<I", declared_size) + data[cd_offset + 28 :]


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


class TestEnsureZipWithinLimits:
    def _zip_bytes(self, files: dict[str, str]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, content in files.items():
                zf.writestr(name, content)
        return buf.getvalue()

    def test_normal_zip_passes(self):
        with zipfile.ZipFile(io.BytesIO(self._zip_bytes({"a.txt": "hello"}))) as zf:
            assert ensure_zip_within_limits(zf) is None

    def test_declared_total_size_exceeded(self):
        """头声明总量超 2GB 即拒绝（无需真实数据）。"""
        bomb = _make_zip_with_fake_declared_size(ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES + 1)
        with zipfile.ZipFile(io.BytesIO(bomb)) as zf:
            with pytest.raises(ValidationException, match="解压总量超限"):
                ensure_zip_within_limits(zf)

    def test_member_count_exceeded(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for i in range(ZIP_MAX_MEMBER_COUNT + 1):
                zf.writestr(f"m{i}.txt", "x")
        with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as zf:
            with pytest.raises(ValidationException, match="条目数超限"):
                ensure_zip_within_limits(zf)

    def test_custom_limits_honored(self):
        with zipfile.ZipFile(io.BytesIO(self._zip_bytes({"a.txt": "hello"}))) as zf:
            with pytest.raises(ValidationException, match="解压总量超限"):
                ensure_zip_within_limits(zf, max_total_uncompressed_bytes=2)


class TestExtractZipBytesBombGuard:
    def test_zip_bomb_by_declared_size_rejected(self, tmp_path):
        svc = FolderFilesystemService()
        bomb = _make_zip_with_fake_declared_size(3 * 1024 * 1024 * 1024)  # 声明 3GB
        with pytest.raises(ValidationException, match="解压总量超限"):
            svc.extract_zip_bytes(str(tmp_path), bomb)
        assert not (tmp_path / "huge.bin").exists()  # 未解压任何内容

    def test_zip_bomb_by_member_count_rejected(self, tmp_path):
        svc = FolderFilesystemService()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for i in range(ZIP_MAX_MEMBER_COUNT + 1):
                zf.writestr(f"m{i}.txt", "x")
        with pytest.raises(ValidationException, match="条目数超限"):
            svc.extract_zip_bytes(str(tmp_path), buf.getvalue())
        assert list(tmp_path.iterdir()) == []
