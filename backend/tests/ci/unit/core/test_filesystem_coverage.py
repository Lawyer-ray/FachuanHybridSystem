"""Coverage tests for core.filesystem.filesystem_service and browse_policy."""

from unittest.mock import MagicMock, patch

import pytest

from apps.core.filesystem.filesystem_service import FolderFilesystemService
from apps.core.exceptions import ValidationException


class TestFolderFilesystemService:
    def _make(self):
        validator = MagicMock()
        return FolderFilesystemService(validator=validator), validator

    def test_validator_property_lazy(self):
        svc = FolderFilesystemService()
        assert svc.validator is not None

    def test_ensure_subdirectories_ok(self):
        svc, validator = self._make()
        validator.mkdirs.return_value = None
        result = svc.ensure_subdirectories("/base", ["a", "b"])
        assert result is True

    def test_ensure_subdirectories_fail(self):
        svc, validator = self._make()
        validator.mkdirs.side_effect = PermissionError("no access")
        result = svc.ensure_subdirectories("/base", ["a"])
        assert result is False

    def test_save_bytes(self):
        svc, validator = self._make()
        validator.sanitize_file_name.return_value = "test.txt"
        with patch("apps.core.filesystem.filesystem_service.Path") as MockPath:
            mock_path_obj = MagicMock()
            mock_parent = MagicMock()
            mock_path_obj.parent = mock_parent

            # base_dir / "sub" yields mock_parent (the directory loop)
            mock_path_obj.__truediv__ = MagicMock(return_value=mock_parent)

            # _get_unique_path calls parent_dir / file_name and checks exists()
            child_candidate = MagicMock()
            child_candidate.exists.return_value = False
            mock_parent.__truediv__ = MagicMock(return_value=child_candidate)

            MockPath.return_value = mock_path_obj
            with patch("builtins.open", MagicMock()):
                svc.save_bytes("/base", ["sub"], "test.txt", b"data")

    def test_get_unique_path_no_conflict(self):
        svc, validator = self._make()
        parent = MagicMock()
        candidate = MagicMock()
        candidate.exists.return_value = False
        parent.__truediv__ = MagicMock(return_value=candidate)
        with patch("apps.core.filesystem.filesystem_service.Path") as MockPath:
            mock_p = MagicMock()
            mock_p.stem = "test"
            mock_p.suffix = ".txt"
            MockPath.return_value = mock_p
            result = svc._get_unique_path(parent, "test.txt")
            assert result is not None


class TestFolderBrowsePolicy:
    @patch("apps.core.filesystem.browse_policy.settings")
    def test_get_browse_roots_empty(self, mock_settings):
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy

        mock_settings.FOLDER_BROWSE_ROOTS = None
        policy = FolderBrowsePolicy()
        with patch.object(policy, "_get_user_downloads_path", return_value=None):
            roots = policy.get_browse_roots()
            assert isinstance(roots, list)

    def test_is_network_path(self):
        from apps.core.filesystem.browse_policy import FolderBrowsePolicy

        policy = FolderBrowsePolicy()
        assert policy.validator.is_network_path("smb://server") is True
