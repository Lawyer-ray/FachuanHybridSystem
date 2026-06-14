"""补充覆盖测试: core/filesystem/folder_binding_base.py (35 missing)

覆盖: _is_cloud_storage, check_folder_accessible (local + cloud),
format_path_for_display, is_browsable_path, compute_parent_path,
check_and_repair_path 等。
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.filesystem.folder_binding_base import BaseFolderBindingService


def _make_binding(
    folder_path: str = "/tmp/test",
    storage_type: str = "local",
    storage_account: object = None,
    folder_inode: int | None = None,
    folder_device: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        folder_path=folder_path,
        storage_type=storage_type,
        storage_account=storage_account,
        folder_inode=folder_inode,
        folder_device=folder_device,
        save=MagicMock(),
    )


# ── _is_cloud_storage ─────────────────────────────────────────────


class TestIsCloudStorage:
    def test_local_storage(self) -> None:
        svc = BaseFolderBindingService()
        binding = _make_binding(storage_type="local")
        assert svc._is_cloud_storage(binding) is False

    def test_cloud_storage_with_account(self) -> None:
        svc = BaseFolderBindingService()
        binding = _make_binding(storage_type="webdav", storage_account=SimpleNamespace(id=1))
        assert svc._is_cloud_storage(binding) is True

    def test_cloud_storage_no_account(self) -> None:
        svc = BaseFolderBindingService()
        binding = _make_binding(storage_type="webdav", storage_account=None)
        assert svc._is_cloud_storage(binding) is False

    def test_no_storage_type_attr(self) -> None:
        svc = BaseFolderBindingService()
        binding = SimpleNamespace(id=1)
        assert svc._is_cloud_storage(binding) is False


# ── check_folder_accessible ───────────────────────────────────────


class TestCheckFolderAccessible:
    def test_local_existing_dir(self, tmp_path: Path) -> None:
        svc = BaseFolderBindingService()
        assert svc.check_folder_accessible(str(tmp_path)) is True

    def test_local_nonexistent(self) -> None:
        svc = BaseFolderBindingService()
        assert svc.check_folder_accessible("/nonexistent/path/xyz") is False

    def test_local_file_not_dir(self, tmp_path: Path) -> None:
        svc = BaseFolderBindingService()
        f = tmp_path / "file.txt"
        f.write_text("hello")
        assert svc.check_folder_accessible(str(f)) is False

    def test_cloud_storage_accessible(self) -> None:
        svc = BaseFolderBindingService()
        mock_provider = MagicMock()
        mock_provider.is_dir.return_value = True

        binding = _make_binding(storage_type="webdav", storage_account=SimpleNamespace(id=1))
        with patch.object(svc, "_get_provider_for_binding", return_value=mock_provider):
            assert svc.check_folder_accessible("/cloud/folder", binding=binding) is True

    def test_cloud_storage_exception(self) -> None:
        svc = BaseFolderBindingService()
        mock_provider = MagicMock()
        mock_provider.is_dir.side_effect = Exception("network error")

        binding = _make_binding(storage_type="webdav", storage_account=SimpleNamespace(id=1))
        with patch.object(svc, "_get_provider_for_binding", return_value=mock_provider):
            assert svc.check_folder_accessible("/cloud/folder", binding=binding) is False


# ── format_path_for_display ───────────────────────────────────────


class TestFormatPathForDisplay:
    def test_empty_path(self) -> None:
        svc = BaseFolderBindingService()
        assert svc.format_path_for_display("") == ""

    def test_short_path(self) -> None:
        svc = BaseFolderBindingService()
        assert svc.format_path_for_display("/short") == "/short"

    def test_long_path_truncated(self) -> None:
        svc = BaseFolderBindingService()
        long_path = "/a" * 100
        result = svc.format_path_for_display(long_path, max_length=30)
        assert "..." in result
        assert len(result) == 30


# ── is_browsable_path ─────────────────────────────────────────────


class TestIsBrowsablePath:
    def test_normal_path(self) -> None:
        svc = BaseFolderBindingService()
        browsable, msg = svc.is_browsable_path("/Users/test/docs")
        assert browsable is True
        assert msg is None

    def test_network_path(self) -> None:
        svc = BaseFolderBindingService()
        with patch.object(svc.path_validator, "is_network_path", return_value=True):
            browsable, msg = svc.is_browsable_path("//server/share")
            assert browsable is False
            assert "网络路径" in (msg or "")


# ── compute_parent_path ───────────────────────────────────────────


class TestComputeParentPath:
    def test_parent_in_roots(self, tmp_path: Path) -> None:
        svc = BaseFolderBindingService()
        with patch.object(svc, "get_browse_roots", return_value=[tmp_path]):
            result = svc.compute_parent_path(tmp_path / "subdir" / "file")
            assert result == str(tmp_path / "subdir")

    def test_parent_not_in_roots(self, tmp_path: Path) -> None:
        svc = BaseFolderBindingService()
        other = tmp_path / "other"
        with patch.object(svc, "get_browse_roots", return_value=[other]):
            result = svc.compute_parent_path(tmp_path / "subdir")
            assert result is None


# ── check_and_repair_path ─────────────────────────────────────────


class TestCheckAndRepairPath:
    def test_accessible_returns_true(self, tmp_path: Path) -> None:
        svc = BaseFolderBindingService()
        binding = _make_binding(folder_path=str(tmp_path))
        with patch.object(svc, "check_folder_accessible", return_value=True):
            accessible, repaired = svc.check_and_repair_path(binding)
            assert accessible is True
            assert repaired is False

    def test_cloud_accessible(self) -> None:
        svc = BaseFolderBindingService()
        binding = _make_binding(
            storage_type="webdav",
            storage_account=SimpleNamespace(id=1),
            folder_path="/cloud/folder",
        )
        mock_provider = MagicMock()
        mock_provider.is_dir.return_value = True

        with patch.object(svc, "_is_cloud_storage", return_value=True), \
             patch.object(svc, "_get_provider_for_binding", return_value=mock_provider):
            accessible, repaired = svc.check_and_repair_path(binding)
            assert accessible is True
            assert repaired is False

    def test_cloud_exception_returns_false(self) -> None:
        svc = BaseFolderBindingService()
        binding = _make_binding(
            storage_type="webdav",
            storage_account=SimpleNamespace(id=1),
            folder_path="/cloud/folder",
        )
        mock_provider = MagicMock()
        mock_provider.is_dir.side_effect = Exception("error")

        with patch.object(svc, "_is_cloud_storage", return_value=True), \
             patch.object(svc, "_get_provider_for_binding", return_value=mock_provider):
            accessible, repaired = svc.check_and_repair_path(binding)
            assert accessible is False
            assert repaired is False

    def test_inaccessible_no_inode(self) -> None:
        svc = BaseFolderBindingService()
        binding = _make_binding(folder_path="/gone", folder_inode=None, folder_device=None)
        with patch.object(svc, "check_folder_accessible", return_value=False):
            accessible, repaired = svc.check_and_repair_path(binding)
            assert accessible is False
            assert repaired is False

    def test_inaccessible_with_inode_finds_new_path(self) -> None:
        svc = BaseFolderBindingService()
        binding = _make_binding(folder_path="/old/path", folder_inode=12345, folder_device=1)
        with patch.object(svc, "check_folder_accessible", return_value=False), \
             patch.object(svc, "_search_by_inode", return_value="/new/path"), \
             patch.object(svc.inode_resolver, "get_inode_info", return_value=(12345, 1)):
            accessible, repaired = svc.check_and_repair_path(binding)
            assert accessible is True
            assert repaired is True
            assert binding.folder_path == "/new/path"
            binding.save.assert_called_once()

    def test_inaccessible_inode_not_found(self) -> None:
        svc = BaseFolderBindingService()
        binding = _make_binding(folder_path="/old", folder_inode=12345, folder_device=1)
        with patch.object(svc, "check_folder_accessible", return_value=False), \
             patch.object(svc, "_search_by_inode", return_value=None):
            accessible, repaired = svc.check_and_repair_path(binding)
            assert accessible is False
            assert repaired is False


# ── _maybe_fill_inode ─────────────────────────────────────────────


class TestMaybeFillInode:
    def test_no_inode_attr(self) -> None:
        svc = BaseFolderBindingService()
        binding = SimpleNamespace(id=1, folder_path="/test")
        svc._maybe_fill_inode(binding)  # Should not raise

    def test_inode_already_set(self) -> None:
        svc = BaseFolderBindingService()
        binding = _make_binding(folder_inode=999)
        svc._maybe_fill_inode(binding)
        binding.save.assert_not_called()

    def test_inode_filled(self, tmp_path: Path) -> None:
        svc = BaseFolderBindingService()
        binding = _make_binding(folder_path="/test", folder_inode=None)
        with patch.object(svc.inode_resolver, "get_inode_info", return_value=(42, 7)):
            svc._maybe_fill_inode(binding)
            assert binding.folder_inode == 42
            assert binding.folder_device == 7
            binding.save.assert_called_once()

    def test_inode_info_none(self) -> None:
        svc = BaseFolderBindingService()
        binding = _make_binding(folder_path="/test", folder_inode=None)
        with patch.object(svc.inode_resolver, "get_inode_info", return_value=None):
            svc._maybe_fill_inode(binding)
            binding.save.assert_not_called()


# ── Lazy property initialization ──────────────────────────────────


class TestLazyProperties:
    def test_path_validator_lazy(self) -> None:
        svc = BaseFolderBindingService()
        assert svc._path_validator is None
        validator = svc.path_validator
        assert validator is not None
        assert svc.path_validator is validator  # Same instance

    def test_filesystem_service_lazy(self) -> None:
        svc = BaseFolderBindingService()
        assert svc._filesystem_service is None
        fs = svc.filesystem_service
        assert fs is not None
        assert svc.filesystem_service is fs

    def test_inode_resolver_lazy(self) -> None:
        svc = BaseFolderBindingService()
        assert svc._inode_resolver is None
        resolver = svc.inode_resolver
        assert resolver is not None
        assert svc.inode_resolver is resolver
