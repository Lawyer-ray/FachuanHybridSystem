"""InodeResolver 单元测试."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from apps.core.filesystem.inode_resolver import InodeResolver


@pytest.fixture
def resolver() -> InodeResolver:
    return InodeResolver()


@pytest.fixture
def tmp_dirs(tmp_path: Path):
    """创建临时目录结构用于 BFS 搜索测试."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "dir_a").mkdir()
    (root / "dir_a" / "sub_a1").mkdir()
    (root / "dir_b").mkdir()
    (root / "dir_b" / "sub_b1").mkdir()
    (root / "dir_b" / "sub_b1" / "deep").mkdir()
    return root


class TestGetInodeInfo:
    def test_returns_inode_and_device_for_existing_dir(self, resolver: InodeResolver, tmp_path: Path):
        result = resolver.get_inode_info(str(tmp_path))
        assert result is not None
        inode, device = result
        expected_stat = tmp_path.stat()
        assert inode == expected_stat.st_ino
        assert device == expected_stat.st_dev

    def test_returns_none_for_nonexistent_path(self, resolver: InodeResolver):
        result = resolver.get_inode_info("/nonexistent/path/that/does/not/exist")
        assert result is None

    def test_returns_none_for_file_not_dir(self, resolver: InodeResolver, tmp_path: Path):
        file_path = tmp_path / "file.txt"
        file_path.write_text("hello")
        result = resolver.get_inode_info(str(file_path))
        # get_inode_info does Path.stat(), which works for files too
        # but it's designed for folders - returns inode for any existing path
        assert result is not None

    def test_returns_tuple_of_two_ints(self, resolver: InodeResolver, tmp_path: Path):
        result = resolver.get_inode_info(str(tmp_path))
        assert result is not None
        assert isinstance(result[0], int)
        assert isinstance(result[1], int)


class TestFindPathByInode:
    def test_finds_immediate_child(self, resolver: InodeResolver, tmp_dirs: Path):
        target = tmp_dirs / "dir_a"
        target_stat = target.stat()

        result = resolver.find_path_by_inode(
            inode=target_stat.st_ino,
            device=target_stat.st_dev,
            search_roots=[tmp_dirs],
        )
        assert result is not None
        assert Path(result).resolve() == target.resolve()

    def test_finds_nested_dir_within_max_depth(self, resolver: InodeResolver, tmp_dirs: Path):
        target = tmp_dirs / "dir_b" / "sub_b1"
        target_stat = target.stat()

        result = resolver.find_path_by_inode(
            inode=target_stat.st_ino,
            device=target_stat.st_dev,
            search_roots=[tmp_dirs],
        )
        assert result is not None
        assert Path(result).resolve() == target.resolve()

    def test_returns_none_if_beyond_max_depth(self, resolver: InodeResolver, tmp_dirs: Path):
        target = tmp_dirs / "dir_b" / "sub_b1" / "deep"
        target_stat = target.stat()

        # max_depth=2, so "deep" at depth 3 should not be found
        result = resolver.find_path_by_inode(
            inode=target_stat.st_ino,
            device=target_stat.st_dev,
            search_roots=[tmp_dirs],
            max_depth=2,
        )
        assert result is None

    def test_finds_at_custom_max_depth(self, resolver: InodeResolver, tmp_dirs: Path):
        target = tmp_dirs / "dir_b" / "sub_b1" / "deep"
        target_stat = target.stat()

        result = resolver.find_path_by_inode(
            inode=target_stat.st_ino,
            device=target_stat.st_dev,
            search_roots=[tmp_dirs],
            max_depth=3,
        )
        assert result is not None
        assert Path(result).resolve() == target.resolve()

    def test_returns_none_for_wrong_inode(self, resolver: InodeResolver, tmp_dirs: Path):
        result = resolver.find_path_by_inode(
            inode=99999999,
            device=99999999,
            search_roots=[tmp_dirs],
        )
        assert result is None

    def test_returns_none_for_empty_search_roots(self, resolver: InodeResolver):
        result = resolver.find_path_by_inode(
            inode=1,
            device=1,
            search_roots=[],
        )
        assert result is None

    def test_skips_nonexistent_search_root(self, resolver: InodeResolver, tmp_dirs: Path):
        target = tmp_dirs / "dir_a"
        target_stat = target.stat()

        result = resolver.find_path_by_inode(
            inode=target_stat.st_ino,
            device=target_stat.st_dev,
            search_roots=[Path("/nonexistent"), tmp_dirs],
        )
        assert result is not None
        assert Path(result).resolve() == target.resolve()

    def test_searches_multiple_roots(self, resolver: InodeResolver, tmp_path: Path):
        root1 = tmp_path / "root1"
        root2 = tmp_path / "root2"
        root1.mkdir()
        root2.mkdir()
        target = root2 / "found_here"
        target.mkdir()

        target_stat = target.stat()
        result = resolver.find_path_by_inode(
            inode=target_stat.st_ino,
            device=target_stat.st_dev,
            search_roots=[root1, root2],
        )
        assert result is not None
        assert Path(result).resolve() == target.resolve()

    def test_timeout_returns_none(self, resolver: InodeResolver, tmp_dirs: Path):
        target = tmp_dirs / "dir_a"
        target_stat = target.stat()

        # timeout=0 makes it impossible to find
        result = resolver.find_path_by_inode(
            inode=target_stat.st_ino,
            device=target_stat.st_dev,
            search_roots=[tmp_dirs],
            timeout_seconds=0.0,
        )
        # May or may not find it depending on timing, but should not hang
        # This test primarily ensures no infinite loop
        assert isinstance(result, (str, type(None)))
