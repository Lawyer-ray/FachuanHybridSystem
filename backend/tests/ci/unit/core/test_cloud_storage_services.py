"""Tests for cloud storage services: LocalProvider, NullProvider, factory."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from apps.core.cloud_storage.local import LocalProvider
from apps.core.cloud_storage.null_provider import NullProvider
from apps.core.cloud_storage.factory import create_provider_for_binding, create_provider_from_account
from apps.core.cloud_storage.protocols import CloudFileInfo


class TestLocalProvider:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.provider = LocalProvider(root=self.tmpdir)

    def test_list_directory_empty(self):
        result = self.provider.list_directory(".")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_list_directory_with_files(self):
        # Create test files
        (Path(self.tmpdir) / "test.txt").write_text("hello")
        (Path(self.tmpdir) / "subdir").mkdir()
        result = self.provider.list_directory(".")
        names = [f.name for f in result]
        assert "test.txt" in names
        assert "subdir" in names

    def test_list_directory_sorted(self):
        (Path(self.tmpdir) / "b_file.txt").write_text("b")
        (Path(self.tmpdir) / "a_file.txt").write_text("a")
        result = self.provider.list_directory(".")
        names = [f.name for f in result]
        assert names == sorted(names, key=str.lower)

    def test_list_directory_hidden_files(self):
        (Path(self.tmpdir) / ".hidden").write_text("hidden")
        result = self.provider.list_directory(".")
        names = [f.name for f in result]
        assert ".hidden" in names

    def test_read_file(self):
        (Path(self.tmpdir) / "test.txt").write_bytes(b"content")
        result = self.provider.read_file("test.txt")
        assert result == b"content"

    def test_read_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            self.provider.read_file("nonexistent.txt")

    def test_write_file(self):
        self.provider.write_file("new_dir/new_file.txt", b"data")
        assert (Path(self.tmpdir) / "new_dir" / "new_file.txt").read_bytes() == b"data"

    def test_mkdir(self):
        self.provider.mkdir("new_dir/sub")
        assert (Path(self.tmpdir) / "new_dir" / "sub").is_dir()

    def test_exists_true(self):
        (Path(self.tmpdir) / "exists.txt").write_text("yes")
        assert self.provider.exists("exists.txt") is True

    def test_exists_false(self):
        assert self.provider.exists("nope.txt") is False

    def test_is_dir_true(self):
        (Path(self.tmpdir) / "mydir").mkdir()
        assert self.provider.is_dir("mydir") is True

    def test_is_dir_false(self):
        (Path(self.tmpdir) / "file.txt").write_text("x")
        assert self.provider.is_dir("file.txt") is False

    def test_delete_file(self):
        f = Path(self.tmpdir) / "to_delete.txt"
        f.write_text("delete me")
        self.provider.delete_file("to_delete.txt")
        assert not f.exists()

    def test_delete_nonexistent_file(self):
        # Should not raise
        self.provider.delete_file("nonexistent.txt")

    def test_get_file_info_exists(self):
        (Path(self.tmpdir) / "info.txt").write_bytes(b"hello")
        info = self.provider.get_file_info("info.txt")
        assert info is not None
        assert info.name == "info.txt"
        assert info.size == 5
        assert info.is_dir is False

    def test_get_file_info_dir(self):
        (Path(self.tmpdir) / "mydir").mkdir()
        info = self.provider.get_file_info("mydir")
        assert info is not None
        assert info.is_dir is True
        assert info.size == 0

    def test_get_file_info_not_found(self):
        info = self.provider.get_file_info("nonexistent")
        assert info is None

    def test_walk(self):
        (Path(self.tmpdir) / "a.txt").write_text("a")
        (Path(self.tmpdir) / "sub").mkdir()
        (Path(self.tmpdir) / "sub" / "b.txt").write_text("b")

        walked = list(self.provider.walk("."))
        assert len(walked) >= 2
        root_entry = walked[0]
        assert root_entry[0] == "."
        filenames = [f.name for f in root_entry[2]]
        assert "a.txt" in filenames

    def test_resolve_path_escape_blocked(self):
        with pytest.raises(OSError, match="路径逃逸"):
            self.provider.read_file("../../../etc/passwd")

    def test_file_info_properties(self):
        info = CloudFileInfo(
            name="test.pdf",
            path="docs/test.pdf",
            is_dir=False,
            size=1024,
            modified_at=1234567890.0,
        )
        assert info.name == "test.pdf"
        assert info.path == "docs/test.pdf"
        assert info.is_dir is False
        assert info.size == 1024


class TestNullProvider:
    def setup_method(self):
        self.provider = NullProvider(reason="测试错误")

    def test_list_directory_raises(self):
        with pytest.raises(RuntimeError, match="测试错误"):
            self.provider.list_directory("/")

    def test_read_file_raises(self):
        with pytest.raises(RuntimeError):
            self.provider.read_file("any")

    def test_write_file_raises(self):
        with pytest.raises(RuntimeError):
            self.provider.write_file("any", b"data")

    def test_mkdir_raises(self):
        with pytest.raises(RuntimeError):
            self.provider.mkdir("any")

    def test_exists_raises(self):
        with pytest.raises(RuntimeError):
            self.provider.exists("any")

    def test_is_dir_raises(self):
        with pytest.raises(RuntimeError):
            self.provider.is_dir("any")

    def test_delete_file_raises(self):
        with pytest.raises(RuntimeError):
            self.provider.delete_file("any")

    def test_get_file_info_raises(self):
        with pytest.raises(RuntimeError):
            self.provider.get_file_info("any")

    def test_walk_raises(self):
        with pytest.raises(RuntimeError):
            list(self.provider.walk("any"))

    def test_default_reason(self):
        provider = NullProvider()
        with pytest.raises(RuntimeError, match="存储账号未配置"):
            provider.exists("/")


class TestFactory:
    def test_create_local_provider(self):
        binding = MagicMock()
        binding.storage_type = "local"
        provider = create_provider_for_binding(binding)
        assert isinstance(provider, LocalProvider)

    def test_create_webdav_no_account(self):
        binding = MagicMock()
        binding.storage_type = "webdav"
        binding.storage_account = None
        provider = create_provider_for_binding(binding)
        assert isinstance(provider, NullProvider)

    def test_create_onedrive_no_account(self):
        binding = MagicMock()
        binding.storage_type = "onedrive"
        binding.storage_account = None
        provider = create_provider_for_binding(binding)
        assert isinstance(provider, NullProvider)

    def test_create_s3_no_account(self):
        binding = MagicMock()
        binding.storage_type = "s3"
        binding.storage_account = None
        provider = create_provider_for_binding(binding)
        assert isinstance(provider, NullProvider)

    def test_create_google_drive_no_account(self):
        binding = MagicMock()
        binding.storage_type = "google_drive"
        binding.storage_account = None
        provider = create_provider_for_binding(binding)
        assert isinstance(provider, NullProvider)

    def test_create_dropbox_no_account(self):
        binding = MagicMock()
        binding.storage_type = "dropbox"
        binding.storage_account = None
        provider = create_provider_for_binding(binding)
        assert isinstance(provider, NullProvider)

    def test_unknown_storage_type(self):
        binding = MagicMock()
        binding.storage_type = "unknown_type"
        binding.storage_account = None
        provider = create_provider_for_binding(binding)
        assert isinstance(provider, NullProvider)

    def test_default_storage_type_is_local(self):
        binding = MagicMock(spec=[])  # no storage_type attr
        provider = create_provider_for_binding(binding)
        assert isinstance(provider, LocalProvider)
