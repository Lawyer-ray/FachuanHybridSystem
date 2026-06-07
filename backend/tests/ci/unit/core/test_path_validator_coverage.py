"""Coverage tests for core.filesystem.path_validator."""

from unittest.mock import MagicMock

import pytest

from apps.core.exceptions import ValidationException
from apps.core.filesystem.path_validator import FolderPathValidator


class TestFolderPathValidator:
    def _make(self):
        return FolderPathValidator()

    # -- is_network_path --
    def test_is_network_path_smb(self):
        v = self._make()
        assert v.is_network_path("smb://server/share") is True

    def test_is_network_path_unc(self):
        v = self._make()
        assert v.is_network_path("\\\\server\\share") is True

    def test_is_network_path_local(self):
        v = self._make()
        assert v.is_network_path("/home/user") is False

    def test_is_network_path_empty(self):
        v = self._make()
        assert v.is_network_path("") is False

    # -- validate_folder_path --
    def test_validate_empty(self):
        v = self._make()
        ok, msg = v.validate_folder_path("")
        assert ok is False

    def test_validate_unix_valid(self):
        v = self._make()
        ok, msg = v.validate_folder_path("/home/user/docs")
        assert ok is True
        assert msg is None

    def test_validate_unix_bad_chars(self):
        v = self._make()
        ok, msg = v.validate_folder_path("/home/user<>")
        assert ok is False

    def test_validate_windows_valid(self):
        v = self._make()
        ok, msg = v.validate_folder_path("C:\\Users\\test")
        assert ok is True

    def test_validate_windows_double_colon(self):
        v = self._make()
        ok, msg = v.validate_folder_path("C:\\Users\\te:st")
        assert ok is False

    def test_validate_network_unc(self):
        v = self._make()
        ok, msg = v.validate_folder_path("\\\\server\\share")
        assert ok is True

    def test_validate_smb(self):
        v = self._make()
        ok, msg = v.validate_folder_path("smb://server/share")
        assert ok is True

    def test_validate_relative(self):
        v = self._make()
        ok, msg = v.validate_folder_path("just_a_name")
        assert ok is False

    # -- sanitize_file_name --
    def test_sanitize_file_name_valid(self):
        v = self._make()
        result = v.sanitize_file_name("test.docx")
        assert result == "test.docx"

    def test_sanitize_file_name_empty(self):
        v = self._make()
        with pytest.raises(ValidationException):
            v.sanitize_file_name("")

    def test_sanitize_file_name_with_slash(self):
        v = self._make()
        with pytest.raises(ValidationException):
            v.sanitize_file_name("dir/file.txt")

    def test_sanitize_file_name_dot_dot(self):
        v = self._make()
        with pytest.raises(ValidationException):
            v.sanitize_file_name("..")

    # -- sanitize_relative_dir --
    def test_sanitize_relative_dir_valid(self):
        v = self._make()
        parts = v.sanitize_relative_dir("a/b/c")
        assert parts == ["a", "b", "c"]

    def test_sanitize_relative_dir_empty(self):
        v = self._make()
        with pytest.raises(ValidationException):
            v.sanitize_relative_dir("")

    def test_sanitize_relative_dir_absolute(self):
        v = self._make()
        with pytest.raises(ValidationException):
            v.sanitize_relative_dir("/a/b")

    def test_sanitize_relative_dir_dot_dot(self):
        v = self._make()
        with pytest.raises(ValidationException):
            v.sanitize_relative_dir("../etc")

    # -- normalize_relative_path --
    def test_normalize_valid(self):
        v = self._make()
        result = v.normalize_relative_path("a/b/c")
        assert result == "a/b/c"

    def test_normalize_none(self):
        v = self._make()
        with pytest.raises(ValidationException):
            v.normalize_relative_path(None)

    def test_normalize_absolute(self):
        v = self._make()
        with pytest.raises(ValidationException):
            v.normalize_relative_path("/etc/passwd")

    def test_normalize_tilde(self):
        v = self._make()
        with pytest.raises(ValidationException):
            v.normalize_relative_path("~/.ssh")

    def test_normalize_dot_dot(self):
        v = self._make()
        with pytest.raises(ValidationException):
            v.normalize_relative_path("../secret")

    def test_normalize_bad_chars(self):
        v = self._make()
        with pytest.raises(ValidationException):
            v.normalize_relative_path("a<b")

    # -- sanitize_zip_member_path --
    def test_sanitize_zip_valid(self):
        v = self._make()
        parts = v.sanitize_zip_member_path("a/b.txt")
        assert parts == ["a", "b.txt"]

    def test_sanitize_zip_empty(self):
        v = self._make()
        with pytest.raises(ValidationException):
            v.sanitize_zip_member_path("")

    def test_sanitize_zip_dot_dot(self):
        v = self._make()
        with pytest.raises(ValidationException):
            v.sanitize_zip_member_path("../etc/passwd")

    def test_sanitize_zip_leading_slash(self):
        v = self._make()
        parts = v.sanitize_zip_member_path("/a/b.txt")
        assert parts == ["a", "b.txt"]

    # -- ensure_within_base --
    def test_ensure_within_base_ok(self):
        from apps.core.utils.path import Path

        v = self._make()
        # Should not raise
        v.ensure_within_base(Path("/base"), Path("/base/sub"))

    def test_ensure_within_base_violation(self):
        from apps.core.utils.path import Path

        v = self._make()
        with pytest.raises(ValidationException):
            v.ensure_within_base(Path("/base"), Path("/other"))

    # -- mkdirs --
    def test_mkdirs_makedirs_p(self):
        v = self._make()
        mock_path = MagicMock()
        mock_path.makedirs_p = MagicMock()
        v.mkdirs(mock_path)
        mock_path.makedirs_p.assert_called_once()

    def test_mkdirs_mkdir(self):
        v = self._make()
        mock_path = MagicMock(spec=["mkdir"])
        v.mkdirs(mock_path)
        mock_path.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    def test_mkdirs_no_method(self):
        v = self._make()
        with pytest.raises(ValidationException):
            v.mkdirs("not_a_path_object")
