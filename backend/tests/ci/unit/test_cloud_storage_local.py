"""LocalProvider 单元测试."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.core.cloud_storage.local import LocalProvider
from apps.core.cloud_storage.protocols import CloudFileInfo


@pytest.fixture
def provider(tmp_path: Path) -> LocalProvider:
    return LocalProvider(root=str(tmp_path))


@pytest.fixture
def sample_tree(tmp_path: Path) -> Path:
    """创建测试用目录结构."""
    root = tmp_path / "testroot"
    root.mkdir()
    (root / "dir_a").mkdir()
    (root / "dir_a" / "file_a1.txt").write_text("hello a1")
    (root / "dir_a" / "file_a2.pdf").write_bytes(b"%PDF-1.4 fake")
    (root / "dir_b").mkdir()
    (root / "dir_b" / "sub_b1").mkdir()
    (root / "dir_b" / "sub_b1" / "deep.pdf").write_bytes(b"%PDF-1.4 deep")
    (root / "top.txt").write_text("top level")
    return root


class TestListDirectory:
    def test_lists_files_and_dirs(self, provider: LocalProvider, sample_tree: Path):
        results = provider.list_directory("testroot")
        names = [r.name for r in results]
        assert "dir_a" in names
        assert "dir_b" in names
        assert "top.txt" in names

    def test_dirs_marked_correctly(self, provider: LocalProvider, sample_tree: Path):
        results = provider.list_directory("testroot")
        dir_a = next(r for r in results if r.name == "dir_a")
        top = next(r for r in results if r.name == "top.txt")
        assert dir_a.is_dir is True
        assert top.is_dir is False

    def test_sorted_case_insensitive(self, provider: LocalProvider, sample_tree: Path):
        results = provider.list_directory("testroot")
        names = [r.name for r in results]
        assert names == sorted(names, key=str.lower)

    def test_nonexistent_directory(self, provider: LocalProvider):
        results = provider.list_directory("nonexistent")
        assert results == []


class TestReadWriteFile:
    def test_write_and_read(self, provider: LocalProvider):
        provider.write_file("testroot/sub/file.txt", b"hello world")
        content = provider.read_file("testroot/sub/file.txt")
        assert content == b"hello world"

    def test_write_creates_parent_dirs(self, provider: LocalProvider):
        provider.write_file("a/b/c/d.bin", b"\x00\x01")
        assert provider.exists("a/b/c/d.bin")

    def test_read_nonexistent_raises(self, provider: LocalProvider):
        with pytest.raises(FileNotFoundError):
            provider.read_file("no_such_file.txt")


class TestMkdir:
    def test_creates_nested(self, provider: LocalProvider):
        provider.mkdir("a/b/c")
        assert provider.is_dir("a/b/c")

    def test_idempotent(self, provider: LocalProvider):
        provider.mkdir("x")
        provider.mkdir("x")
        assert provider.is_dir("x")


class TestExistsAndIsDir:
    def test_exists_file(self, provider: LocalProvider, sample_tree: Path):
        assert provider.exists("testroot/top.txt") is True

    def test_exists_dir(self, provider: LocalProvider, sample_tree: Path):
        assert provider.exists("testroot/dir_a") is True

    def test_not_exists(self, provider: LocalProvider):
        assert provider.exists("nope") is False

    def test_is_dir(self, provider: LocalProvider, sample_tree: Path):
        assert provider.is_dir("testroot/dir_a") is True
        assert provider.is_dir("testroot/top.txt") is False


class TestDeleteFile:
    def test_delete(self, provider: LocalProvider, sample_tree: Path):
        provider.delete_file("testroot/top.txt")
        assert not provider.exists("testroot/top.txt")

    def test_delete_nonexistent_no_error(self, provider: LocalProvider):
        provider.delete_file("nope.txt")


class TestGetFileInfo:
    def test_returns_info(self, provider: LocalProvider, sample_tree: Path):
        info = provider.get_file_info("testroot/top.txt")
        assert info is not None
        assert info.name == "top.txt"
        assert info.is_dir is False
        assert info.size == len(b"top level")

    def test_returns_dir_info(self, provider: LocalProvider, sample_tree: Path):
        info = provider.get_file_info("testroot/dir_a")
        assert info is not None
        assert info.is_dir is True
        assert info.size == 0

    def test_nonexistent_returns_none(self, provider: LocalProvider):
        assert provider.get_file_info("nope") is None


class TestWalk:
    def test_walks_tree(self, provider: LocalProvider, sample_tree: Path):
        collected = []
        for dirpath, dirs, files in provider.walk("testroot"):
            collected.append((dirpath, list(dirs), [f.name for f in files]))

        all_names = [f for _, _, files in collected for f in files]
        assert "top.txt" in all_names
        assert "file_a1.txt" in all_names
        assert "file_a2.pdf" in all_names
        assert "deep.pdf" in all_names

    def test_walk_empty_dir(self, provider: LocalProvider):
        provider.mkdir("empty")
        results = list(provider.walk("empty"))
        assert len(results) == 1
        assert results[0][2] == []


class TestCloudFileInfoContract:
    """Verify CloudFileInfo fields are populated correctly."""

    def test_list_directory_populates_all_fields(self, provider: LocalProvider, sample_tree: Path):
        results = provider.list_directory("testroot")
        for info in results:
            assert isinstance(info, CloudFileInfo)
            assert info.name
            assert info.path
            assert isinstance(info.is_dir, bool)
            assert isinstance(info.size, int)
            assert isinstance(info.modified_at, float)


class TestPathTraversal:
    """Verify path traversal attacks are blocked."""

    def test_dotdot_read_blocked(self, provider: LocalProvider, tmp_path: Path):
        """Reading outside root via .. should raise OSError."""
        (tmp_path / "secret.txt").write_text("secret")
        with pytest.raises(OSError, match="路径逃逸"):
            provider.read_file("../../../secret.txt")

    def test_dotdot_write_blocked(self, provider: LocalProvider, tmp_path: Path):
        """Writing outside root via .. should raise OSError."""
        with pytest.raises(OSError, match="路径逃逸"):
            provider.write_file("../../../evil.txt", b"bad")

    def test_dotdot_mkdir_blocked(self, provider: LocalProvider, tmp_path: Path):
        """Creating dir outside root via .. should raise OSError."""
        with pytest.raises(OSError, match="路径逃逸"):
            provider.mkdir("../../../evil_dir")

    def test_dotdot_exists_blocked(self, provider: LocalProvider, tmp_path: Path):
        """Checking existence outside root via .. should raise OSError."""
        with pytest.raises(OSError, match="路径逃逸"):
            provider.exists("../../../etc/passwd")

    def test_dotdot_delete_blocked(self, provider: LocalProvider, tmp_path: Path):
        """Deleting outside root via .. should raise OSError."""
        (tmp_path / "important.txt").write_text("keep")
        with pytest.raises(OSError, match="路径逃逸"):
            provider.delete_file("../../important.txt")

    def test_walk_stays_within_root(self, provider: LocalProvider, sample_tree: Path):
        """walk() should yield paths relative to root, not absolute."""
        for dirpath, _dirs, files in provider.walk("testroot"):
            assert not Path(dirpath).is_absolute(), f"dirpath should be relative: {dirpath}"
            for f in files:
                assert not Path(f.path).is_absolute(), f"file path should be relative: {f.path}"

    def test_normal_relative_path_works(self, provider: LocalProvider, sample_tree: Path):
        """Normal relative paths should work fine."""
        info = provider.get_file_info("testroot/top.txt")
        assert info is not None
        assert info.name == "top.txt"
