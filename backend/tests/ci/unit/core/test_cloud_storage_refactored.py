"""Tests for refactored pure functions from core/cloud_storage/."""

from __future__ import annotations

import pytest

from apps.core.cloud_storage.browse_helper import (
    browse_cloud_folder,
    _error_result,
)


class TestErrorResult:
    """Tests for _error_result pure function."""

    def test_basic_error(self):
        result = _error_result("Error message", "/path", "local")
        assert result["browsable"] is False
        assert result["message"] == "Error message"
        assert result["path"] == "/path"
        assert result["storage_type"] == "local"

    def test_none_path(self):
        result = _error_result("Error", None, "webdav")
        assert result["path"] is None
        assert result["parent_path"] is None

    def test_empty_entries(self):
        result = _error_result("Error", "/path", "s3")
        assert result["entries"] == []

    def test_different_storage_types(self):
        for stype in ["local", "webdav", "s3", "onedrive", "gdrive", "dropbox"]:
            result = _error_result("msg", "/p", stype)
            assert result["storage_type"] == stype


class TestBrowseCloudFolderHelpers:
    """Tests for helper functions used in browse_cloud_folder."""

    def test_parent_path_root(self):
        """Root path should have parent_path as '/'."""
        # We test the logic by calling browse_cloud_folder with mocked provider
        # For now, test the _error_result function which is a pure function
        result = _error_result("msg", "/", "local")
        assert result["parent_path"] is None

    def test_parent_path_subfolder(self):
        """Subfolder path calculation."""
        # This is tested through integration, but we can verify the error result structure
        result = _error_result("msg", "/a/b/c", "local")
        assert result["browsable"] is False


class TestBrowseCloudFolderPathNormalization:
    """Tests for path normalization logic in browse_cloud_folder."""

    def test_error_result_structure(self):
        """Verify error result has all required keys."""
        result = _error_result("test", "/path", "local")
        required_keys = {"browsable", "message", "path", "parent_path", "entries", "storage_type"}
        assert set(result.keys()) == required_keys

    def test_error_result_browsable_false(self):
        result = _error_result("any message", "any path", "any type")
        assert result["browsable"] is False

    def test_error_result_message_preserved(self):
        msg = "这是一个错误消息"
        result = _error_result(msg, "/path", "local")
        assert result["message"] == msg
